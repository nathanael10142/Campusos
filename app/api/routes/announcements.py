"""
Admin Announcements System - Official Communications
Campus OS UNIGOM - Professional Broadcast System
Développé par Nathanael Batera Akilimali
"""

from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File, Form, status
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import uuid4
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import UserRole
from loguru import logger
import json

router = APIRouter()


# ============================================
# MODELS
# ============================================

class AnnouncementType(str):
    INFO = "info"
    URGENT = "urgent"
    EVENT = "event"
    ACADEMIC = "academic"
    GENERAL = "general"
    MAINTENANCE = "maintenance"


class AnnouncementStatus(str):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class TargetAudience(BaseModel):
    """Target audience for announcement"""
    all_users: bool = True
    faculties: Optional[List[str]] = None
    academic_levels: Optional[List[str]] = None


class AnnouncementCreate(BaseModel):
    """Create announcement schema"""
    title: str = Field(..., min_length=3, max_length=255)
    content: str = Field(..., min_length=10)
    type: str = Field(default="general")
    status: str = Field(default="draft")
    background_image_url: Optional[str] = None
    background_color: Optional[str] = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')
    target_audience: Optional[TargetAudience] = None


class AnnouncementUpdate(BaseModel):
    """Update announcement schema"""
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    content: Optional[str] = Field(None, min_length=10)
    type: Optional[str] = None
    status: Optional[str] = None
    background_image_url: Optional[str] = None
    background_color: Optional[str] = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')
    target_audience: Optional[TargetAudience] = None


class AnnouncementResponse(BaseModel):
    """Announcement response schema"""
    id: str
    title: str
    content: str
    type: str
    status: str
    background_image_url: Optional[str]
    background_color: Optional[str]
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime]
    published_at: Optional[datetime]
    archived_at: Optional[datetime]
    target_all_users: bool
    target_faculties: Optional[List[str]]
    target_academic_levels: Optional[List[str]]
    attachments: List[Dict[str, Any]] = []
    stats: Optional[Dict[str, Any]] = None
    user_has_viewed: Optional[bool] = None


class ReactionCreate(BaseModel):
    """Add reaction to announcement"""
    reaction: str = Field(..., min_length=1, max_length=10)


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


