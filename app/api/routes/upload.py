"""
File Upload API for Messaging
Campus OS UNIGOM
"""

from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File, Form
from typing import Optional
from datetime import datetime
from uuid import uuid4
import os
import shutil
from pathlib import Path
from app.core.database import get_db
from app.core.security import decode_token
from loguru import logger

router = APIRouter()


# ============================================
# CONFIGURATION
# ============================================

# File upload settings
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
ALLOWED_VIDEO_TYPES = {'video/mp4', 'video/mpeg', 'video/webm', 'video/quicktime'}
ALLOWED_AUDIO_TYPES = {'audio/mpeg', 'audio/ogg', 'audio/wav', 'audio/mp4', 'audio/webm'}
ALLOWED_DOCUMENT_TYPES = {
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'text/plain'
}

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_current_user_id(authorization: str = Header(...)) -> str:
    """Extract user ID from token"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    token = authorization.split(" ")[1]
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return payload.get("sub")


def validate_file_type(content_type: str, allowed_types: set) -> bool:
    """Validate file MIME type"""
    return content_type in allowed_types


def generate_unique_filename(original_filename: str) -> str:
    """Generate unique filename while preserving extension"""
    ext = Path(original_filename).suffix
    unique_name = f"{uuid4()}{ext}"
    return unique_name


def get_file_type_category(content_type: str) -> str:
    """Determine file type category"""
    if content_type in ALLOWED_IMAGE_TYPES:
        return "image"
    elif content_type in ALLOWED_VIDEO_TYPES:
        return "video"
    elif content_type in ALLOWED_AUDIO_TYPES:
        return "audio"
    elif content_type in ALLOWED_DOCUMENT_TYPES:
        return "document"
    else:
        return "file"


# ============================================
# UPLOAD ROUTES
# ============================================

@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None),
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Upload image for messaging"""
    
    try:
        # Validate file type
        if not validate_file_type(file.content_type, ALLOWED_IMAGE_TYPES):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}"
            )
        
        # Check file size
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()  # Get position (file size)
        file.file.seek(0)  # Reset to beginning
        
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Max size: {MAX_FILE_SIZE / (1024 * 1024)}MB"
            )
        
        # Generate unique filename
        unique_filename = generate_unique_filename(file.filename)
        
        # Create subdirectory for images
        image_dir = UPLOAD_DIR / "images" / datetime.utcnow().strftime("%Y%m")
        image_dir.mkdir(parents=True, exist_ok=True)
        
        # Save file
        file_path = image_dir / unique_filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Generate URL (adjust based on your deployment)
        file_url = f"/uploads/images/{datetime.utcnow().strftime('%Y%m')}/{unique_filename}"
        
        # Save metadata to database
        file_metadata = {
            "id": str(uuid4()),
            "user_id": user_id,
            "conversation_id": conversation_id,
            "file_type": "image",
            "original_filename": file.filename,
            "stored_filename": unique_filename,
            "file_path": str(file_path),
            "file_url": file_url,
            "file_size": file_size,
            "mime_type": file.content_type,
            "uploaded_at": datetime.utcnow().isoformat()
        }
        
        db.table("uploaded_files").insert(file_metadata).execute()
        
        return {
            "file_id": file_metadata["id"],
            "file_url": file_url,
            "file_type": "image",
            "filename": file.filename,
            "size": file_size
        }
    
    except Exception as e:
        logger.error(f"Error uploading image: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload image: {str(e)}")


