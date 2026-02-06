"""
OAuth models and schemas for Google authentication
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from app.models.user import Faculty, AcademicLevel


class GoogleOAuthStart(BaseModel):
    """Request to start Google OAuth flow"""
    redirect_uri: Optional[str] = None


class GoogleOAuthCallback(BaseModel):
    """Google OAuth callback data"""
    code: str
    state: Optional[str] = None


class GoogleUserInfo(BaseModel):
    """Google user information from OAuth"""
    id: str  # Google user ID
    email: EmailStr
    verified_email: bool
    name: str
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    picture: Optional[str] = None
    locale: Optional[str] = None


class GoogleOAuthComplete(BaseModel):
    """Complete Google OAuth registration with additional info"""
    google_token: str  # Temporary token from OAuth callback
    phone: str
    faculty: Faculty
    academic_level: AcademicLevel
    student_id: Optional[str] = None


class OAuthStateData(BaseModel):
    """Data stored in OAuth state parameter"""
    timestamp: float
    nonce: str
    redirect_uri: Optional[str] = None
