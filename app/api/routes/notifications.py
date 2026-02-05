"""
Notifications routes
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import List
from pydantic import BaseModel
from datetime import datetime
from app.core.database import get_db
from app.core.security import decode_token

router = APIRouter()


class Notification(BaseModel):
    id: str
    user_id: str
    title: str
    message: str
    type: str  # info, warning, urgent, profit
    read: bool
    created_at: str


class NotificationCreate(BaseModel):
    title: str
    message: str
    type: str = "info"


def get_current_user_id(authorization: str = Header(...)) -> str:
    """Extract user ID from token"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    token = authorization.split(" ")[1]
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return payload.get("sub")


@router.get("/", response_model=List[Notification])
async def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    user_id: str = Depends(get_current_user_id)
):
    """Get user notifications"""
    db = get_db()
    
    query = db.table("notifications").select("*").eq("user_id", user_id)
    
    if unread_only:
        query = query.eq("read", False)
    
    notifications = query.order("created_at", desc=True).limit(limit).execute()
    
    return notifications.data


@router.post("/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Mark notification as read"""
    db = get_db()
    
    result = db.table("notifications")\
        .update({"read": True})\
        .eq("id", notification_id)\
        .eq("user_id", user_id)\
        .execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return {"success": True}


@router.post("/read-all")
async def mark_all_as_read(user_id: str = Depends(get_current_user_id)):
    """Mark all notifications as read"""
    db = get_db()
    
    db.table("notifications")\
        .update({"read": True})\
        .eq("user_id", user_id)\
        .eq("read", False)\
        .execute()
    
    return {"success": True, "message": "Toutes les notifications marquées comme lues"}
