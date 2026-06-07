"""
Authentication & RBAC for the Banking AI Copilot.

Provides:
  - JWT token generation and validation
  - User management (create, verify, seed demo users)
  - Role-based access control (admin, banker, fraud_analyst, compliance_officer)
  - FastAPI dependency for protected routes

Roles:
  admin             — full access to everything
  banker            — Banker Copilot + Fraud Monitor + Documents (read only)
  fraud_analyst     — Fraud Monitor only
  compliance_officer — Documents + Policy Query only

Demo users (seeded on startup):
  admin / Admin@2026       role: admin
  banker1 / Banker@2026    role: banker
  analyst / Analyst@2026   role: fraud_analyst
  compliance / Comply@2026 role: compliance_officer
"""
import os
from datetime import datetime, timedelta
from typing import Optional, List

import bcrypt as _bcrypt

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import JWTError, jwt
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE-ME-IN-PRODUCTION-use-256-bit-random-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))  # 8 hours
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")

# ── Roles ─────────────────────────────────────────────────────
ROLES = {
    "admin": {
        "label": "Administrator",
        "permissions": ["chat", "fraud", "customer", "trust", "documents", "feedback", "admin"],
    },
    "banker": {
        "label": "Branch Banker",
        "permissions": ["chat", "fraud", "customer", "trust", "documents:read", "feedback"],
    },
    "fraud_analyst": {
        "label": "Fraud Analyst",
        "permissions": ["fraud", "customer:read", "trust:read"],
    },
    "compliance_officer": {
        "label": "Compliance Officer",
        "permissions": ["documents", "chat", "trust:read"],
    },
}

# ── Demo Users (seeded on startup) ───────────────────────────
DEMO_USERS = [
    {"username": "admin",      "password": "Admin@2026",      "role": "admin",              "full_name": "Alex Admin"},
    {"username": "banker1",    "password": "Banker@2026",     "role": "banker",             "full_name": "Sarah Chen"},
    {"username": "analyst",    "password": "Analyst@2026",    "role": "fraud_analyst",      "full_name": "Marcus Reid"},
    {"username": "compliance", "password": "Comply@2026",     "role": "compliance_officer", "full_name": "Diana Torres"},
]

# ── Crypto ────────────────────────────────────────────────────
def _hash_pw(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

def _verify_pw(password: str, hashed: str) -> bool:
    return _bcrypt.checkpw(password.encode(), hashed.encode())

bearer_scheme = HTTPBearer(auto_error=False)

router = APIRouter()


# ── DB helpers ────────────────────────────────────────────────

def _engine():
    return create_engine(DATABASE_URL)


def ensure_users_table():
    """Create the users table if it doesn't exist and seed demo users."""
    engine = _engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'banker',
                full_name TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_login TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                action TEXT NOT NULL,
                resource TEXT NOT NULL,
                resource_id TEXT,
                ip_address TEXT,
                timestamp TEXT NOT NULL
            )
        """))
        conn.commit()

    # Seed demo users (skip if already exist)
    for u in DEMO_USERS:
        _create_user_if_missing(
            username=u["username"],
            password=u["password"],
            role=u["role"],
            full_name=u["full_name"],
        )


def _create_user_if_missing(username: str, password: str, role: str, full_name: str):
    engine = _engine()
    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM users WHERE username = :u"), {"u": username}
        ).fetchone()
        if existing:
            return
        hashed = _hash_pw(password)
        conn.execute(text("""
            INSERT INTO users (username, hashed_password, role, full_name, is_active, created_at)
            VALUES (:u, :h, :r, :fn, 1, :ts)
        """), {"u": username, "h": hashed, "r": role, "fn": full_name, "ts": datetime.now().isoformat()})
        conn.commit()
    print(f"  [Auth] Seeded user: {username} ({role})")


def _get_user(username: str) -> Optional[dict]:
    engine = _engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM users WHERE username = :u AND is_active = 1"), {"u": username}
        ).fetchone()
    if row:
        return dict(row._mapping)
    return None


def _update_last_login(username: str):
    engine = _engine()
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE users SET last_login = :ts WHERE username = :u"),
            {"ts": datetime.now().isoformat(), "u": username},
        )
        conn.commit()


def log_audit(username: str, action: str, resource: str, resource_id: str = "", ip: str = ""):
    """Write an audit log entry for PII-access and sensitive actions."""
    try:
        engine = _engine()
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO audit_log (username, action, resource, resource_id, ip_address, timestamp)
                VALUES (:u, :a, :r, :rid, :ip, :ts)
            """), {
                "u": username, "a": action, "r": resource,
                "rid": resource_id, "ip": ip, "ts": datetime.now().isoformat(),
            })
            conn.commit()
    except Exception:
        pass  # Never block the main request on audit failure


