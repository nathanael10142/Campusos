"""
Push Notifications API (Firebase Cloud Messaging)
Campus OS UNIGOM
"""

from fastapi import APIRouter, HTTPException, Depends, Header, BackgroundTasks
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from uuid import uuid4
from app.core.database import get_db
from app.core.security import decode_token
from loguru import logger

router = APIRouter()


# ============================================
# MODELS
# ============================================

class FCMTokenRegister(BaseModel):
    fcm_token: str
    device_id: str
    platform: str  # 'android', 'ios', 'web'


class PushNotification(BaseModel):
    user_ids: List[str]
    title: str
    body: str
    data: Optional[Dict[str, Any]] = None
    notification_type: str = 'message'


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


async def send_fcm_notification(
    fcm_tokens: List[str],
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Send push notification using Firebase Cloud Messaging
    Note: You need to set up Firebase Admin SDK and credentials
    """
    try:
        # Import Firebase Admin
        try:
            import firebase_admin
            from firebase_admin import messaging, credentials
        except ImportError:
            logger.error("Firebase Admin SDK not installed")
            return {"success": False, "error": "Firebase not configured"}
        
        # Initialize Firebase Admin if not already initialized
        if not firebase_admin._apps:
            # Load Firebase credentials (configure path in env)
            try:
                cred = credentials.Certificate("firebase-credentials.json")
                firebase_admin.initialize_app(cred)
            except Exception as e:
                logger.error(f"Failed to initialize Firebase: {e}")
                return {"success": False, "error": "Firebase initialization failed"}
        
        # Prepare notification
        notification = messaging.Notification(
            title=title,
            body=body
        )
        
        # Send to multiple tokens
        messages = [
            messaging.Message(
                notification=notification,
                data=data or {},
                token=token
            )
            for token in fcm_tokens
        ]
        
        # Send batch
        response = messaging.send_all(messages)
        
        logger.info(f"FCM sent: {response.success_count} successful, {response.failure_count} failed")
        
        return {
            "success": True,
            "success_count": response.success_count,
            "failure_count": response.failure_count
        }
    
    except Exception as e:
        logger.error(f"Error sending FCM notification: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def queue_notification(
    db,
    user_ids: List[str],
    title: str,
    body: str,
    notification_type: str,
    data: Optional[Dict[str, Any]] = None
):
    """Queue notifications for later delivery"""
    
    for user_id in user_ids:
        notification = {
            "id": str(uuid4()),
            "user_id": user_id,
            "notification_type": notification_type,
            "title": title,
            "body": body,
            "data": data,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        }
        
        db.table("notification_queue").insert(notification).execute()


async def send_message_notification(
    db,
    conversation_id: str,
    sender_id: str,
    message_content: str,
    background_tasks: BackgroundTasks
):
    """
    Send push notification for new message
    This should be called from messaging routes when a new message is sent
    """
    
    # Get conversation participants (except sender)
    participants_result = db.table("conversation_participants").select(
        "user_id"
    ).eq("conversation_id", conversation_id).neq("user_id", sender_id).eq(
        "is_muted", False
    ).execute()
    
    participants = participants_result.data if hasattr(participants_result, 'data') else []
    
    if not participants:
        return
    
    # Get sender info
    sender_result = db.table("users").select("full_name, avatar_url").eq("id", sender_id).execute()
    sender_name = sender_result.data[0]["full_name"] if sender_result.data else "Someone"
    
    # Get conversation info
    conv_result = db.table("conversations").select("type, name").eq("id", conversation_id).execute()
    conv = conv_result.data[0] if conv_result.data else {}
    
    # Prepare notification title/body
    if conv.get("type") == "group":
        title = conv.get("name", "Groupe")
        body = f"{sender_name}: {message_content[:100]}"
    else:
        title = sender_name
        body = message_content[:100]
    
    # Get FCM tokens for participants
    recipient_ids = [p["user_id"] for p in participants]
    
    # Check user settings for notifications
    settings_result = db.table("user_messaging_settings").select(
        "user_id, enable_message_notifications, enable_group_notifications"
    ).in_("user_id", recipient_ids).execute()
    
    settings_map = {
        s["user_id"]: s
        for s in (settings_result.data if hasattr(settings_result, 'data') else [])
    }
    
    # Filter recipients based on notification settings
    enabled_recipients = []
    for user_id in recipient_ids:
        settings = settings_map.get(user_id, {})
        if conv.get("type") == "group":
            if settings.get("enable_group_notifications", True):
                enabled_recipients.append(user_id)
        else:
            if settings.get("enable_message_notifications", True):
                enabled_recipients.append(user_id)
    
    if not enabled_recipients:
        return
    
    # Get FCM tokens
    tokens_result = db.table("push_notification_tokens").select(
        "fcm_token"
    ).in_("user_id", enabled_recipients).eq("is_active", True).execute()
    
    tokens = [t["fcm_token"] for t in (tokens_result.data if hasattr(tokens_result, 'data') else [])]
    
    if tokens:
        # Send notification in background
        background_tasks.add_task(
            send_fcm_notification,
            fcm_tokens=tokens,
            title=title,
            body=body,
            data={
                "type": "message",
                "conversation_id": conversation_id,
                "sender_id": sender_id
            }
        )


# ============================================
# FCM ROUTES
# ============================================

@router.post("/register-token")
async def register_fcm_token(
    token_data: FCMTokenRegister,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Register FCM token for push notifications"""
    
    try:
        # Validate platform
        if token_data.platform not in ['android', 'ios', 'web']:
            raise HTTPException(status_code=400, detail="Invalid platform")
        
        # Upsert token
        token_entry = {
            "id": str(uuid4()),
            "user_id": user_id,
            "device_id": token_data.device_id,
            "fcm_token": token_data.fcm_token,
            "platform": token_data.platform,
            "is_active": True,
            "last_used_at": datetime.utcnow().isoformat()
        }
        
        result = db.table("push_notification_tokens").upsert(token_entry).execute()
        
        return {"message": "Token registered successfully"}
    
    except Exception as e:
        logger.error(f"Error registering FCM token: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to register token: {str(e)}")


@router.delete("/token/{device_id}")
async def unregister_fcm_token(
    device_id: str,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Unregister FCM token"""
    
    try:
        db.table("push_notification_tokens").update({
            "is_active": False
        }).eq("user_id", user_id).eq("device_id", device_id).execute()
        
        return {"message": "Token unregistered"}
    
    except Exception as e:
        logger.error(f"Error unregistering token: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to unregister token: {str(e)}")


@router.post("/send")
async def send_push_notification(
    notification: PushNotification,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Send push notification (admin/system use)
    Regular users should not have access to this
    """
    
    try:
        # Check if user is admin (implement your admin check)
        # For now, just queue the notification
        
        # Queue notifications
        await queue_notification(
            db,
            notification.user_ids,
            notification.title,
            notification.body,
            notification.notification_type,
            notification.data
        )
        
        # Get FCM tokens
        tokens_result = db.table("push_notification_tokens").select(
            "fcm_token"
        ).in_("user_id", notification.user_ids).eq("is_active", True).execute()
        
        tokens = [t["fcm_token"] for t in (tokens_result.data if hasattr(tokens_result, 'data') else [])]
        
        if tokens:
            # Send in background
            background_tasks.add_task(
                send_fcm_notification,
                fcm_tokens=tokens,
                title=notification.title,
                body=notification.body,
                data=notification.data
            )
        
        return {
            "message": "Notification queued",
            "recipients": len(notification.user_ids),
            "tokens_found": len(tokens)
        }
    
    except Exception as e:
        logger.error(f"Error sending notification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to send notification: {str(e)}")


@router.get("/history")
async def get_notification_history(
    limit: int = 50,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get notification history for user"""
    
    try:
        result = db.table("notification_queue").select(
            "*"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
        
        return result.data if hasattr(result, 'data') else []
    
    except Exception as e:
        logger.error(f"Error fetching notification history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {str(e)}")


@router.post("/mark-read")
async def mark_notifications_read(
    notification_ids: List[str],
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Mark notifications as delivered/read"""
    
    try:
        db.table("notification_queue").update({
            "status": "delivered",
            "delivered_at": datetime.utcnow().isoformat()
        }).eq("user_id", user_id).in_("id", notification_ids).execute()
        
        return {"message": "Notifications marked as read"}
    
    except Exception as e:
        logger.error(f"Error marking notifications: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to mark notifications: {str(e)}")
