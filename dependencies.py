"""
Centralized FastAPI Dependency Injection & Security Context.
Provides shared database sessions, user/staff authentication, cache manager, and permissions.
"""

import os
import time
import json
import logging
import secrets
from typing import Optional, Dict, Tuple, Set, Any, List, Union
from pathlib import Path

from fastapi import Request, Depends, HTTPException, status, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
import bcrypt
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from database import SessionLocal
import models
import permissions

logger = logging.getLogger("expiryguard.dependencies")

# Security Configuration
security = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__truncate_error=False)

SECRET_KEY = os.getenv("SECRET_KEY")
KNOWN_SECRET_PLACEHOLDERS = {
    "generate_a_secure_random_64_character_hex_key_here",
    "your_secret_key_here",
    "changeme",
    "secret",
    "replace_me",
    "test_secret_key",
}
if not SECRET_KEY or SECRET_KEY.lower() in KNOWN_SECRET_PLACEHOLDERS or len(SECRET_KEY) < 16:
    SECRET_KEY = secrets.token_hex(32)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7


def safe_hash_password(password: str) -> str:
    """Hashes password safely using direct bcrypt + SHA-256 pre-hashing."""
    if not password:
        password = ""
    import hashlib, base64
    pre_hashed = base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pre_hashed, salt).decode("utf-8")


def safe_verify_password(plain_password: str, hashed_password: str) -> bool:
    """Safely verifies passwords against direct bcrypt, passlib hashes, and legacy plain text."""
    if not plain_password or not hashed_password:
        return False
    import hashlib, base64

    safe_plain = plain_password.strip()
    safe_hashed = hashed_password.strip()

    # 1. Direct bcrypt check on pre-hashed SHA-256 bytes
    try:
        pre_hashed = base64.b64encode(hashlib.sha256(plain_password.encode("utf-8")).digest())
        if bcrypt.checkpw(pre_hashed, safe_hashed.encode("utf-8")):
            return True
    except Exception:
        pass

    # 2. Direct bcrypt check on raw bytes
    try:
        raw_bytes = plain_password.encode("utf-8")[:72]
        if bcrypt.checkpw(raw_bytes, safe_hashed.encode("utf-8")):
            return True
    except Exception:
        pass

    # 3. Passlib verify fallback
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        if pwd_context.verify(pwd_bytes.decode("utf-8", "ignore"), safe_hashed):
            return True
    except Exception:
        pass

    # 4. Legacy plain-text fallback
    try:
        if safe_plain == safe_hashed:
            return True
    except Exception:
        pass

    return False


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class AuthenticatedUser:
    """
    Unified user representation for both Pharmacy Owners and Staff Members.
    """
    def __init__(
        self,
        db_user: models.User,
        staff: Optional[models.StaffMember] = None,
        custom_permissions: Optional[Set[str]] = None,
    ):
        self._user = db_user
        self._staff = staff

        self.id = db_user.id
        self.user_id = db_user.id
        self.shop_id = db_user.id
        self.owner_id = db_user.id

        if staff:
            self.staff_id = staff.id
            self.name = staff.name
            self.email = staff.email or db_user.email
            self.phone = staff.phone or db_user.phone
            self.role = permissions.normalize_role(staff.role)
            self.is_owner = False
            self.permissions = custom_permissions or permissions.get_role_permissions(self.role, staff.permissions_json)
        else:
            self.staff_id = None
            self.name = db_user.owner_name
            self.email = db_user.email
            self.phone = db_user.phone
            self.role = permissions.ROLE_OWNER
            self.is_owner = True
            self.permissions = permissions.ROLE_DEFAULT_PERMISSIONS[permissions.ROLE_OWNER]

        self.shop_name = db_user.shop_name
        self.owner_name = db_user.owner_name
        self.address = db_user.address
        self.gstin = db_user.gstin
        self.gst_number = db_user.gst_number
        self.default_gst_percentage = db_user.default_gst_percentage

    def has_permission(self, perm: str) -> bool:
        if self.is_owner or "*" in self.permissions:
            return True
        return perm in self.permissions

    def __getattr__(self, name: str):
        return getattr(self._user, name)


_AUTH_CACHE: Dict[str, Tuple[AuthenticatedUser, float]] = {}