# ── Token helpers ─────────────────────────────────────────────

def _create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload["iat"] = datetime.utcnow()
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# ── FastAPI Dependencies ──────────────────────────────────────

class CurrentUser(BaseModel):
    username: str
    role: str
    full_name: str
    permissions: List[str]


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> CurrentUser:
    """
    Dependency: validates Bearer JWT and returns the current user.
    Raises 401 if token is missing or invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = _decode_token(credentials.credentials)
        username: str = payload.get("sub")
        if not username:
            raise ValueError("sub missing")
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = _get_user(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated.",
        )

    role_perms = ROLES.get(user["role"], {}).get("permissions", [])
    return CurrentUser(
        username=username,
        role=user["role"],
        full_name=user.get("full_name", ""),
        permissions=role_perms,
    )


def require_permission(permission: str):
    """
    Dependency factory: ensures the current user has a specific permission.

    Usage:
        @router.get("/admin-only")
        async def admin_only(user=Depends(require_permission("admin"))):
            ...
    """
    def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        # Exact match or prefix match (e.g. "documents" covers "documents:read")
        has = any(
            p == permission or p.split(":")[0] == permission
            for p in user.permissions
        )
        if not has:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required. Your role: {user.role}.",
            )
        return user
    return _check


# ── Auth Routes ───────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class UserInfo(BaseModel):
    username: str
    role: str
    role_label: str
    full_name: str
    permissions: List[str]


@router.post("/login", response_model=TokenResponse, tags=["Authentication"])
async def login(request: LoginRequest):
    """
    Authenticate and receive a JWT bearer token.

    Demo credentials:
    - admin / Admin@2026
    - banker1 / Banker@2026
    - analyst / Analyst@2026
    - compliance / Comply@2026
    """
    user = _get_user(request.username)
    if not user or not _verify_pw(request.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    token = _create_access_token({"sub": user["username"], "role": user["role"]})
    _update_last_login(user["username"])

    role_info = ROLES.get(user["role"], {})
    return TokenResponse(
        access_token=token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "username": user["username"],
            "full_name": user.get("full_name", ""),
            "role": user["role"],
            "role_label": role_info.get("label", user["role"]),
            "permissions": role_info.get("permissions", []),
        },
    )


@router.get("/me", response_model=UserInfo, tags=["Authentication"])
async def get_me(current_user: CurrentUser = Depends(get_current_user)):
    """Return the currently authenticated user's profile and permissions."""
    role_info = ROLES.get(current_user.role, {})
    return UserInfo(
        username=current_user.username,
        role=current_user.role,
        role_label=role_info.get("label", current_user.role),
        full_name=current_user.full_name,
        permissions=current_user.permissions,
    )


@router.post("/logout", tags=["Authentication"])
async def logout(current_user: CurrentUser = Depends(get_current_user)):
    """Invalidate the current session (client must discard the token)."""
    log_audit(current_user.username, "logout", "auth")
    return {"status": "ok", "message": "Logged out successfully."}


@router.get("/users", tags=["Authentication"])
async def list_users(current_user: CurrentUser = Depends(require_permission("admin"))):
    """Admin only: list all users."""
    engine = _engine()
    import pandas as pd
    df = pd.read_sql(
        "SELECT id, username, role, full_name, is_active, created_at, last_login FROM users",
        engine,
    )
    return {"status": "ok", "users": df.to_dict(orient="records")}


@router.get("/audit-log", tags=["Authentication"])
async def get_audit_log(
    limit: int = 50,
    current_user: CurrentUser = Depends(require_permission("admin")),
):
    """Admin only: view audit log of data access and sensitive actions."""
    engine = _engine()
    import pandas as pd
    df = pd.read_sql(
        f"SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT {limit}",
        engine,
    )
    return {"status": "ok", "entries": df.to_dict(orient="records")}
