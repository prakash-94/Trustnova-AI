"""
TrustNova AI — Authentication & RBAC
12 banking roles, JWT tokens, granular permissions.
"""
import os
from datetime import datetime, timedelta
from typing import Optional, List

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from src.models.database import auto_pk
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE-IN-PRODUCTION-256bit-random")
ALGORITHM  = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

# ── Role Definitions ──────────────────────────────────────────────────────────

ROLES: dict[str, dict] = {
    "admin": {
        "label": "Administrator",
        "permissions": ["*"],  # wildcard — all permissions
        "nav_sections": ["all"],
    },
    "personal_banker": {
        "label": "Personal Banker",
        "permissions": [
            "customers:read", "customers:write",
            "accounts:read",
            "transactions:read",
            "credit_cards:read",
            "kyc:read",
            "risk:read",
            "chat:all",
        ],
        "nav_sections": ["customer_search", "customer360", "accounts", "transactions", "credit_cards", "kyc_center", "ai_copilot"],
    },
    "branch_manager": {
        "label": "Branch Manager",
        "permissions": [
            "customers:read", "customers:write",
            "accounts:read", "accounts:write",
            "transactions:read",
            "credit_cards:read",
            "loans:read",
            "kyc:read", "kyc:write",
            "risk:read",
            "reports:read",
            "chat:all",
        ],
        "nav_sections": ["customer_search", "customer360", "accounts", "transactions", "loans", "credit_cards", "kyc_center", "risk_center", "ai_copilot"],
    },
    "loan_officer": {
        "label": "Loan Officer",
        "permissions": [
            "customers:read",
            "accounts:read",
            "transactions:read",
            "loans:read", "loans:write", "loans:approve",
            "risk:read",
            "kyc:read",
            "chat:all",
        ],
        "nav_sections": ["customer_search", "customer360", "accounts", "loans", "risk_center", "ai_copilot"],
    },
    "mortgage_officer": {
        "label": "Mortgage Officer",
        "permissions": [
            "customers:read",
            "accounts:read",
            "transactions:read",
            "loans:read", "loans:write",
            "risk:read",
            "kyc:read",
            "chat:all",
        ],
        "nav_sections": ["customer_search", "customer360", "accounts", "loans", "risk_center", "ai_copilot"],
    },
    "underwriter": {
        "label": "Underwriter",
        "permissions": [
            "customers:read",
            "accounts:read",
            "transactions:read",
            "loans:read", "loans:approve",
            "risk:read", "risk:write",
            "kyc:read",
            "chat:all",
        ],
        "nav_sections": ["customer_search", "customer360", "loans", "risk_center", "ai_copilot"],
    },
    "aml_analyst": {
        "label": "AML Analyst",
        "permissions": [
            "customers:read",
            "accounts:read",
            "transactions:read",
            "aml:read", "aml:write", "aml:sar",
            "risk:read",
            "reports:read",
            "chat:all",
        ],
        "nav_sections": ["customer_search", "customer360", "transactions", "aml_center", "risk_center", "ai_copilot"],
    },
    "kyc_analyst": {
        "label": "KYC Analyst",
        "permissions": [
            "customers:read", "customers:write",
            "accounts:read",
            "kyc:read", "kyc:write",
            "risk:read",
            "chat:all",
        ],
        "nav_sections": ["customer_search", "customer360", "kyc_center", "risk_center", "ai_copilot"],
    },
    "fraud_analyst": {
        "label": "Fraud Analyst",
        "permissions": [
            "customers:read",
            "accounts:read",
            "transactions:read",
            "fraud:read", "fraud:write", "fraud:investigate",
            "risk:read",
            "chat:all",
        ],
        "nav_sections": ["customer_search", "customer360", "transactions", "fraud_center", "risk_center", "ai_copilot"],
    },
    "commercial_banker": {
        "label": "Commercial Relationship Manager",
        "permissions": [
            "customers:read", "customers:write",
            "accounts:read",
            "transactions:read",
            "loans:read", "loans:write",
            "risk:read",
            "kyc:read",
            "chat:all",
        ],
        "nav_sections": ["customer_search", "customer360", "accounts", "loans", "transactions", "risk_center", "ai_copilot"],
    },
    "credit_risk_analyst": {
        "label": "Credit Risk Analyst",
        "permissions": [
            "customers:read",
            "accounts:read",
            "transactions:read",
            "loans:read",
            "credit_cards:read",
            "risk:read", "risk:write",
            "aml:read",
            "reports:read",
            "chat:all",
        ],
        "nav_sections": ["customer_search", "customer360", "loans", "risk_center", "compliance_center", "ai_copilot"],
    },
    "operations_specialist": {
        "label": "Operations Specialist",
        "permissions": [
            "customers:read",
            "accounts:read",
            "transactions:read",
            "wire_transfers:read", "wire_transfers:write",
            "kyc:read",
            "chat:all",
        ],
        "nav_sections": ["customer_search", "accounts", "transactions", "ai_copilot"],
    },
    "treasury_analyst": {
        "label": "Treasury Analyst",
        "permissions": [
            "accounts:read",
            "transactions:read",
            "wire_transfers:read",
            "treasury:read", "treasury:write",
            "reports:read",
            "chat:all",
        ],
        "nav_sections": ["treasury_dashboard", "transactions", "ai_copilot"],
    },
    "executive": {
        "label": "Bank Executive",
        "permissions": [
            "customers:read", "customers:write",
            "accounts:read",
            "transactions:read",
            "loans:read",
            "credit_cards:read",
            "appointments:read", "appointments:write",
            "chat:all",
        ],
        "nav_sections": [
            "home", "ai_copilot",
            "customer_search", "customer360",
            "accounts", "transactions", "loans",
            "appointments", "credit_cards",
        ],
    },
}

