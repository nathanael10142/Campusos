"""
Chat routes - L'Oracle conversation management
"""

from fastapi import APIRouter, HTTPException, status, Depends, Header
from typing import List
from app.core.database import get_db
from app.core.security import decode_token
from datetime import datetime
from pydantic import BaseModel
from uuid import uuid4

router = APIRouter()


class ChatSessionCreate(BaseModel):
    user_id: str
    title: str
    course_context: str | None = None
    faculty_context: str | None = None


class ChatMessageCreate(BaseModel):
    content: str
    type: str = "text"


class ChatSessionResponse(BaseModel):
    id: str
    user_id: str
    title: str
    course_context: str | None
    faculty_context: str | None
    created_at: datetime
    updated_at: datetime | None
    is_active: bool
    message_count: int | None
    total_cost: float | None


class ChatMessageResponse(BaseModel):
    id: str
    chat_id: str
    sender: str
    type: str
    content: str
    code_language: str | None
    file_url: str | None
    metadata: dict | None
    timestamp: datetime
    is_read: bool


def get_current_user_id(authorization: str = Header(...)) -> str:
    """Extract user ID from token"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    token = authorization.split(" ")[1]
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return payload.get("sub")


@router.get("/sessions", response_model=List[ChatSessionResponse])
async def get_chat_sessions(db = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    """Get all chat sessions for user"""
    
    result = db.table("chat_sessions").select("*").eq("user_id", user_id).order("updated_at", desc=True).execute()
    
    return result.data


@router.post("/sessions", response_model=ChatSessionResponse)
async def create_chat_session(
    session: ChatSessionCreate,
    db = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Create new chat session"""
    
    session_data = {
        "id": str(uuid4()),
        "user_id": user_id,
        "title": session.title,
        "course_context": session.course_context,
        "faculty_context": session.faculty_context,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "is_active": True,
        "message_count": 0,
        "total_cost": 0.0
    }
    
    result = db.table("chat_sessions").insert(session_data).execute()
    
    return result.data[0]


@router.get("/sessions/{chat_id}/messages", response_model=List[ChatMessageResponse])
async def get_chat_messages(
    chat_id: str,
    db = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get all messages in a chat session"""
    
    # Verify user owns this chat
    session = db.table("chat_sessions").select("user_id").eq("id", chat_id).execute()
    if not session.data or session.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    result = db.table("chat_messages").select("*").eq("chat_id", chat_id).order("timestamp").execute()
    
    return result.data


@router.post("/sessions/{chat_id}/messages", response_model=ChatMessageResponse)
async def send_chat_message(
    chat_id: str,
    message: ChatMessageCreate,
    db = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Send a message in chat session"""
    
    # Verify user owns this chat
    session = db.table("chat_sessions").select("user_id").eq("id", chat_id).execute()
    if not session.data or session.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Create user message
    user_message = {
        "id": str(uuid4()),
        "chat_id": chat_id,
        "sender": "user",
        "type": message.type,
        "content": message.content,
        "timestamp": datetime.utcnow().isoformat(),
        "is_read": True
    }
    
    result = db.table("chat_messages").insert(user_message).execute()
    
    # Update session
    db.table("chat_sessions").update({
        "updated_at": datetime.utcnow().isoformat(),
        "message_count": db.func("message_count + 1")
    }).eq("id", chat_id).execute()
    
    return result.data[0]


@router.delete("/sessions/{chat_id}")
async def delete_chat_session(
    chat_id: str,
    db = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Delete a chat session"""
    
    # Verify user owns this chat
    session = db.table("chat_sessions").select("user_id").eq("id", chat_id).execute()
    if not session.data or session.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Delete messages first
    db.table("chat_messages").delete().eq("chat_id", chat_id).execute()
    
    # Delete session
    db.table("chat_sessions").delete().eq("id", chat_id).execute()
    
    return {"message": "Chat session deleted"}
