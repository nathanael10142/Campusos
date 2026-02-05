"""
Authentication routes
"""

from fastapi import APIRouter, HTTPException, status, Header, Request, Depends
from app.models.user import UserCreate, UserLogin, TokenResponse, UserResponse, UserRole, UserStatus
from app.core.database import get_db_session
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    generate_device_id,
    encrypt_device_id
)
from datetime import datetime
from loguru import logger

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, request: Request, db_session = Depends(get_db_session)):
    """
    Inscription d'un nouvel étudiant
    """
    from app.core.db_wrapper import DatabaseWrapper
    db = DatabaseWrapper(db_session)
    
    try:
        # Check if email exists
        existing_user = db.select("users", filters={"email": user_data.email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cet email est déjà utilisé. Le système Batera a détecté un doublon."
            )
        
        # Generate device ID
        user_agent = request.headers.get("user-agent", "unknown")
        ip_address = request.client.host
        device_id = generate_device_id(user_agent, ip_address)
        encrypted_device_id = encrypt_device_id(device_id)
        
        # Create user
        hashed_password = get_password_hash(user_data.password)
        
        user_insert = {
            "email": user_data.email,
            "password_hash": hashed_password,
            "full_name": user_data.full_name,
            "phone": user_data.phone,
            "faculty": user_data.faculty.value,
            "academic_level": user_data.academic_level.value,
            "student_id": user_data.student_id,
            "role": UserRole.STUDENT.value,
            "status": UserStatus.ACTIVE.value,
            "batera_coins": 5.0,  # Welcome bonus
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
        
        logger.info(f"✅ New user registered: {user_data.email}")
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur de calcul dans le noyau Batera v15. Nathanael a été notifié."
        )


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, request: Request, db_session = Depends(get_db_session)):
    """
    Connexion d'un utilisateur
    """
    from app.core.db_wrapper import DatabaseWrapper
    db = DatabaseWrapper(db_session)
    
    try:
        # Get user
        users = db.select("users", filters={"email": credentials.email})
        
        if not users:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email ou mot de passe incorrect. Le système Batera n'a pas reconnu vos identifiants."
            )
        
        user = users[0]
        
        # Check password
        if not verify_password(credentials.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email ou mot de passe incorrect. Le système Batera n'a pas reconnu vos identifiants."
            )
        
        # Check if account is active
        if user["status"] != UserStatus.ACTIVE.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Votre compte est {user['status']}. Contactez l'administrateur."
            )
        
        # Check device binding
        user_agent = request.headers.get("user-agent", "unknown")
        ip_address = request.client.host
        device_id = generate_device_id(user_agent, ip_address)
        encrypted_device_id = encrypt_device_id(device_id)
        
        if user.get("device_id") and user["device_id"] != encrypted_device_id:
            # Device mismatch - log security event
            logger.warning(f"⚠️ Device mismatch for user {user['email']}")
            # For now, we allow it but log it (can be made stricter)
        
        # Update device ID and last login
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
        
        logger.info(f"✅ User logged in: {user['email']}")
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur de calcul dans le noyau Batera v15. Nathanael a été notifié."
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user(authorization: str = Header(...), db_session = Depends(get_db_session)):
    """
    Obtenir les informations de l'utilisateur connecté
    """
    from app.core.security import decode_token
    from app.core.db_wrapper import DatabaseWrapper
    db = DatabaseWrapper(db_session)
    
    try:
        # Extract token
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Format d'autorisation invalide"
            )
        
        token = authorization.split(" ")[1]
        payload = decode_token(token)
        
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalide ou expiré"
            )
        
        user_id = payload.get("sub")
        
        # Get user from database
        users = db.select("users", filters={"id": user_id})
        
        if not users:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
        user = users[0]
        
        return UserResponse(
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
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get current user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération des informations utilisateur"
        )
