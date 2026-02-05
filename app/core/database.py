"""
Database connection and utilities
Supports both Supabase (cloud) and local PostgreSQL (development)
"""

from supabase import create_client, Client
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings
from app.core.db_wrapper import DatabaseWrapper
from loguru import logger

# Database instances
supabase: Client = None
engine = None
SessionLocal = None


async def init_db():
    """Initialize database connection"""
    global supabase, engine, SessionLocal
    
    try:
        # Check if using local PostgreSQL
        if settings.DATABASE_URL and "postgresql" in settings.DATABASE_URL:
            logger.info("🔄 Using local PostgreSQL database")
            
            # Create SQLAlchemy engine
            engine = create_engine(
                settings.DATABASE_URL,
                echo=settings.DEBUG,
                future=True
            )
            
            # Create session factory
            SessionLocal = sessionmaker(
                autocommit=False, 
                autoflush=False, 
                bind=engine
            )
            
            logger.info("✅ Local PostgreSQL connection initialized")
            
        else:
            # Use Supabase
            logger.info("🔄 Using Supabase database")
            supabase = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_KEY
            )
            logger.info("✅ Supabase client initialized")
            
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        raise


def get_db():
    """Get database client wrapped in DatabaseWrapper"""
    if engine:
        # Return wrapped SQLAlchemy session for local DB
        return DatabaseWrapper(SessionLocal())
    else:
        # Return wrapped Supabase client
        return DatabaseWrapper(supabase)


def get_db_session():
    """Get SQLAlchemy session with proper lifecycle management"""
    if not engine:
        raise ValueError("SQLAlchemy not initialized")
    
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
