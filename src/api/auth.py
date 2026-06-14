"""
TrustNova AI — Authentication & RBAC
13 banking roles, JWT tokens, granular nav_sections + permissions.
"""
import os
from datetime import datetime, timedelta
from typing import Optional, List

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import JWTError, jwt
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE-ME-IN-PRODUCTION-use-256-bit-random-key")
ALGORITHM  = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")

# ── Role Definitions ──────────────────────────────────────────────────────────
ROLES: dict[str, dict] = {
    "admin": {
        "label": "Administrator",
        "permissions": ["*"],
        "nav_sections": ["all"],
    },
    "personal_banker": {
        "label": "Personal Banker",
        "permissions": ["customers:read","customers:write","accounts:read","transactions:read","credit_cards:read","credit_cards:write","kyc:read","risk:read","chat:all","appointments:read","appointments:write"],
        "nav_sections": ["home","customer_search","customer360","accounts","transactions","credit_cards","kyc_center","ai_copilot"],
    },
    "branch_manager": {
        "label": "Branch Manager",
        "permissions": ["customers:read","customers:write","accounts:read","accounts:write","transactions:read","credit_cards:read","credit_cards:write","loans:read","kyc:read","kyc:write","risk:read","reports:read","chat:all","appointments:read","appointments:write"],
        "nav_sections": ["home","customer_search","customer360","accounts","transactions","loans","credit_cards","kyc_center","risk_center","ai_copilot"],
    },
    "loan_officer": {
        "label": "Loan Officer",
        "permissions": ["customers:read","accounts:read","transactions:read","loans:read","loans:write","loans:approve","risk:read","kyc:read","chat:all"],
        "nav_sections": ["home","customer_search","customer360","accounts","loans","risk_center","ai_copilot"],
    },
    "underwriter": {
        "label": "Underwriter",
        "permissions": ["customers:read","accounts:read","transactions:read","loans:read","loans:approve","risk:read","risk:write","kyc:read","chat:all"],
        "nav_sections": ["home","customer_search","customer360","loans","risk_center","ai_copilot"],
    },
    "fraud_analyst": {
        "label": "Fraud Analyst",
        "permissions": ["customers:read","accounts:read","transactions:read","fraud:read","fraud:write","fraud:investigate","risk:read","chat:all"],
        "nav_sections": ["home","customer_search","customer360","transactions","fraud_center","risk_center","ai_copilot"],
    },
    "aml_analyst": {
        "label": "AML Analyst",
        "permissions": ["customers:read","accounts:read","transactions:read","aml:read","aml:write","aml:sar","risk:read","reports:read","chat:all"],
        "nav_sections": ["home","customer_search","customer360","transactions","aml_center","risk_center","ai_copilot"],
    },
    "kyc_analyst": {
        "label": "KYC Analyst",
        "permissions": ["customers:read","customers:write","accounts:read","kyc:read","kyc:write","risk:read","chat:all"],
        "nav_sections": ["home","customer_search","customer360","kyc_center","risk_center","ai_copilot"],
    },
    "commercial_banker": {
        "label": "Commercial Relationship Manager",
        "permissions": ["customers:read","customers:write","accounts:read","transactions:read","loans:read","loans:write","risk:read","kyc:read","chat:all"],
        "nav_sections": ["home","customer_search","customer360","accounts","loans","transactions","risk_center","ai_copilot"],
    },
    "credit_risk_analyst": {
        "label": "Credit Risk Analyst",
        "permissions": ["customers:read","accounts:read","transactions:read","loans:read","credit_cards:read","risk:read","risk:write","aml:read","reports:read","chat:all"],
        "nav_sections": ["home","customer_search","customer360","loans","risk_center","compliance_center","ai_copilot"],
    },
    "operations_specialist": {
        "label": "Operations Specialist",
        "permissions": ["customers:read","accounts:read","transactions:read","kyc:read","chat:all"],
        "nav_sections": ["home","customer_search","accounts","transactions","ai_copilot"],
    },
    "treasury_analyst": {
        "label": "Treasury Analyst",
        "permissions": ["accounts:read","transactions:read","treasury:read","treasury:write","reports:read","chat:all"],
        "nav_sections": ["home","treasury_dashboard","transactions","ai_copilot"],
    },
    "executive": {
        "label": "Bank Executive",
        "permissions": ["customers:read","customers:write","accounts:read","transactions:read","loans:read","credit_cards:read","credit_cards:write","appointments:read","appointments:write","chat:all"],
        "nav_sections": ["home","ai_copilot","customer_search","customer360","accounts","transactions","loans","appointments","credit_cards"],
    },
}

DEMO_USERS = [
    {"username": "admin",       "password": "Admin@2026",    "role": "admin",              "full_name": "Alex Admin"},
    {"username": "executive",   "password": "Exec@2026",     "role": "executive",          "full_name": "Jennifer Walsh"},
    {"username": "banker1",     "password": "Banker@2026",   "role": "personal_banker",    "full_name": "Sarah Chen"},
    {"username": "manager",     "password": "Manager@2026",  "role": "branch_manager",     "full_name": "David Kim"},
    {"username": "loanofficer", "password": "Loan@2026",     "role": "loan_officer",       "full_name": "James Wilson"},
    {"username": "underwriter", "password": "Under@2026",    "role": "underwriter",        "full_name": "Emily Park"},
    {"username": "analyst",     "password": "Analyst@2026",  "role": "fraud_analyst",      "full_name": "Marcus Reid"},
    {"username": "amlanalyst",  "password": "Aml@2026",      "role": "aml_analyst",        "full_name": "Nina Torres"},
    {"username": "kyc",         "password": "Kyc@2026",      "role": "kyc_analyst",        "full_name": "Priya Sharma"},
    {"username": "commercial",  "password": "Comm@2026",     "role": "commercial_banker",  "full_name": "Robert Chen"},
    {"username": "treasury",    "password": "Treasury@2026", "role": "treasury_analyst",   "full_name": "Angela Lee"},
    {"username": "compliance",  "password": "Comply@2026",   "role": "credit_risk_analyst","full_name": "Diana Torres"},
    {"username": "ops",         "password": "Ops@2026",      "role": "operations_specialist","full_name": "Tom Baker"},
]

