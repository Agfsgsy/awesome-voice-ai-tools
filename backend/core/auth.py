"""نظام المصادقة والأمان - JWT, API Keys, Password Hashing, Roles, Permissions"""

import os
import secrets
import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from enum import Enum
from pathlib import Path

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.core.logger import get_logger

logger = get_logger("auth")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# JWT settings from environment
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# API Key settings
API_KEY_HEADER = "X-API-Key"
API_KEY_MIN_LENGTH = 32

# Default admin credentials from environment (change in production!)
DEFAULT_ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


def _ensure_jwt_secret() -> str:
    """Ensure JWT secret key is set - generate if empty (dev only warning)"""
    global JWT_SECRET_KEY
    if not JWT_SECRET_KEY:
        JWT_SECRET_KEY = secrets.token_urlsafe(64)
        logger.warning(
            "JWT_SECRET_KEY not set in environment! Generated temporary key. "
            "Set a strong JWT_SECRET_KEY in production!"
        )
    return JWT_SECRET_KEY


# ---------------------------------------------------------------------------
# Password Hashing
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters")
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    if not plain_password or not hashed_password:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Roles & Permissions
# ---------------------------------------------------------------------------

class Role(str, Enum):
    ADMIN = "admin"
    USER = "user"
    API = "api"


class Permission(str, Enum):
    TTS_GENERATE = "tts:generate"
    TTS_CLONE = "tts:clone"
    UPLOAD_FILES = "upload:files"
    MANAGE_MODELS = "manage:models"
    MANAGE_PLUGINS = "manage:plugins"
    VIEW_LOGS = "view:logs"
    VIEW_SETTINGS = "view:settings"
    EDIT_SETTINGS = "edit:settings"
    MANAGE_USERS = "manage:users"
    VIEW_SYSTEM = "view:system"


# Role-based permission matrix
ROLE_PERMISSIONS: Dict[Role, List[Permission]] = {
    Role.ADMIN: [
        Permission.TTS_GENERATE,
        Permission.TTS_CLONE,
        Permission.UPLOAD_FILES,
        Permission.MANAGE_MODELS,
        Permission.MANAGE_PLUGINS,
        Permission.VIEW_LOGS,
        Permission.VIEW_SETTINGS,
        Permission.EDIT_SETTINGS,
        Permission.MANAGE_USERS,
        Permission.VIEW_SYSTEM,
    ],
    Role.USER: [
        Permission.TTS_GENERATE,
        Permission.TTS_CLONE,
        Permission.UPLOAD_FILES,
        Permission.VIEW_SETTINGS,
    ],
    Role.API: [
        Permission.TTS_GENERATE,
        Permission.TTS_CLONE,
        Permission.UPLOAD_FILES,
    ],
}


def has_permission(role: Role, permission: Permission) -> bool:
    """Check if a role has a specific permission"""
    permissions = ROLE_PERMISSIONS.get(role, [])
    return permission in permissions


def get_role_permissions(role: Role) -> List[Permission]:
    """Get all permissions for a role"""
    return ROLE_PERMISSIONS.get(role, [])