DEMO_USERS = [
    {"username": "admin",       "password": "Admin@2026",      "role": "admin",              "full_name": "Alex Admin"},
    {"username": "banker1",     "password": "Banker@2026",     "role": "personal_banker",    "full_name": "Sarah Chen"},
    {"username": "manager",     "password": "Manager@2026",    "role": "branch_manager",     "full_name": "David Kim"},
    {"username": "loanofficer", "password": "Loan@2026",       "role": "loan_officer",       "full_name": "James Wilson"},
    {"username": "underwriter", "password": "Under@2026",      "role": "underwriter",        "full_name": "Emily Park"},
    {"username": "analyst",     "password": "Analyst@2026",    "role": "fraud_analyst",      "full_name": "Marcus Reid"},
    {"username": "amlanalyst",  "password": "Aml@2026",        "role": "aml_analyst",        "full_name": "Nina Torres"},
    {"username": "kyc",         "password": "Kyc@2026",        "role": "kyc_analyst",        "full_name": "Priya Sharma"},
    {"username": "commercial",  "password": "Comm@2026",       "role": "commercial_banker",  "full_name": "Robert Chen"},
    {"username": "treasury",    "password": "Treasury@2026",   "role": "treasury_analyst",   "full_name": "Angela Lee"},
    {"username": "compliance",  "password": "Comply@2026",     "role": "credit_risk_analyst","full_name": "Diana Torres"},
    {"username": "ops",         "password": "Ops@2026",        "role": "operations_specialist","full_name": "Tom Baker"},
    {"username": "executive",   "password": "Exec@2026",       "role": "executive",            "full_name": "Jennifer Walsh"},
]

# ── Crypto ────────────────────────────────────────────────────────────────────