def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
    token_param: Optional[str] = Query(None, alias="token"),
) -> AuthenticatedUser:
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif request.cookies.get("access_token"):
        token = request.cookies.get("access_token")
    elif token_param:
        token = token_param

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a Bearer token or login to establish a session.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        staff_id = payload.get("staff_id")

        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")

        cache_key = f"u:{user_id}:s:{staff_id or 'none'}"
        now = time.time()
        if cache_key in _AUTH_CACHE:
            cached_auth, timestamp = _AUTH_CACHE[cache_key]
            if now - timestamp < 30:
                return cached_auth

        db_user = db.query(models.User).filter(models.User.id == user_id).first()
        if db_user is None:
            raise HTTPException(status_code=401, detail="Pharmacy account not found")

        staff = None
        if staff_id is not None:
            staff = db.query(models.StaffMember).filter(
                models.StaffMember.id == staff_id,
                models.StaffMember.user_id == user_id,
            ).first()
            if staff is None:
                raise HTTPException(status_code=401, detail="Staff account not found or removed")
            if (staff.status or "ACTIVE").upper() != "ACTIVE":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Staff account is disabled. Please contact your pharmacy administrator.",
                )

        auth_user = AuthenticatedUser(db_user=db_user, staff=staff)
        _AUTH_CACHE[cache_key] = (auth_user, now)
        return auth_user

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_permission(perm: Union[str, List[str], Set[str], Tuple[str, ...]]):
    def _permission_checker(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if isinstance(perm, (list, tuple, set)):
            allowed = any(current_user.has_permission(p) for p in perm)
        else:
            allowed = current_user.has_permission(perm)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You do not have permission to perform this action.",
            )
        return current_user
    return _permission_checker


class FastCacheManager:
    """
    High-performance in-memory TTL caching engine with per-user isolation and tag-based invalidation.
    """
    def __init__(self):
        self._cache: Dict[str, Tuple[float, Any, Set[str]]] = {}
        self._user_keys: Dict[int, Set[str]] = {}

    def _resolve_key(self, arg1: Any, arg2: Optional[Any] = None) -> Tuple[str, Optional[int]]:
        if arg2 is not None:
            return f"u:{arg1}:{arg2}", int(arg1) if isinstance(arg1, (int, str)) and str(arg1).isdigit() else None
        return str(arg1), None

    def get(self, arg1: Any, arg2: Optional[Any] = None) -> Optional[Any]:
        key, _ = self._resolve_key(arg1, arg2)
        entry = self._cache.get(key)
        if not entry:
            return None
        expire_time, data, _ = entry
        if time.time() > expire_time:
            self._cache.pop(key, None)
            return None
        return data

    def set(
        self,
        arg1: Any,
        arg2: Any = None,
        data: Any = None,
        ttl: Union[int, float] = 15,
        ttl_seconds: Optional[Union[int, float]] = None,
        user_id: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ):
        effective_ttl = ttl_seconds if ttl_seconds is not None else ttl
        if data is not None:
            u_id = int(arg1) if isinstance(arg1, (int, str)) and str(arg1).isdigit() else None
            key = f"u:{arg1}:{arg2}"
            actual_data = data
            effective_user_id = u_id or user_id
        else:
            key = str(arg1)
            actual_data = arg2
            effective_user_id = user_id

        tag_set = set(tags or [])
        if effective_user_id:
            tag_set.add(f"user_{effective_user_id}")
            if effective_user_id not in self._user_keys:
                self._user_keys[effective_user_id] = set()
            self._user_keys[effective_user_id].add(key)

        self._cache[key] = (time.time() + float(effective_ttl), actual_data, tag_set)

    def invalidate_tag(self, user_id: int, tag: str):
        self.invalidate_user(user_id, tag)

    def invalidate_user(self, user_id: int, tag: Optional[str] = None):
        keys_to_remove = set()
        user_tag = f"user_{user_id}"
        for k, (exp, data, tags) in list(self._cache.items()):
            if user_tag in tags or k.startswith(f"u:{user_id}:"):
                if tag is None or tag in tags:
                    keys_to_remove.add(k)
        for k in keys_to_remove:
            self._cache.pop(k, None)
        if tag is None and user_id in self._user_keys:
            self._user_keys.pop(user_id, None)

    def invalidate_tags(self, tags: List[str]):
        keys_to_remove = set()
        for k, (exp, data, entry_tags) in list(self._cache.items()):
            if any(t in entry_tags for t in tags):
                keys_to_remove.add(k)
        for k in keys_to_remove:
            self._cache.pop(k, None)


fast_cache = FastCacheManager()

# SlowAPI Limiter instance
redis_storage_uri = "memory://"
redis_url_env = os.getenv("REDIS_URL")
if redis_url_env:
    try:
        import redis
        r_client = redis.Redis.from_url(redis_url_env, socket_timeout=0.5, socket_connect_timeout=0.5)
        r_client.ping()
        redis_storage_uri = redis_url_env
    except Exception:
        redis_storage_uri = "memory://"

limiter = Limiter(key_func=get_remote_address, storage_uri=redis_storage_uri)