def get_current_admin_id(authorization: str = Header(...)) -> str:
    """Verify admin access"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    token = authorization.split(" ")[1]
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    user_id = payload.get("sub")
    role = payload.get("role")
    
    if role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=403,
            detail="Accès refusé. Seuls les administrateurs peuvent gérer les annonces officielles."
        )
    
    return user_id


async def get_announcement_with_details(db, announcement_id: str, user_id: Optional[str] = None):
    """Get announcement with attachments and stats"""
    
    # Get announcement
    announcement = db.table("announcements").select("*").eq("id", announcement_id).execute()
    
    if not announcement.data:
        return None
    
    ann_data = announcement.data[0]
    
    # Get attachments
    attachments = db.table("announcement_attachments").select("*").eq(
        "announcement_id", announcement_id
    ).execute()
    
    # Get stats
    stats_result = db.rpc("get_announcement_stats", {"p_announcement_id": announcement_id}).execute()
    stats = stats_result.data[0] if stats_result.data else {
        "total_views": 0,
        "total_reactions": 0,
        "reaction_breakdown": {}
    }
    
    # Check if user has viewed
    user_has_viewed = False
    if user_id:
        view_check = db.table("announcement_views").select("id").eq(
            "announcement_id", announcement_id
        ).eq("user_id", user_id).execute()
        user_has_viewed = len(view_check.data) > 0
    
    return {
        **ann_data,
        "attachments": attachments.data if attachments.data else [],
        "stats": stats,
        "user_has_viewed": user_has_viewed
    }


# ============================================
# ADMIN ROUTES
# ============================================

@router.post("/", response_model=AnnouncementResponse, status_code=status.HTTP_201_CREATED)
async def create_announcement(
    announcement: AnnouncementCreate,
    db=Depends(get_db),
    admin_id: str = Depends(get_current_admin_id)
):
    """
    Create a new announcement (Admin only)
    """
    try:
        # Prepare data
        announcement_data = {
            "title": announcement.title,
            "content": announcement.content,
            "type": announcement.type,
            "status": announcement.status,
            "background_image_url": announcement.background_image_url,
            "background_color": announcement.background_color,
            "created_by": admin_id,
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Handle target audience
        if announcement.target_audience:
            announcement_data["target_all_users"] = announcement.target_audience.all_users
            announcement_data["target_faculties"] = announcement.target_audience.faculties
            announcement_data["target_academic_levels"] = announcement.target_audience.academic_levels
        else:
            announcement_data["target_all_users"] = True
        
        # Set published_at if status is published
        if announcement.status == "published":
            announcement_data["published_at"] = datetime.utcnow().isoformat()
        
        # Create announcement
        result = db.table("announcements").insert(announcement_data).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la création de l'annonce"
            )
        
        created = result.data[0]
        
        # Get full details
        full_announcement = await get_announcement_with_details(db, created["id"], admin_id)
        
        logger.info(f"Announcement created by admin {admin_id}: {created['id']}")
        
        return AnnouncementResponse(**full_announcement)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating announcement: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la création de l'annonce"
        )


@router.get("/admin", response_model=List[AnnouncementResponse])
async def get_admin_announcements(
    status_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    limit: int = 50,
    db=Depends(get_db),
    admin_id: str = Depends(get_current_admin_id)
):
    """
    Get all announcements for admin management (Admin only)
    """
    try:
        query = db.table("announcements").select("*")
        
        if status_filter:
            query = query.eq("status", status_filter)
        
        if type_filter:
            query = query.eq("type", type_filter)
        
        result = query.order("created_at", desc=True).limit(limit).execute()
        
        # Get full details for each
        announcements = []
        for ann in result.data:
            full_ann = await get_announcement_with_details(db, ann["id"], admin_id)
            announcements.append(AnnouncementResponse(**full_ann))
        
        return announcements
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching admin announcements: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération des annonces"
        )


@router.put("/{announcement_id}", response_model=AnnouncementResponse)
async def update_announcement(
    announcement_id: str,
    update_data: AnnouncementUpdate,
    db=Depends(get_db),
    admin_id: str = Depends(get_current_admin_id)
):
    """
    Update an announcement (Admin only)
    """
    try:
        # Check if announcement exists
        existing = db.table("announcements").select("*").eq("id", announcement_id).execute()
        
        if not existing.data:
            raise HTTPException(status_code=404, detail="Annonce non trouvée")
        
        # Prepare update data
        update_dict = {}
        
        if update_data.title is not None:
            update_dict["title"] = update_data.title
        if update_data.content is not None:
            update_dict["content"] = update_data.content
        if update_data.type is not None:
            update_dict["type"] = update_data.type
        if update_data.status is not None:
            update_dict["status"] = update_data.status
            # Set published_at if changing to published
            if update_data.status == "published" and existing.data[0]["published_at"] is None:
                update_dict["published_at"] = datetime.utcnow().isoformat()
            # Set archived_at if changing to archived
            elif update_data.status == "archived":
                update_dict["archived_at"] = datetime.utcnow().isoformat()
        if update_data.background_image_url is not None:
            update_dict["background_image_url"] = update_data.background_image_url
        if update_data.background_color is not None:
            update_dict["background_color"] = update_data.background_color
        if update_data.target_audience is not None:
            update_dict["target_all_users"] = update_data.target_audience.all_users
            update_dict["target_faculties"] = update_data.target_audience.faculties
            update_dict["target_academic_levels"] = update_data.target_audience.academic_levels
        
        update_dict["updated_at"] = datetime.utcnow().isoformat()
        
        # Update
        result = db.table("announcements").update(update_dict).eq("id", announcement_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la mise à jour"
            )
        
        # Get full details
        full_announcement = await get_announcement_with_details(db, announcement_id, admin_id)
        
        logger.info(f"Announcement updated by admin {admin_id}: {announcement_id}")
        
        return AnnouncementResponse(**full_announcement)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating announcement: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la mise à jour de l'annonce"
        )


@router.delete("/{announcement_id}")
async def delete_announcement(
    announcement_id: str,
    db=Depends(get_db),
    admin_id: str = Depends(get_current_admin_id)
):
    """
    Delete an announcement (Admin only)
    """
    try:
        # Check if exists
        existing = db.table("announcements").select("id").eq("id", announcement_id).execute()
        
        if not existing.data:
            raise HTTPException(status_code=404, detail="Annonce non trouvée")
        
        # Delete (cascade will handle attachments, views, reactions)
        db.table("announcements").delete().eq("id", announcement_id).execute()
        
        logger.info(f"Announcement deleted by admin {admin_id}: {announcement_id}")
        
        return {"success": True, "message": "Annonce supprimée avec succès"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting announcement: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la suppression de l'annonce"
        )


@router.post("/{announcement_id}/attachments")
async def add_announcement_attachment(
    announcement_id: str,
    file: UploadFile = File(...),
    file_type: str = Form(...),
    db=Depends(get_db),
    admin_id: str = Depends(get_current_admin_id)
):
    """
    Add attachment to announcement (Admin only)
    Note: File upload should be handled by the existing upload system
    This endpoint just creates the attachment record
    """
    try:
        # Check if announcement exists
        announcement = db.table("announcements").select("id").eq("id", announcement_id).execute()
        
        if not announcement.data:
            raise HTTPException(status_code=404, detail="Annonce non trouvée")
        
        # This is a placeholder - integrate with existing upload system
        # For now, return structure for frontend to implement
        return {
            "message": "Upload attachment using the main upload endpoint, then call this with file_url",
            "upload_endpoint": "/api/upload/file",
            "then_call": f"/api/announcements/{announcement_id}/attachments/link"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding attachment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de l'ajout de la pièce jointe"
        )


@router.post("/{announcement_id}/attachments/link")
async def link_announcement_attachment(
    announcement_id: str,
    file_url: str = Form(...),
    file_name: str = Form(...),
    file_type: str = Form(...),
    file_size: int = Form(...),
    mime_type: str = Form(...),
    thumbnail_url: Optional[str] = Form(None),
    db=Depends(get_db),
    admin_id: str = Depends(get_current_admin_id)
):
    """
    Link an already uploaded file to announcement (Admin only)
    """
    try:
        attachment_data = {
            "announcement_id": announcement_id,
            "file_type": file_type,
            "file_url": file_url,
            "file_name": file_name,
            "file_size": file_size,
            "mime_type": mime_type,
            "thumbnail_url": thumbnail_url,
            "created_at": datetime.utcnow().isoformat()
        }
        
        result = db.table("announcement_attachments").insert(attachment_data).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de l'ajout de la pièce jointe"
            )
        
        logger.info(f"Attachment added to announcement {announcement_id} by admin {admin_id}")
        
        return result.data[0]
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error linking attachment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de l'ajout de la pièce jointe"
        )


# ============================================
# USER ROUTES
# ============================================

@router.get("/user", response_model=List[AnnouncementResponse])
async def get_user_announcements(
    limit: int = 50,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Get announcements for current user (filtered by target audience)
    """
    try:
        # Use the SQL function to get filtered announcements
        result = db.rpc("get_user_announcements", {"p_user_id": user_id}).execute()
        
        # Get full details for each
        announcements = []
        for ann in result.data[:limit]:
            full_ann = await get_announcement_with_details(db, ann["id"], user_id)
            announcements.append(AnnouncementResponse(**full_ann))
        
        return announcements
    
    except Exception as e:
        logger.error(f"Error fetching user announcements: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération des annonces"
        )


