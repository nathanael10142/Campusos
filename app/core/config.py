"""
Configuration settings for Campus OS UNIGOM
"""

from pydantic_settings import BaseSettings
from typing import List, Optional
import os


class Settings(BaseSettings):
    """Application settings"""
    
    # Application
    APP_NAME: str = "Campus OS UNIGOM"
    VERSION: str = "15.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Supabase (Primary Database - Cloud)
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_KEY: str
    
    # Direct Database URL (for local development)
    DATABASE_URL: Optional[str] = None
    
    # Local PostgreSQL (Development/Backup Database)
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_SERVER: Optional[str] = None
    POSTGRES_PORT: Optional[int] = None
    POSTGRES_DB: Optional[str] = None
    
    # Google AI
    GOOGLE_AI_API_KEY: str
    
    # ElevenLabs (Optional)
    ELEVENLABS_API_KEY: str = ""
    
    # Security
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    DEVICE_ENCRYPTION_KEY: str
    
    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""
    GOOGLE_OAUTH_SCOPES: List[str] = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile"
    ]
    
    # Admin
    ADMIN_EMAIL: str = "nathanael@unigom.ac.cd"
    ADMIN_PHONE: str = ""
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000
    
    # AI Configuration
    AI_MAX_TOKENS: int = 2048
    AI_TEMPERATURE: float = 0.7
    AI_TIMEOUT_SECONDS: int = 30
    
    # Batera Coins
    COIN_TO_USD_RATE: float = 0.5
    PAYMENT_PROVIDER: str = "manual"
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://localhost:*",           # Allow all localhost ports (dev)
        "http://127.0.0.1:*",           # Allow all 127.0.0.1 ports (dev)
    ]
    
    # Redis (Optional)
    REDIS_URL: str = "redis://localhost:6379/0"
    ENABLE_REDIS_CACHE: bool = False
    
    # Firebase (for push notifications)
    FIREBASE_SERVICE_ACCOUNT_KEY_PATH: str = ""
    ENABLE_PUSH_NOTIFICATIONS: bool = False
    
    @property
    def postgres_url(self) -> Optional[str]:
        """Build PostgreSQL connection URL for local development"""
        if all([self.POSTGRES_USER, self.POSTGRES_PASSWORD, 
                self.POSTGRES_SERVER, self.POSTGRES_PORT, self.POSTGRES_DB]):
            return (
                f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
                f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        return None
    
    @property
    def database_url(self) -> str:
        """Return active database URL (prefers DATABASE_URL, then Supabase, then local PostgreSQL)"""
        # If DATABASE_URL is explicitly set, use it
        if self.DATABASE_URL:
            return self.DATABASE_URL
        
        # In production, always use Supabase
        if self.ENVIRONMENT == "production":
            return self.SUPABASE_URL
        
        # In development, use local PostgreSQL if configured
        if self.postgres_url and self.ENVIRONMENT == "development":
            return self.postgres_url
        
        # Default to Supabase
        return self.SUPABASE_URL
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "forbid"  # Explicitly forbid extra fields for security


# Create settings instance
settings = Settings()
