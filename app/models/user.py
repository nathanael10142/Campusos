"""
User models and schemas
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    """User roles"""
    ADMIN = "admin"
    STUDENT = "student"
    PROFESSOR = "professor"


class UserStatus(str, Enum):
    """User account status"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    FROZEN = "frozen"
    PENDING = "pending"


class Faculty(str, Enum):
    """Faculties at UNIGOM"""
    DROIT = "Droit"
    ECONOMIE = "Sciences Économiques"
    GESTION = "Gestion"
    INFORMATIQUE = "Informatique"
    MEDECINE = "Médecine"
    POLYTECHNIQUE = "Polytechnique"
    AGRONOMIE = "Agronomie"
    AUTRE = "Autre"


class AcademicLevel(str, Enum):
    """Academic levels"""
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    M1 = "M1"
    M2 = "M2"


# Request/Response Schemas
class UserCreate(BaseModel):
    """User registration schema"""
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=3, max_length=100)
    phone: str
    faculty: Faculty
    academic_level: AcademicLevel
    student_id: Optional[str] = None


class UserLogin(BaseModel):
    """User login schema"""
    email: EmailStr
    password: str
    device_info: Optional[str] = None


class UserResponse(BaseModel):
    """User response schema"""
    id: str
    email: EmailStr
    full_name: str
    phone: str
    faculty: Faculty
    academic_level: AcademicLevel
    student_id: Optional[str]
    role: UserRole
    status: UserStatus
    batera_coins: float
    avatar_url: Optional[str]
    created_at: datetime
    last_login: Optional[datetime]


class UserUpdate(BaseModel):
    """User update schema"""
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    faculty: Optional[Faculty] = None
    academic_level: Optional[AcademicLevel] = None


class TokenResponse(BaseModel):
    """Authentication token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class PasswordReset(BaseModel):
    """Password reset request"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation"""
    token: str
    new_password: str = Field(..., min_length=8)