def _hash_pw(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

def _verify_pw(password: str, hashed: str) -> bool:
    return _bcrypt.checkpw(password.encode(), hashed.encode())

bearer_scheme = HTTPBearer(auto_error=False)
router = APIRouter()

# ── DB-free user store (SQLite fallback) ──────────────────────────────────────

def ensure_users_table():
    """Create auth tables and seed users appropriate to the environment."""
    try:
        from src.models.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS users (
                    id {auto_pk},
                    username TEXT UNIQUE NOT NULL,
                    hashed_password TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'personal_banker',
                    full_name TEXT NOT NULL DEFAULT '',
                    email TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    last_login TEXT,
                    created_at TEXT NOT NULL
                )
            """))
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id {auto_pk},
                    username TEXT NOT NULL,
                    role TEXT,
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    resource_id TEXT,
                    customer_id TEXT,
                    ip_address TEXT,
                    timestamp TEXT NOT NULL
                )
            """))
            conn.commit()
        is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
        seed_demo = os.getenv("SEED_DEMO_USERS", "false" if is_production else "true").lower() in (
            "1", "true", "yes", "on"
        )
        if seed_demo:
            sync_passwords = os.getenv("RESET_DEMO_PASSWORDS", "true").lower() in ("1", "true", "yes", "on")
            for u in DEMO_USERS:
                _create_user_if_missing(
                    u["username"], u["password"], u["role"], u["full_name"],
                    sync_password=sync_passwords,
                )
        else:
            admin_password = os.getenv("ADMIN_PASSWORD", "")
            if admin_password:
                _create_user_if_missing(
                    os.getenv("ADMIN_USERNAME", "admin"), admin_password, "admin",
                    os.getenv("ADMIN_FULL_NAME", "TrustNova Administrator"),
                    sync_password=False,
                )
            else:
                print("[Auth] Production admin not seeded: set ADMIN_PASSWORD in Render.")
    except Exception as e:
        print(f"[Auth] Warning: could not seed users: {e}")


def _create_user_if_missing(
    username: str,
    password: str,
    role: str,
    full_name: str,
    *,
    sync_password: bool = False,
):
    from src.models.database import engine
    from sqlalchemy import text
    hashed = _hash_pw(password)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id FROM users WHERE username=:u"), {"u": username}).fetchone()
        if not row:
            conn.execute(text("""
                INSERT INTO users (username, hashed_password, role, full_name, is_active, created_at)
                VALUES (:u, :h, :r, :fn, 1, :ts)
            """), {"u": username, "h": hashed, "r": role, "fn": full_name, "ts": datetime.now().isoformat()})
            print(f"  [Auth] Seeded: {username} ({role})")
        elif sync_password:
            conn.execute(text("""
                UPDATE users SET hashed_password=:h, role=:r, full_name=:fn WHERE username=:u
            """), {"u": username, "h": hashed, "r": role, "fn": full_name})
        conn.commit()


def _get_user(username: str) -> Optional[dict]:
    from src.models.database import engine
    from sqlalchemy import text
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM users WHERE username=:u AND is_active=1"), {"u": username}
        ).fetchone()
    return dict(row._mapping) if row else None