# ---------------------------------------------------------------------------
# JWT Tokens
# ---------------------------------------------------------------------------

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "access"})
    secret = _ensure_jwt_secret()
    return jwt.encode(to_encode, secret, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create a JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "refresh"})
    secret = _ensure_jwt_secret()
    return jwt.encode(to_encode, secret, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT token"""
    secret = _ensure_jwt_secret()
    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
        if payload.get("exp") and datetime.fromtimestamp(payload["exp"], tz=timezone.utc) < datetime.now(timezone.utc):
            return None
        return payload
    except JWTError:
        return None
    except Exception as e:
        logger.error(f"Token decode error: {e}")
        return None


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

# In-memory API key store (in production, use database)
# Format: {api_key: {user_id, role, name, created_at, last_used, request_count}}
_api_keys: Dict[str, Dict[str, Any]] = {}


def generate_api_key() -> str:
    """Generate a secure API key"""
    return "vai_" + secrets.token_urlsafe(48)


def create_api_key(user_id: str, role: Role = Role.API, name: str = "") -> str:
    """Create a new API key for a user"""
    api_key = generate_api_key()
    _api_keys[api_key] = {
        "user_id": user_id,
        "role": role.value,
        "name": name or f"API Key {len(_api_keys) + 1}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_used": None,
        "request_count": 0,
        "active": True,
    }
    logger.info(f"Created API key for user: {user_id}")
    return api_key


def validate_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """Validate an API key and return user info"""
    if not api_key or not api_key.startswith("vai_"):
        return None
    key_data = _api_keys.get(api_key)
    if not key_data or not key_data.get("active"):
        return None
    key_data["last_used"] = datetime.now(timezone.utc).isoformat()
    key_data["request_count"] = key_data.get("request_count", 0) + 1
    return key_data


def revoke_api_key(api_key: str) -> bool:
    """Revoke an API key"""
    if api_key in _api_keys:
        _api_keys[api_key]["active"] = False
        logger.info(f"Revoked API key")
        return True
    return False


def list_api_keys(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List API keys (optionally filtered by user)"""
    results = []
    for key, data in _api_keys.items():
        if user_id is None or data.get("user_id") == user_id:
            results.append({
                "key_preview": key[:12] + "...",
                "name": data.get("name"),
                "role": data.get("role"),
                "created_at": data.get("created_at"),
                "last_used": data.get("last_used"),
                "request_count": data.get("request_count"),
                "active": data.get("active"),
            })
    return results


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------

# In-memory user store (in production, use database)
# Format: {username: {password_hash, role, user_id, created_at, disabled}}
_users: Dict[str, Dict[str, Any]] = {}


def _initialize_default_admin():
    """Initialize default admin user if configured"""
    global _users
    if DEFAULT_ADMIN_USERNAME and DEFAULT_ADMIN_PASSWORD and DEFAULT_ADMIN_USERNAME not in _users:
        try:
            _users[DEFAULT_ADMIN_USERNAME] = {
                "user_id": "admin_" + secrets.token_hex(8),
                "password_hash": hash_password(DEFAULT_ADMIN_PASSWORD),
                "role": Role.ADMIN.value,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "disabled": False,
            }
            logger.info(f"Created default admin user: {DEFAULT_ADMIN_USERNAME}")
        except Exception as e:
            logger.error(f"Failed to create default admin: {e}")


# Initialize on module load
_initialize_default_admin()


def create_user(username: str, password: str, role: Role = Role.USER) -> Dict[str, Any]:
    """Create a new user"""
    if not username or len(username) < 3:
        raise ValueError("Username must be at least 3 characters")
    if username in _users:
        raise ValueError(f"User '{username}' already exists")

    user_id = "user_" + secrets.token_hex(8)
    _users[username] = {
        "user_id": user_id,
        "password_hash": hash_password(password),
        "role": role.value,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "disabled": False,
    }
    logger.info(f"Created user: {username} with role: {role.value}")
    return {"username": username, "user_id": user_id, "role": role.value}


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate a user and return user info if successful"""
    user = _users.get(username)
    if not user:
        return None
    if user.get("disabled"):
        return None
    if not verify_password(password, user.get("password_hash", "")):
        return None
    return {
        "username": username,
        "user_id": user["user_id"],
        "role": user["role"],
    }


def get_user(username: str) -> Optional[Dict[str, Any]]:
    """Get user info by username"""
    user = _users.get(username)
    if not user:
        return None
    return {
        "username": username,
        "user_id": user["user_id"],
        "role": user["role"],
        "disabled": user.get("disabled", False),
        "created_at": user.get("created_at"),
    }


def list_users() -> List[Dict[str, Any]]:
    """List all users"""
    return [
        {
            "username": username,
            "user_id": data["user_id"],
            "role": data["role"],
            "disabled": data.get("disabled", False),
            "created_at": data.get("created_at"),
        }
        for username, data in _users.items()
    ]


def disable_user(username: str) -> bool:
    """Disable a user account"""
    if username in _users:
        _users[username]["disabled"] = True
        logger.info(f"Disabled user: {username}")
        return True
    return False


def enable_user(username: str) -> bool:
    """Enable a user account"""
    if username in _users:
        _users[username]["disabled"] = False
        logger.info(f"Enabled user: {username}")
        return True
    return False


# ---------------------------------------------------------------------------
# Request Authentication Helpers
# ---------------------------------------------------------------------------

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security_bearer = HTTPBearer(auto_error=False)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security_bearer)) -> Dict[str, Any]:
    """Get current user from JWT token in Authorization header"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user(username)
    if not user or user.get("disabled"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(current_user: Dict[str, Any] = Security(get_current_user)) -> Dict[str, Any]:
    """Get current active user"""
    if current_user.get("disabled"):
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def require_permission(permission: Permission):
    """Dependency factory to require a specific permission"""
    async def _check_permission(current_user: Dict[str, Any] = Security(get_current_user)) -> Dict[str, Any]:
        role = Role(current_user.get("role", "user"))
        if not has_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value}",
            )
        return current_user
    return _check_permission


async def require_admin(current_user: Dict[str, Any] = Security(get_current_user)) -> Dict[str, Any]:
    """Require admin role"""
    role = Role(current_user.get("role", "user"))
    if role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def get_current_user_or_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security_bearer),
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Authenticate via JWT token or API key"""
    # Try API key first (from header)
    if not api_key:
        # Could be passed in a different way; handled at route level
        pass

    # Try JWT token
    if credentials:
        token = credentials.credentials
        payload = decode_token(token)
        if payload:
            username = payload.get("sub")
            if username:
                user = get_user(username)
                if user and not user.get("disabled"):
                    return user

    # Try API key authentication
    if api_key:
        key_data = validate_api_key(api_key)
        if key_data:
            return {
                "username": key_data["user_id"],
                "user_id": key_data["user_id"],
                "role": key_data["role"],
            }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Valid authentication required (JWT token or API key)",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ---------------------------------------------------------------------------
# Secure Random Utilities
# ---------------------------------------------------------------------------

def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token"""
    return secrets.token_urlsafe(length)


def constant_time_compare(val1: str, val2: str) -> bool:
    """Constant-time string comparison to prevent timing attacks"""
    return hmac.compare_digest(val1.encode(), val2.encode())