@router.get("/{announcement_id}", response_model=AnnouncementResponse)
async def get_announcement(
    announcement_id: str,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Get single announcement details
    """
    try:
        full_announcement = await get_announcement_with_details(db, announcement_id, user_id)
        
        if not full_announcement:
            raise HTTPException(status_code=404, detail="Annonce non trouvée")
        
        return AnnouncementResponse(**full_announcement)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching announcement: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération de l'annonce"
        )


@router.post("/{announcement_id}/view")
async def mark_announcement_viewed(
    announcement_id: str,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Mark announcement as viewed by user
    """
    try:
        # Check if already viewed
        existing = db.table("announcement_views").select("id").eq(
            "announcement_id", announcement_id
        ).eq("user_id", user_id).execute()
        
        if existing.data:
            return {"success": True, "message": "Déjà marquée comme vue"}
        
        # Create view record
        view_data = {
            "announcement_id": announcement_id,
            "user_id": user_id,
            "viewed_at": datetime.utcnow().isoformat()
        }
        
        db.table("announcement_views").insert(view_data).execute()
        
        return {"success": True, "message": "Marquée comme vue"}
    
    except Exception as e:
        logger.error(f"Error marking announcement as viewed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors du marquage"
        )


@router.post("/{announcement_id}/react")
async def react_to_announcement(
    announcement_id: str,
    reaction_data: ReactionCreate,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Add or update reaction to announcement
    """
    try:
        # Check if user already reacted
        existing = db.table("announcement_reactions").select("id").eq(
            "announcement_id", announcement_id
        ).eq("user_id", user_id).execute()
        
        if existing.data:
            # Update existing reaction
            result = db.table("announcement_reactions").update({
                "reaction": reaction_data.reaction
            }).eq("announcement_id", announcement_id).eq("user_id", user_id).execute()
        else:
            # Create new reaction
            reaction_record = {
                "announcement_id": announcement_id,
                "user_id": user_id,
                "reaction": reaction_data.reaction,
                "created_at": datetime.utcnow().isoformat()
            }
            result = db.table("announcement_reactions").insert(reaction_record).execute()
        
        return {"success": True, "message": "Réaction ajoutée"}
    
    except Exception as e:
        logger.error(f"Error adding reaction: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de l'ajout de la réaction"
        )


@router.get("/{announcement_id}/stats")
async def get_announcement_statistics(
    announcement_id: str,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Get announcement statistics (views, reactions)
    """
    try:
        stats_result = db.rpc("get_announcement_stats", {"p_announcement_id": announcement_id}).execute()
        
        if not stats_result.data:
            return {
                "total_views": 0,
                "total_reactions": 0,
                "reaction_breakdown": {}
            }
        
        return stats_result.data[0]
    
    except Exception as e:
        logger.error(f"Error fetching announcement stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération des statistiques"
        )
