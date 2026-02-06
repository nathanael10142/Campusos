"""
Google OAuth authentication routes
"""

from fastapi import APIRouter, HTTPException, status, Request, Depends
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from app.models.oauth import (
    GoogleOAuthStart,
    GoogleOAuthCallback,
    GoogleOAuthComplete,
    GoogleUserInfo,
    OAuthStateData
)
from app.models.user import UserResponse, TokenResponse, UserRole, UserStatus
from app.core.config import settings
from app.core.database import get_db_session
from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_device_id,
    encrypt_device_id,
    create_short_lived_token,
    decode_token
)
from datetime import datetime
from loguru import logger
import secrets
import time

router = APIRouter()

# Initialize OAuth
oauth = OAuth()

if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
    oauth.register(
        name='google',
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': ' '.join(settings.GOOGLE_OAUTH_SCOPES)
        }
    )


@router.get("/google/login")
async def google_login(request: Request, redirect_uri: str = None):
    """
    Initiate Google OAuth flow
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth n'est pas configuré. Contactez l'administrateur."
        )
    
    # Create state with nonce for security
    state_data = OAuthStateData(
        timestamp=time.time(),
        nonce=secrets.token_urlsafe(32),
        redirect_uri=redirect_uri
    )
    
    # Encode state as JWT for security
    state = create_short_lived_token(state_data.dict(), seconds=600)  # 10 minutes
    
    # Determine redirect URI
    callback_uri = redirect_uri or settings.GOOGLE_REDIRECT_URI or str(request.url_for('google_callback'))
    
    # Redirect to Google OAuth
    redirect_url = await oauth.google.authorize_redirect(request, callback_uri, state=state)
    
    logger.info(f"🔐 Initiating Google OAuth login with redirect: {callback_uri}")
    
    return redirect_url


@router.get("/google/callback")
async def google_callback(request: Request, db_session = Depends(get_db_session)):
    """
    Handle Google OAuth callback
    """
    from app.core.db_wrapper import DatabaseWrapper
    db = DatabaseWrapper(db_session)
    
    try:
        # Get authorization token from Google
        token = await oauth.google.authorize_access_token(request)
        
        # Verify state to prevent CSRF
        state = request.query_params.get('state')
        if state:
            state_data = decode_token(state)
            if not state_data or (time.time() - state_data.get('timestamp', 0)) > 600:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Session expirée. Veuillez recommencer."
                )
        
        # Get user info from Google
        user_info = token.get('userinfo')
        if not user_info:
            user_info = await oauth.google.userinfo(token=token)
        
        google_user = GoogleUserInfo(**user_info)
        
        logger.info(f"✅ Google OAuth successful for: {google_user.email}")
        
        # Check if user exists by Google ID or email
        existing_user = db.select("users", filters={"google_id": google_user.id})
        
        if not existing_user:
            # Try to find by email
            existing_user = db.select("users", filters={"email": google_user.email})
        
        if existing_user:
            # User exists - log them in
            user = existing_user[0]
            
            # Update Google ID if not set
            if not user.get("google_id"):
                db.update("users", {"google_id": google_user.id}, filters={"id": user["id"]})
            
            # Update avatar from Google if not set
            if not user.get("avatar_url") and google_user.picture:
                db.update("users", {"avatar_url": google_user.picture}, filters={"id": user["id"]})
            
            # Update device and last login
            user_agent = request.headers.get("user-agent", "unknown")
            ip_address = request.client.host
            device_id = generate_device_id(user_agent, ip_address)
            encrypted_device_id = encrypt_device_id(device_id)
            
            db.update("users", {
                "device_id": encrypted_device_id,
                "last_login": datetime.utcnow().isoformat()
            }, filters={"id": user["id"]})
            
            # Create tokens
            token_data = {"sub": str(user["id"]), "email": user["email"], "role": user["role"]}
            access_token = create_access_token(token_data)
            refresh_token = create_refresh_token(token_data)
            
            # Create user response
            user_response = UserResponse(
                id=str(user["id"]),
                email=user["email"],
                full_name=user["full_name"],
                phone=user["phone"],
                faculty=user["faculty"],
                academic_level=user["academic_level"],
                student_id=user.get("student_id"),
                role=user["role"],
                status=user["status"],
                batera_coins=user["batera_coins"],
                avatar_url=user.get("avatar_url"),
                created_at=user["created_at"],
                last_login=user.get("last_login")
            )
            
            logger.info(f"✅ User logged in via Google: {user['email']}")
            
            return TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                user=user_response
            )
        
        else:
            # New user - need additional information
            # Create a temporary token for completing registration
            temp_token_data = {
                "google_id": google_user.id,
                "email": google_user.email,
                "name": google_user.name,
                "picture": google_user.picture,
                "type": "google_registration"
            }
            temp_token = create_short_lived_token(temp_token_data, seconds=1800)  # 30 minutes
            
            logger.info(f"🆕 New Google user needs to complete registration: {google_user.email}")
            
            return {
                "status": "needs_completion",
                "message": "Veuillez compléter votre inscription",
                "google_token": temp_token,
                "user_info": {
                    "email": google_user.email,
                    "name": google_user.name,
                    "picture": google_user.picture
                }
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google OAuth callback error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de l'authentification Google. Nathanael a été notifié."
        )


@router.post("/google/complete", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def complete_google_registration(
    completion_data: GoogleOAuthComplete,
    request: Request,
    db_session = Depends(get_db_session)
):
    """
    Complete Google OAuth registration with additional information
    """
    from app.core.db_wrapper import DatabaseWrapper
    db = DatabaseWrapper(db_session)
    
    try:
        # Decode and verify temporary token
        token_payload = decode_token(completion_data.google_token)
        
        if not token_payload or token_payload.get("type") != "google_registration":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token invalide ou expiré. Veuillez recommencer l'authentification Google."
            )
        
        google_id = token_payload.get("google_id")
        email = token_payload.get("email")
        name = token_payload.get("name")
        picture = token_payload.get("picture")
        
        # Check if user already exists (shouldn't happen, but safety check)
        existing_user = db.select("users", filters={"email": email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Un compte existe déjà avec cet email."
            )
        
        # Generate device ID
        user_agent = request.headers.get("user-agent", "unknown")
        ip_address = request.client.host
        device_id = generate_device_id(user_agent, ip_address)
        encrypted_device_id = encrypt_device_id(device_id)
        
        # Create user with Google OAuth data
        user_insert = {
            "google_id": google_id,
            "email": email,
            "password_hash": None,  # No password for Google OAuth users
            "full_name": name,
            "phone": completion_data.phone,
            "faculty": completion_data.faculty.value,
            "academic_level": completion_data.academic_level.value,
            "student_id": completion_data.student_id,
            "role": UserRole.STUDENT.value,
            "status": UserStatus.ACTIVE.value,
            "batera_coins": 10.0,  # Bonus for Google sign-up
            "avatar_url": picture,
            "device_id": encrypted_device_id,
            "created_at": datetime.utcnow().isoformat(),
            "last_login": datetime.utcnow().isoformat()
        }
        
        created_user = db.insert("users", user_insert)
        
        if not created_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la création du compte. Nathanael a été notifié."
            )
        
        # Create tokens
        token_data = {"sub": str(created_user["id"]), "email": created_user["email"], "role": created_user["role"]}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        # Create user response
        user_response = UserResponse(
            id=str(created_user["id"]),
            email=created_user["email"],
            full_name=created_user["full_name"],
            phone=created_user["phone"],
            faculty=created_user["faculty"],
            academic_level=created_user["academic_level"],
            student_id=created_user.get("student_id"),
            role=created_user["role"],
            status=created_user["status"],
            batera_coins=created_user["batera_coins"],
            avatar_url=created_user.get("avatar_url"),
            created_at=created_user["created_at"],
            last_login=created_user.get("last_login")
        )
        
        logger.info(f"✅ New user registered via Google: {email}")
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_response
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google registration completion error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la finalisation de l'inscription. Nathanael a été notifié."
        )