@router.post("/video")
async def upload_video(
    file: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None),
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Upload video for messaging"""
    
    try:
        # Validate file type
        if not validate_file_type(file.content_type, ALLOWED_VIDEO_TYPES):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_VIDEO_TYPES)}"
            )
        
        # Check file size
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Max size: {MAX_FILE_SIZE / (1024 * 1024)}MB"
            )
        
        # Generate unique filename
        unique_filename = generate_unique_filename(file.filename)
        
        # Create subdirectory for videos
        video_dir = UPLOAD_DIR / "videos" / datetime.utcnow().strftime("%Y%m")
        video_dir.mkdir(parents=True, exist_ok=True)
        
        # Save file
        file_path = video_dir / unique_filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Generate URL
        file_url = f"/uploads/videos/{datetime.utcnow().strftime('%Y%m')}/{unique_filename}"
        
        # Save metadata
        file_metadata = {
            "id": str(uuid4()),
            "user_id": user_id,
            "conversation_id": conversation_id,
            "file_type": "video",
            "original_filename": file.filename,
            "stored_filename": unique_filename,
            "file_path": str(file_path),
            "file_url": file_url,
            "file_size": file_size,
            "mime_type": file.content_type,
            "uploaded_at": datetime.utcnow().isoformat()
        }
        
        db.table("uploaded_files").insert(file_metadata).execute()
        
        return {
            "file_id": file_metadata["id"],
            "file_url": file_url,
            "file_type": "video",
            "filename": file.filename,
            "size": file_size
        }
    
    except Exception as e:
        logger.error(f"Error uploading video: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload video: {str(e)}")


@router.post("/audio")
async def upload_audio(
    file: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None),
    is_voice_note: bool = Form(False),
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Upload audio/voice note for messaging"""
    
    try:
        # Validate file type
        if not validate_file_type(file.content_type, ALLOWED_AUDIO_TYPES):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_AUDIO_TYPES)}"
            )
        
        # Check file size
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Max size: {MAX_FILE_SIZE / (1024 * 1024)}MB"
            )
        
        # Generate unique filename
        unique_filename = generate_unique_filename(file.filename)
        
        # Create subdirectory
        subdir = "voice" if is_voice_note else "audio"
        audio_dir = UPLOAD_DIR / subdir / datetime.utcnow().strftime("%Y%m")
        audio_dir.mkdir(parents=True, exist_ok=True)
        
        # Save file
        file_path = audio_dir / unique_filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Generate URL
        file_url = f"/uploads/{subdir}/{datetime.utcnow().strftime('%Y%m')}/{unique_filename}"
        
        # Save metadata
        file_metadata = {
            "id": str(uuid4()),
            "user_id": user_id,
            "conversation_id": conversation_id,
            "file_type": "voice" if is_voice_note else "audio",
            "original_filename": file.filename,
            "stored_filename": unique_filename,
            "file_path": str(file_path),
            "file_url": file_url,
            "file_size": file_size,
            "mime_type": file.content_type,
            "uploaded_at": datetime.utcnow().isoformat()
        }
        
        db.table("uploaded_files").insert(file_metadata).execute()
        
        return {
            "file_id": file_metadata["id"],
            "file_url": file_url,
            "file_type": "voice" if is_voice_note else "audio",
            "filename": file.filename,
            "size": file_size
        }
    
    except Exception as e:
        logger.error(f"Error uploading audio: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload audio: {str(e)}")


@router.post("/document")
async def upload_document(
    file: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None),
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Upload document for messaging"""
    
    try:
        # Validate file type
        if not validate_file_type(file.content_type, ALLOWED_DOCUMENT_TYPES):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: PDF, Word, Excel, PowerPoint, Text"
            )
        
        # Check file size
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Max size: {MAX_FILE_SIZE / (1024 * 1024)}MB"
            )
        
        # Generate unique filename
        unique_filename = generate_unique_filename(file.filename)
        
        # Create subdirectory for documents
        doc_dir = UPLOAD_DIR / "documents" / datetime.utcnow().strftime("%Y%m")
        doc_dir.mkdir(parents=True, exist_ok=True)
        
        # Save file
        file_path = doc_dir / unique_filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Generate URL
        file_url = f"/uploads/documents/{datetime.utcnow().strftime('%Y%m')}/{unique_filename}"
        
        # Save metadata
        file_metadata = {
            "id": str(uuid4()),
            "user_id": user_id,
            "conversation_id": conversation_id,
            "file_type": "document",
            "original_filename": file.filename,
            "stored_filename": unique_filename,
            "file_path": str(file_path),
            "file_url": file_url,
            "file_size": file_size,
            "mime_type": file.content_type,
            "uploaded_at": datetime.utcnow().isoformat()
        }
        
        db.table("uploaded_files").insert(file_metadata).execute()
        
        return {
            "file_id": file_metadata["id"],
            "file_url": file_url,
            "file_type": "document",
            "filename": file.filename,
            "size": file_size
        }
    
    except Exception as e:
        logger.error(f"Error uploading document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload document: {str(e)}")


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Upload user avatar/profile picture"""
    
    try:
        # Validate file type (images only)
        if not validate_file_type(file.content_type, ALLOWED_IMAGE_TYPES):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}"
            )
        
        # Check file size (smaller limit for avatars)
        MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5MB
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        
        if file_size > MAX_AVATAR_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Max size: {MAX_AVATAR_SIZE / (1024 * 1024)}MB"
            )
        
        # Generate unique filename
        unique_filename = generate_unique_filename(file.filename)
        
        # Create subdirectory for avatars
        avatar_dir = UPLOAD_DIR / "avatars"
        avatar_dir.mkdir(parents=True, exist_ok=True)
        
        # Save file
        file_path = avatar_dir / unique_filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Generate URL
        file_url = f"/uploads/avatars/{unique_filename}"
        
        # Update user profile
        db.table("users").update({
            "avatar_url": file_url,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", user_id).execute()
        
        # Save metadata
        file_metadata = {
            "id": str(uuid4()),
            "user_id": user_id,
            "file_type": "avatar",
            "original_filename": file.filename,
            "stored_filename": unique_filename,
            "file_path": str(file_path),
            "file_url": file_url,
            "file_size": file_size,
            "mime_type": file.content_type,
            "uploaded_at": datetime.utcnow().isoformat()
        }
        
        db.table("uploaded_files").insert(file_metadata).execute()
        
        return {
            "file_id": file_metadata["id"],
            "file_url": file_url,
            "file_type": "avatar",
            "filename": file.filename,
            "size": file_size
        }
    
    except Exception as e:
        logger.error(f"Error uploading avatar: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload avatar: {str(e)}")