# ── Crypto ────────────────────────────────────────────────────────────────────
def _hash_pw(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

def _verify_pw(password: str, hashed: str) -> bool:
    return _bcrypt.checkpw(password.encode(), hashed.encode())

bearer_scheme = HTTPBearer(auto_error=False)
router = APIRouter()

def _engine():
    return create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# ── DB helpers ────────────────────────────────────────────────────────────────
def ensure_users_table():
    engine = _engine()
    with engine.connect() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'personal_banker',
            full_name TEXT NOT NULL DEFAULT '',
            email TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            last_login TEXT,
            created_at TEXT NOT NULL
        )"""))
        conn.execute(text("""CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            resource TEXT NOT NULL,
            resource_id TEXT,
            ip_address TEXT,
            timestamp TEXT NOT NULL
        )"""))
        conn.commit()
    for u in DEMO_USERS:
        _create_user_if_missing(u["username"], u["password"], u["role"], u["full_name"])

def _create_user_if_missing(username: str, password: str, role: str, full_name: str):
    engine = _engine()
    with engine.connect() as conn:
        existing = conn.execute(text("SELECT id FROM users WHERE username=:u"), {"u": username}).fetchone()
        if existing:
            return
        conn.execute(text("""INSERT INTO users (username,hashed_password,role,full_name,is_active,created_at)
            VALUES (:u,:h,:r,:fn,1,:ts)"""),
            {"u": username, "h": _hash_pw(password), "r": role, "fn": full_name, "ts": datetime.now().isoformat()})
        conn.commit()
    print(f"  [Auth] Seeded: {username} ({role})")

def _get_user(username: str) -> Optional[dict]:
    engine = _engine()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM users WHERE username=:u AND is_active=1"), {"u": username}).fetchone()
    return dict(row._mapping) if row else None

def _update_last_login(username: str):
    engine = _engine()
    with engine.connect() as conn:
        conn.execute(text("UPDATE users SET last_login=:ts WHERE username=:u"), {"ts": datetime.now().isoformat(), "u": username})
        conn.commit()

def log_audit(username: str, action: str, resource: str, resource_id: str = "", ip: str = ""):
    try:
        engine = _engine()
        with engine.connect() as conn:
            conn.execute(text("""INSERT INTO audit_log (username,action,resource,resource_id,ip_address,timestamp)
                VALUES (:u,:a,:r,:rid,:ip,:ts)"""),
                {"u": username,"a": action,"r": resource,"rid": resource_id,"ip": ip,"ts": datetime.now().isoformat()})
            conn.commit()
    except Exception:
        pass

# ── Token helpers ─────────────────────────────────────────────────────────────
def _create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload["iat"] = datetime.utcnow()
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def _decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

# ── FastAPI auth dependency ───────────────────────────────────────────────────
class CurrentUser(BaseModel):
    username: str
    role: str
    full_name: str
    permissions: List[str]
    nav_sections: List[str]

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = _decode_token(credentials.credentials)
        username: str = payload.get("sub", "")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = _get_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    role_def = ROLES.get(user["role"], {})
    return CurrentUser(
        username=user["username"],
        role=user["role"],
        full_name=user["full_name"],
        permissions=role_def.get("permissions", []),
        nav_sections=role_def.get("nav_sections", []),
    )

def require_permission(permission: str):
    def _dep(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        perms = current_user.permissions
        if "*" in perms or permission in perms:
            return current_user
        # Check wildcard prefix (e.g. "chat:all" covers "chat:query")
        prefix = permission.split(":")[0]
        if f"{prefix}:all" in perms or f"{prefix}:*" in perms:
            return current_user
        raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
    return _dep

def require_role(*roles: str):
    def _dep(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in roles and "*" not in current_user.permissions:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return current_user
    return _dep

# ── Auth routes ───────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
async def login(req: LoginRequest, request: Request):
    user = _get_user(req.username)
    if not user or not _verify_pw(req.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    _update_last_login(req.username)
    log_audit(req.username, "login", "auth", ip=request.client.host if request.client else "")
    role_def = ROLES.get(user["role"], {})
    token = _create_access_token({"sub": user["username"], "role": user["role"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
            "role_label": role_def.get("label", user["role"]),
            "permissions": role_def.get("permissions", []),
            "nav_sections": role_def.get("nav_sections", []),
        }
    }

@router.post("/logout")
async def logout(current_user: CurrentUser = Depends(get_current_user)):
    return {"message": "Logged out"}

@router.get("/me")
async def me(current_user: CurrentUser = Depends(get_current_user)):
    role_def = ROLES.get(current_user.role, {})
    return {
        "username": current_user.username,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "role_label": role_def.get("label", current_user.role),
        "permissions": current_user.permissions,
        "nav_sections": current_user.nav_sections,
    }

@router.get("/roles")
async def list_roles(current_user: CurrentUser = Depends(get_current_user)):
    return {"roles": [{"id": k, "label": v["label"]} for k, v in ROLES.items()]}
