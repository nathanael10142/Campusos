"""
Security utilities for authentication and encryption
"""

from datetime import datetime, timedelta
from typing import Optional, Dict
from jose import JWTError, jwt
from passlib.context import CryptContext
from cryptography.fernet import Fernet
import hashlib
import secrets
from app.core.config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Device encryption
cipher_suite = Fernet(settings.DEVICE_ENCRYPTION_KEY.encode()[:44] + b'=' * (44 - len(settings.DEVICE_ENCRYPTION_KEY.encode())))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: Dict) -> str:
    """Create JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[Dict]:
    """Decode JWT token"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def generate_device_id(user_agent: str, ip_address: str) -> str:
    """Generate unique device ID"""
    device_string = f"{user_agent}:{ip_address}:{secrets.token_hex(16)}"
    return hashlib.sha256(device_string.encode()).hexdigest()


def encrypt_device_id(device_id: str) -> str:
    """Encrypt device ID"""
    return cipher_suite.encrypt(device_id.encode()).decode()


def decrypt_device_id(encrypted_device_id: str) -> str:
    """Decrypt device ID"""
    return cipher_suite.decrypt(encrypted_device_id.encode()).decode()


def generate_api_key() -> str:
    """Generate random API key"""
    return f"batera_{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str) -> str:
    """Hash API key for storage"""
    return hashlib.sha256(api_key.encode()).hexdigest()


def create_short_lived_token(data: Dict, seconds: int = 60) -> str:
    """Create short-lived token (for anti-scraping)"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(seconds=seconds)
    to_encode.update({"exp": expire, "type": "ephemeral"})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt
