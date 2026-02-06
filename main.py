"""
CAMPUS OS UNIGOM - Backend API
Développé par Nathanael Batera Akilimali
Version 15.0.0
"""

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import time
from loguru import logger

from app.core.config import settings
from app.core.database import init_db
from app.api.routes import auth, users, ai, courses, payments, admin, notifications, oauth

# Import new routes
try:
    from app.api.routes import radar, chat, messaging, contacts, upload, notifications_fcm
    HAS_RADAR = True
    HAS_CHAT = True
    HAS_MESSAGING = True
    HAS_CONTACTS = True
    HAS_UPLOAD = True
    HAS_FCM = True
except ImportError as e:
    logger.warning(f"Some optional routes not available: {e}")
    HAS_RADAR = False
    HAS_CHAT = False
    HAS_MESSAGING = False
    HAS_CONTACTS = False
    HAS_UPLOAD = False
    HAS_FCM = False

# Configure logger
logger.add(
    "logs/campus_os_{time}.log",
    rotation="500 MB",
    retention="10 days",
    level="INFO"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("🚀 Campus OS UNIGOM Backend starting...")
    
    # Initialize database connection
    await init_db()
    logger.info("✅ Database connected")
    
    yield
    
    logger.info("👋 Campus OS UNIGOM Backend shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Campus OS UNIGOM API",
    description="L'Intelligence Batera pour l'Université de Goma",
    version="15.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# CORS Middleware - allow all localhost ports during development for Flutter web dev
cors_origins = settings.CORS_ORIGINS
if settings.DEBUG:
    # In development, allow any localhost port (for Flutter web dev server, etc.)
    cors_origins = list(cors_origins) + [
        "http://localhost:58785",
        "http://localhost:58786",
        "http://localhost:58787",
        "http://localhost:5000",
        "http://localhost:5001",
        "http://127.0.0.1:58785",
        "http://127.0.0.1:58786",
        "http://127.0.0.1:5000",
    ]
    logger.info(f"✅ CORS Origins (DEBUG): {cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Powered-By"] = "Batera Intelligence System v15"
    return response


# Custom exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": "Erreur de validation des données",
            "details": exc.errors(),
            "message": "Le moteur Batera a détecté une erreur dans votre requête. Nathanael a été notifié."
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "Erreur interne du serveur",
            "message": "Erreur de calcul dans le noyau Batera v15. Nathanael a été notifié."
        }
    )


# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Bienvenue sur Campus OS UNIGOM API",
        "version": "15.0.0",
        "developer": "Nathanael Batera Akilimali",
        "status": "operational",
        "powered_by": "Batera Intelligence System",
        "location": "Goma, RDC"
    }


# Health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "15.0.0",
        "environment": settings.ENVIRONMENT
    }


# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(oauth.router, prefix="/api/v1/oauth", tags=["OAuth Authentication"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["Batera AI"])
app.include_router(courses.router, prefix="/api/v1/courses", tags=["Courses"])
app.include_router(payments.router, prefix="/api/v1/payments", tags=["Payments"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin Panel"])
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["Notifications"])

# Include new routers if available
if HAS_RADAR:
    app.include_router(radar.router, prefix="/api/v1/radar", tags=["Radar Alerts"])
if HAS_CHAT:
    app.include_router(chat.router, prefix="/api/v1/chats", tags=["AI Chat Sessions"])
if HAS_MESSAGING:
    app.include_router(messaging.router, prefix="/api/v1/messaging", tags=["WhatsApp-Level Messaging"])
if HAS_CONTACTS:
    app.include_router(contacts.router, prefix="/api/v1/contacts", tags=["Contacts & User Discovery"])
if HAS_UPLOAD:
    app.include_router(upload.router, prefix="/api/v1/upload", tags=["File Upload"])
if HAS_FCM:
    app.include_router(notifications_fcm.router, prefix="/api/v1/fcm", tags=["Push Notifications"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