def log_audit(username: str, role: str, action: str, resource: str,
              resource_id: str = "", customer_id: str = "", ip: str = ""):
    # Audit log table schema: id, username, action, resource, resource_id, ip_address, timestamp
    # (role and customer_id are not stored in the DB table — passed for future use)
    try:
        from src.models.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO audit_log (username, action, resource, resource_id, ip_address, timestamp)
                VALUES (:u, :a, :res, :rid, :ip, :ts)
            """), {
                "u": username, "a": action, "res": resource,
                "rid": resource_id or "",
                "ip": ip, "ts": datetime.now().isoformat()
            })
            conn.commit()
    except Exception:
        pass

# ── Token helpers ─────────────────────────────────────────────────────────────

def _create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def _decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

# ── Dependencies ──────────────────────────────────────────────────────────────

class CurrentUser(BaseModel):
    username: str
    role: str
    full_name: str
    permissions: List[str]
    nav_sections: List[str]


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> CurrentUser:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        payload = _decode_token(credentials.credentials)
        username = payload.get("sub")
        if not username:
            raise ValueError
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    user = _get_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    role_def = ROLES.get(user["role"], {})
    perms = role_def.get("permissions", [])
    return CurrentUser(
        username=username,
        role=user["role"],
        full_name=user.get("full_name", ""),
        permissions=perms,
        nav_sections=role_def.get("nav_sections", []),
    )


# Maps sidebar section IDs to the permissions they unlock via a temp grant.
# When a user has an active approved grant for a section, these permissions
# are treated as if the user's role already includes them.
SECTION_PERMISSIONS: dict[str, list[str]] = {
    "aml_center":   ["aml:read", "aml:write", "aml:sar"],
    "kyc_center":   ["kyc:read", "kyc:write"],
    "fraud_center": ["fraud:read", "fraud:write", "fraud:investigate"],
    "risk_center":  ["risk:read", "risk:write"],
    "loans":        ["loans:read"],
    "treasury_dashboard": ["treasury:read"],
    "compliance_center":  ["compliance:read"],
}


def _has_active_temp_grant(username: str, permission: str) -> bool:
    """
    Check the access_requests table for an active (approved + not expired)
    grant whose section covers the requested permission.
    Returns True if such a grant exists.
    """
    try:
        from src.models.database import engine
        from sqlalchemy import text as _text
        # Use the same "...Z" format that access_requests.py stores
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        with engine.connect() as conn:
            rows = conn.execute(_text("""
                SELECT section FROM access_requests
                WHERE  username   = :u
                  AND  status     = 'approved'
                  AND  expires_at IS NOT NULL
                  AND  expires_at > :now
            """), {"u": username, "now": now}).fetchall()
        for row in rows:
            section = row[0]
            granted_perms = SECTION_PERMISSIONS.get(section, [])
            perm_prefix = permission.split(":")[0]
            if any(
                gp == permission
                or gp.startswith(perm_prefix + ":")
                or permission.startswith(gp.split(":")[0] + ":")
                for gp in granted_perms
            ):
                return True
    except Exception:
        pass
    return False


def require_permission(permission: str):
    def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if "*" in user.permissions:
            return user  # admin wildcard
        # exact match or prefix match (e.g. "loans" covers "loans:read")
        has = any(
            p == permission
            or p.startswith(permission.split(":")[0] + ":")
            or permission.startswith(p.split(":")[0] + ":")
            for p in user.permissions
        )
        if not has:
            # Fall back to checking active temporary access grants
            if _has_active_temp_grant(user.username, permission):
                return user
            raise HTTPException(
                status_code=403,
                detail=f"Permission '{permission}' required. Your role: {user.role}."
            )
        return user
    return _check

# ── Auth Routes ───────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(req: LoginRequest, request: Request):
    user = _get_user(req.username)
    if not user or not _verify_pw(req.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    role_def = ROLES.get(user["role"], {})
    token = _create_access_token({"sub": user["username"], "role": user["role"]})
    log_audit(user["username"], user["role"], "login", "auth", ip=request.client.host if request.client else "")
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "username": user["username"],
            "full_name": user.get("full_name", ""),
            "role": user["role"],
            "role_label": role_def.get("label", user["role"]),
            "permissions": role_def.get("permissions", []),
            "nav_sections": role_def.get("nav_sections", []),
        },
    }


@router.get("/me")
async def get_me(current_user: CurrentUser = Depends(get_current_user)):
    role_def = ROLES.get(current_user.role, {})
    return {
        "username": current_user.username,
        "role": current_user.role,
        "role_label": role_def.get("label", current_user.role),
        "full_name": current_user.full_name,
        "permissions": current_user.permissions,
        "nav_sections": current_user.nav_sections,
    }


@router.post("/logout")
async def logout(current_user: CurrentUser = Depends(get_current_user)):
    log_audit(current_user.username, current_user.role, "logout", "auth")
    return {"message": "Logged out successfully."}


@router.get("/roles")
async def list_roles(current_user: CurrentUser = Depends(require_permission("admin"))):
    return {
        role: {"label": info["label"], "nav_sections": info["nav_sections"]}
        for role, info in ROLES.items()
    }
