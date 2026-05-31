"""
auth.py — Authentication and Authorization utilities including password hashing,
JWT token creation, and FastAPI dependency checks for role-based access control (RBAC).

Note: Uses bcrypt directly instead of passlib to ensure compatibility with bcrypt >= 4.x
(passlib 1.7.4 is abandoned and incompatible with modern bcrypt versions).
"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status, Header
import jwt
import bcrypt
from backend.database import get_db

# Configuration
SECRET_KEY = "SECRET_KEY_FOR_WEB_ANTI_CHEAT_WEBCAM_DETECTION_SYSTEM"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 360  # 6 hours


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against its bcrypt hash."""
    try:
        plain_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8") if isinstance(hashed_password, str) else hashed_password
        return bcrypt.checkpw(plain_bytes, hashed_bytes)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generates a bcrypt hash of a plain password."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generates a JWT access token containing the payload."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(authorization: Optional[str] = Header(None), db = Depends(get_db)) -> dict:
    """
    FastAPI dependency to extract and authenticate the current user from the Authorization header.
    Supports both 'Bearer <token>' format and raw token strings.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token xác thực bị thiếu. Vui lòng đăng nhập lại.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Mã token không hợp lệ.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên làm việc đã hết hạn. Vui lòng đăng nhập lại.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mã xác thực không hợp lệ.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    user = await db.get_user_by_username(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Không tìm thấy người dùng.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(allowed_roles: list[str]):
    """
    FastAPI dependency factory to restrict endpoint access to specific roles.
    Example: Depends(require_role(["admin", "teacher"]))
    """
    def role_dependency(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền thực hiện hành động này."
               )
        return current_user
    return role_dependency
