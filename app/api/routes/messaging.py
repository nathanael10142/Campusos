"""
Advanced Messaging System API
WhatsApp-Level Chat avec Contrôles Universitaires
Campus OS UNIGOM
"""

from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File, Form
from typing import List, Optional
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

class ConversationCreate(BaseModel):
    type: str  # 'direct', 'group', 'broadcast'
    name: Optional[str] = None
    description: Optional[str] = None
    participant_ids: List[str]
    faculty: Optional[str] = None
    academic_level: Optional[str] = None
    auditorium_id: Optional[str] = None
    course_code: Optional[str] = None


class ConversationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    only_admins_can_send: Optional[bool] = None
    only_admins_can_edit_info: Optional[bool] = None


class MessageCreate(BaseModel):
    content: Optional[str] = None
    message_type: str = 'text'  # text, image, video, audio, voice, document, location, etc.
    media_url: Optional[str] = None
    reply_to_message_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None


class MessageUpdate(BaseModel):
    content: str


class ParticipantUpdate(BaseModel):
    role: Optional[str] = None  # member, admin, super_admin
    can_send_messages: Optional[bool] = None
    can_add_members: Optional[bool] = None
    can_remove_members: Optional[bool] = None
    can_edit_group_info: Optional[bool] = None


class AddParticipantsRequest(BaseModel):
    user_ids: List[str]


class MessageReaction(BaseModel):
    reaction: str  # emoji


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


async def check_participant_permission(db, conversation_id: str, user_id: str, permission: str) -> bool:
    """Check if user has specific permission in conversation"""
    result = db.table("conversation_participants").select(permission).eq(
        "conversation_id", conversation_id
    ).eq("user_id", user_id).execute()
    
    if not result.data:
        return False
    
    return result.data[0].get(permission, False)


async def check_blocked(db, user_id: str, target_id: str) -> bool:
    """Check if users have blocked each other"""
    result = db.table("blocked_users").select("id").or_(
        f"and(blocker_id.eq.{user_id},blocked_id.eq.{target_id}),"
        f"and(blocker_id.eq.{target_id},blocked_id.eq.{user_id})"
    ).execute()
    
    return len(result.data) > 0


async def verify_auditorium_access(db, user_id: str, auditorium_id: str) -> bool:
    """Verify user has access to auditorium (same faculty/level)"""
    # Get user info
    user = db.table("users").select("faculty, academic_level").eq("id", user_id).execute()
    if not user.data:
        return False
    
    user_data = user.data[0]
    
    # Get auditorium info
    auditorium = db.table("auditoriums").select("faculty, academic_level").eq("id", auditorium_id).execute()
    if not auditorium.data:
        return False
    
    aud_data = auditorium.data[0]
    
    # Check match
    return (user_data["faculty"] == aud_data["faculty"] and 
            user_data["academic_level"] == aud_data["academic_level"])


# ============================================
# CONVERSATION ROUTES
# ============================================

@router.get("/conversations")
async def get_conversations(
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get all conversations for current user"""
    
    try:
        # Get conversations user is part of
        participant_result = db.table("conversation_participants").select(
            "conversation_id, role, is_muted, is_pinned, last_read_at"
        ).eq("user_id", user_id).execute()
        
        participant_data = participant_result.data if hasattr(participant_result, 'data') else (participant_result if isinstance(participant_result, list) else [])
        
        if not participant_data:
            return []
        
        conversation_ids = [p["conversation_id"] for p in participant_data]
        participant_map = {p["conversation_id"]: p for p in participant_data}
        
        # Get conversation details
        conv_result = db.table("conversations").select("*").in_("id", conversation_ids).eq("is_active", True).order("last_message_at", desc=True).execute()
        conversations = conv_result.data if hasattr(conv_result, 'data') else (conv_result if isinstance(conv_result, list) else [])
        
        # Enrich with participant info
        enriched = []
        for conv in conversations:
            conv_id = conv["id"]
            if conv_id not in participant_map:
                continue
            
            conv["user_role"] = participant_map[conv_id]["role"]
            conv["is_muted"] = participant_map[conv_id]["is_muted"]
            conv["is_pinned"] = participant_map[conv_id]["is_pinned"]
            conv["last_read_at"] = participant_map[conv_id]["last_read_at"]
            
            # Get unread count
            last_read = participant_map[conv_id]["last_read_at"] or "1970-01-01"
            unread_result = db.table("chat_messages").select("id").eq("conversation_id", conv_id).gt("created_at", last_read).execute()
            unread_msgs = unread_result.data if hasattr(unread_result, 'data') else (unread_result if isinstance(unread_result, list) else [])
            conv["unread_count"] = len(unread_msgs)
            
            # Get last message
            last_msg_result = db.table("chat_messages").select("*").eq("conversation_id", conv_id).order("created_at", desc=True).limit(1).execute()
            last_msgs = last_msg_result.data if hasattr(last_msg_result, 'data') else (last_msg_result if isinstance(last_msg_result, list) else [])
            conv["last_message"] = last_msgs[0] if last_msgs else None
            
            # For direct chats, get other participant info
            if conv.get("type") == "direct":
                other_result = db.table("conversation_participants").select("user_id").eq("conversation_id", conv_id).neq("user_id", user_id).execute()
                others = other_result.data if hasattr(other_result, 'data') else (other_result if isinstance(other_result, list) else [])
                
                if others:
                    other_user_result = db.table("users").select("id, full_name, avatar_url, status").eq("id", others[0]["user_id"]).execute()
                    other_users = other_user_result.data if hasattr(other_user_result, 'data') else (other_user_result if isinstance(other_user_result, list) else [])
                    
                    if other_users:
                        conv["other_participant"] = other_users[0]
            
            enriched.append(conv)
        
        return enriched
    
    except Exception as e:
        logger.error(f"Error fetching conversations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch conversations: {str(e)}")


@router.post("/conversations")
async def create_conversation(
    conversation: ConversationCreate,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Create new conversation (direct or group)"""
    
    # Validate type
    if conversation.type not in ['direct', 'group', 'broadcast']:
        raise HTTPException(status_code=400, detail="Invalid conversation type")
    
    # For direct chats, check if conversation already exists
    if conversation.type == 'direct':
        if len(conversation.participant_ids) != 1:
            raise HTTPException(status_code=400, detail="Direct chat requires exactly 1 other participant")
        
        other_user_id = conversation.participant_ids[0]
        
        # Check if blocked
        if await check_blocked(db, user_id, other_user_id):
            raise HTTPException(status_code=403, detail="Cannot create conversation with blocked user")
        
        # Check if conversation exists
        existing = db.rpc("get_direct_conversation", {
            "user1": user_id,
            "user2": other_user_id
        }).execute()
        
        if existing.data:
            return existing.data[0]
    
    # For groups, validate participants can access auditorium
    if conversation.type == 'group' and conversation.auditorium_id:
        for participant_id in conversation.participant_ids:
            if not await verify_auditorium_access(db, participant_id, conversation.auditorium_id):
                user_info = db.table("users").select("full_name").eq("id", participant_id).execute()
                user_name = user_info.data[0]["full_name"] if user_info.data else participant_id
                raise HTTPException(
                    status_code=403,
                    detail=f"User {user_name} n'a pas accès à cet auditoire"
                )
    
    # Create conversation
    conv_id = str(uuid4())
    conv_data = {
        "id": conv_id,
        "type": conversation.type,
        "name": conversation.name,
        "description": conversation.description,
        "faculty": conversation.faculty,
        "academic_level": conversation.academic_level,
        "auditorium_id": conversation.auditorium_id,
        "course_code": conversation.course_code,
        "created_by": user_id,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    db.table("conversations").insert(conv_data).execute()
    
    # Add creator as super_admin (for groups)
    participant_data = {
        "id": str(uuid4()),
        "conversation_id": conv_id,
        "user_id": user_id,
        "role": "super_admin" if conversation.type in ['group', 'broadcast'] else "member",
        "can_send_messages": True,
        "can_add_members": True if conversation.type in ['group', 'broadcast'] else False,
        "can_remove_members": True if conversation.type in ['group', 'broadcast'] else False,
        "can_edit_group_info": True if conversation.type in ['group', 'broadcast'] else False,
        "can_delete_messages": True if conversation.type in ['group', 'broadcast'] else False,
        "joined_at": datetime.utcnow().isoformat()
    }
    
    db.table("conversation_participants").insert(participant_data).execute()
    
    # Add other participants
    for participant_id in conversation.participant_ids:
        if participant_id != user_id:
            p_data = {
                "id": str(uuid4()),
                "conversation_id": conv_id,
                "user_id": participant_id,
                "role": "member",
                "can_send_messages": True,
                "added_by": user_id,
                "joined_at": datetime.utcnow().isoformat()
            }
            db.table("conversation_participants").insert(p_data).execute()
    
    # Create system message for group creation
    if conversation.type in ['group', 'broadcast']:
        system_msg = {
            "id": str(uuid4()),
            "conversation_id": conv_id,
            "sender_id": user_id,
            "content": f"Groupe créé par {user_id}",
            "message_type": "system",
            "created_at": datetime.utcnow().isoformat()
        }
        db.table("chat_messages").insert(system_msg).execute()
    
    return conv_data


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get conversation details"""
    
    # Verify user is participant
    participant = db.table("conversation_participants").select("*").eq(
        "conversation_id", conversation_id
    ).eq("user_id", user_id).execute()
    
    if not participant.data:
        raise HTTPException(status_code=403, detail="Not a participant of this conversation")
    
    # Get conversation
    conversation = db.table("conversations").select("*").eq("id", conversation_id).execute()
    
    if not conversation.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    conv = conversation.data[0]
    conv["user_role"] = participant.data[0]["role"]
    conv["user_permissions"] = participant.data[0]
    
    # Get creator info
    if conv.get("created_by"):
        creator_info = db.table("users").select("id, full_name, avatar_url").eq("id", conv["created_by"]).execute()
        if creator_info.data:
            conv["creator"] = creator_info.data[0]
    
    # Get all participants
    participants = db.table("conversation_participants").select(
        "*, users!conversation_participants_user_id_fkey(id, full_name, avatar_url, faculty, academic_level)"
    ).eq("conversation_id", conversation_id).execute()
    
    conv["participants"] = participants.data
    
    return conv


@router.put("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    updates: ConversationUpdate,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Update conversation (name, description, settings)"""
    
    # Check permission
    if not await check_participant_permission(db, conversation_id, user_id, "can_edit_group_info"):
        raise HTTPException(status_code=403, detail="No permission to edit group info")
    
    update_data = updates.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow().isoformat()
    
    result = db.table("conversations").update(update_data).eq("id", conversation_id).execute()
    
    return result.data[0] if result.data else None


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Delete/leave conversation"""
    
    # Check if user is participant
    participant = db.table("conversation_participants").select("role").eq(
        "conversation_id", conversation_id
    ).eq("user_id", user_id).execute()
    
    if not participant.data:
        raise HTTPException(status_code=403, detail="Not a participant")
    
    # Get conversation type
    conversation = db.table("conversations").select("type, created_by").eq("id", conversation_id).execute()
    
    if not conversation.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    conv_type = conversation.data[0]["type"]
    created_by = conversation.data[0]["created_by"]
    
    # For direct chats or if user is creator, mark as inactive
    if conv_type == 'direct' or created_by == user_id:
        db.table("conversations").update({"is_active": False}).eq("id", conversation_id).execute()
    else:
        # For groups, just remove user
        db.table("conversation_participants").update({
            "left_at": datetime.utcnow().isoformat()
        }).eq("conversation_id", conversation_id).eq("user_id", user_id).execute()
    
    return {"message": "Conversation deleted/left successfully"}


# ============================================
# MESSAGE ROUTES
# ============================================

@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    limit: int = 50,
    before: Optional[str] = None,  # message_id for pagination
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get messages in conversation with pagination"""
    
    # Verify user is participant
    participant = db.table("conversation_participants").select("id").eq(
        "conversation_id", conversation_id
    ).eq("user_id", user_id).execute()
    
    if not participant.data:
        raise HTTPException(status_code=403, detail="Not a participant")
    
    # Build query
    query = db.table("chat_messages").select(
        "*, sender:users(id, full_name, avatar_url)"
    ).eq("conversation_id", conversation_id).eq("is_deleted", False)
    
    if before:
        # Get timestamp of 'before' message
        before_msg = db.table("chat_messages").select("created_at").eq("id", before).execute()
        if before_msg.data:
            query = query.lt("created_at", before_msg.data[0]["created_at"])
    
    result = query.order("created_at", desc=True).limit(limit).execute()
    
    messages = result.data[::-1]  # Reverse to chronological order
    
    # Get reactions for each message
    if messages:
        message_ids = [msg["id"] for msg in messages]
        reactions = db.table("message_reactions").select(
            "message_id, reaction, user_id, users(full_name)"
        ).in_("message_id", message_ids).execute()
        
        # Group reactions by message
        reactions_by_message = {}
        for reaction in reactions.data:
            msg_id = reaction["message_id"]
            if msg_id not in reactions_by_message:
                reactions_by_message[msg_id] = []
            reactions_by_message[msg_id].append(reaction)
        
        # Add reactions to messages
        for msg in messages:
            msg["reactions"] = reactions_by_message.get(msg["id"], [])
    
    return messages


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    message: MessageCreate,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Send message in conversation"""
    
    # Check if user can send messages
    if not await check_participant_permission(db, conversation_id, user_id, "can_send_messages"):
        raise HTTPException(status_code=403, detail="No permission to send messages")
    
    # Create message
    msg_id = str(uuid4())
    msg_data = {
        "id": msg_id,
        "conversation_id": conversation_id,
        "sender_id": user_id,
        "content": message.content,
        "message_type": message.message_type,
        "media_url": message.media_url,
        "reply_to_message_id": message.reply_to_message_id,
        "latitude": message.latitude,
        "longitude": message.longitude,
        "location_name": message.location_name,
        "created_at": datetime.utcnow().isoformat()
    }
    
    result = db.table("chat_messages").insert(msg_data).execute()
    
    if result:
        # Fetch sender info to include in response
        sender_info = db.table("users").select("id, full_name, avatar_url").eq("id", user_id).execute()
        if sender_info.data:
            result["sender"] = sender_info.data[0]
    
    return result


@router.put("/messages/{message_id}")
async def edit_message(
    message_id: str,
    update: MessageUpdate,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Edit message (only text messages, within 15 minutes)"""
    
    # Get message
    message = db.table("chat_messages").select("*").eq("id", message_id).execute()
    
    if not message.data:
        raise HTTPException(status_code=404, detail="Message not found")
    
    msg = message.data[0]
    
    # Check if user is sender
    if msg["sender_id"] != user_id:
        raise HTTPException(status_code=403, detail="Can only edit own messages")
    
    # Check if message type is text
    if msg["message_type"] != "text":
        raise HTTPException(status_code=400, detail="Can only edit text messages")
    
    # Check time limit (15 minutes)
    created_at = datetime.fromisoformat(msg["created_at"].replace('Z', '+00:00'))
    if (datetime.utcnow() - created_at).total_seconds() > 900:  # 15 minutes
        raise HTTPException(status_code=400, detail="Can only edit messages within 15 minutes")
    
    # Update message
    result = db.table("chat_messages").update({
        "content": update.content,
        "is_edited": True,
        "edited_at": datetime.utcnow().isoformat()
    }).eq("id", message_id).execute()
    
    return result.data[0] if result.data else None


@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: str,
    for_everyone: bool = False,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Delete message (for self or for everyone)"""
    
    # Get message
    message = db.table("chat_messages").select("*, conversation_id").eq("id", message_id).execute()
    
    if not message.data:
        raise HTTPException(status_code=404, detail="Message not found")
    
    msg = message.data[0]
    
    # Check if user is sender
    if msg["sender_id"] != user_id:
        raise HTTPException(status_code=403, detail="Can only delete own messages")
    
    if for_everyone:
        # Check if within time limit (1 hour)
        created_at = datetime.fromisoformat(msg["created_at"].replace('Z', '+00:00'))
        if (datetime.utcnow() - created_at).total_seconds() > 3600:  # 1 hour
            raise HTTPException(status_code=400, detail="Can only delete for everyone within 1 hour")
        
        # Mark as deleted for everyone
        result = db.table("chat_messages").update({
            "is_deleted": True,
            "deleted_at": datetime.utcnow().isoformat(),
            "deleted_for_everyone": True,
            "content": "Ce message a été supprimé"
        }).eq("id", message_id).execute()
    else:
        # Just mark as deleted for user (soft delete)
        result = db.table("chat_messages").update({
            "is_deleted": True,
            "deleted_at": datetime.utcnow().isoformat()
        }).eq("id", message_id).execute()
    
    return {"message": "Message deleted"}


@router.post("/messages/{message_id}/reactions")
async def add_reaction(
    message_id: str,
    reaction_data: MessageReaction,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Add reaction to message"""
    
    # Verify message exists and user has access
    message = db.table("chat_messages").select("conversation_id").eq("id", message_id).execute()
    
    if not message.data:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Verify user is participant
    participant = db.table("conversation_participants").select("id").eq(
        "conversation_id", message.data[0]["conversation_id"]
    ).eq("user_id", user_id).execute()
    
    if not participant.data:
        raise HTTPException(status_code=403, detail="Not a participant")
    
    # Add reaction (upsert)
    reaction_entry = {
        "id": str(uuid4()),
        "message_id": message_id,
        "user_id": user_id,
        "reaction": reaction_data.reaction,
        "created_at": datetime.utcnow().isoformat()
    }
    
    result = db.table("message_reactions").upsert(reaction_entry).execute()
    
    return result.data[0] if result.data else None


@router.delete("/messages/{message_id}/reactions")
async def remove_reaction(
    message_id: str,
    reaction: str,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Remove reaction from message"""
    
    result = db.table("message_reactions").delete().eq(
        "message_id", message_id
    ).eq("user_id", user_id).eq("reaction", reaction).execute()
    
    return {"message": "Reaction removed"}


@router.post("/messages/{message_id}/status")
async def update_message_status(
    message_id: str,
    status: str,  # 'delivered' or 'read'
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Update message status (delivered/read)"""
    
    if status not in ['delivered', 'read']:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    # Update or insert status
    status_entry = {
        "id": str(uuid4()),
        "message_id": message_id,
        "user_id": user_id,
        "status": status,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    result = db.table("message_status").upsert(status_entry).execute()
    
    # If status is 'read', update participant's last_read_at
    if status == 'read':
        message = db.table("chat_messages").select("conversation_id").eq("id", message_id).execute()
        if message.data:
            db.table("conversation_participants").update({
                "last_read_at": datetime.utcnow().isoformat(),
                "last_read_message_id": message_id
            }).eq("conversation_id", message.data[0]["conversation_id"]).eq("user_id", user_id).execute()
    
    return result.data[0] if result.data else None


# ============================================
# PARTICIPANT MANAGEMENT
# ============================================

@router.post("/conversations/{conversation_id}/participants")
async def add_participants(
    conversation_id: str,
    request: AddParticipantsRequest,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Add participants to conversation"""
    
    # Check permission
    if not await check_participant_permission(db, conversation_id, user_id, "can_add_members"):
        raise HTTPException(status_code=403, detail="No permission to add members")
    
    # Get conversation details for auditorium validation
    conversation = db.table("conversations").select("auditorium_id, type").eq("id", conversation_id).execute()
    
    if not conversation.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    conv = conversation.data[0]
    
    # Validate auditorium access for new participants
    if conv["auditorium_id"]:
        for new_user_id in request.user_ids:
            if not await verify_auditorium_access(db, new_user_id, conv["auditorium_id"]):
                user_info = db.table("users").select("full_name").eq("id", new_user_id).execute()
                user_name = user_info.data[0]["full_name"] if user_info.data else new_user_id
                raise HTTPException(
                    status_code=403,
                    detail=f"User {user_name} n'a pas accès à cet auditoire"
                )
    
    # Add participants
    added_users = []
    for new_user_id in request.user_ids:
        # Check if already participant
        existing = db.table("conversation_participants").select("id").eq(
            "conversation_id", conversation_id
        ).eq("user_id", new_user_id).execute()
        
        if not existing.data:
            participant_data = {
                "id": str(uuid4()),
                "conversation_id": conversation_id,
                "user_id": new_user_id,
                "role": "member",
                "can_send_messages": True,
                "added_by": user_id,
                "joined_at": datetime.utcnow().isoformat()
            }
            db.table("conversation_participants").insert(participant_data).execute()
            added_users.append(new_user_id)
            
            # Create system message
            user_info = db.table("users").select("full_name").eq("id", new_user_id).execute()
            user_name = user_info.data[0]["full_name"] if user_info.data else "Utilisateur"
            
            system_msg = {
                "id": str(uuid4()),
                "conversation_id": conversation_id,
                "sender_id": user_id,
                "content": f"{user_name} a été ajouté au groupe",
                "message_type": "system",
                "created_at": datetime.utcnow().isoformat()
            }
            db.table("chat_messages").insert(system_msg).execute()
    
    return {"added_users": added_users}


@router.delete("/conversations/{conversation_id}/participants/{participant_id}")
async def remove_participant(
    conversation_id: str,
    participant_id: str,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Remove participant from conversation"""
    
    # Check if user can remove members OR removing self
    if participant_id != user_id:
        if not await check_participant_permission(db, conversation_id, user_id, "can_remove_members"):
            raise HTTPException(status_code=403, detail="No permission to remove members")
    
    # Remove participant
    db.table("conversation_participants").update({
        "left_at": datetime.utcnow().isoformat()
    }).eq("conversation_id", conversation_id).eq("user_id", participant_id).execute()
    
    # Create system message
    user_info = db.table("users").select("full_name").eq("id", participant_id).execute()
    user_name = user_info.data[0]["full_name"] if user_info.data else "Utilisateur"
    
    system_msg = {
        "id": str(uuid4()),
        "conversation_id": conversation_id,
        "sender_id": user_id,
        "content": f"{user_name} a quitté le groupe",
        "message_type": "system",
        "created_at": datetime.utcnow().isoformat()
    }
    db.table("chat_messages").insert(system_msg).execute()
    
    return {"message": "Participant removed"}


@router.put("/conversations/{conversation_id}/participants/{participant_id}")
async def update_participant(
    conversation_id: str,
    participant_id: str,
    update: ParticipantUpdate,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Update participant role/permissions"""
    
    # Check if user is admin
    current_participant = db.table("conversation_participants").select("role").eq(
        "conversation_id", conversation_id
    ).eq("user_id", user_id).execute()
    
    if not current_participant.data or current_participant.data[0]["role"] not in ['admin', 'super_admin']:
        raise HTTPException(status_code=403, detail="Only admins can update participant roles")
    
    # Update participant
    update_data = update.dict(exclude_unset=True)
    result = db.table("conversation_participants").update(update_data).eq(
        "conversation_id", conversation_id
    ).eq("user_id", participant_id).execute()
    
    return result.data[0] if result.data else None


# ============================================
# BLOCKED USERS
# ============================================

@router.post("/users/{target_id}/block")
async def block_user(
    target_id: str,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Block a user"""
    
    if target_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot block yourself")
    
    # Block user
    block_data = {
        "id": str(uuid4()),
        "blocker_id": user_id,
        "blocked_id": target_id,
        "created_at": datetime.utcnow().isoformat()
    }
    
    result = db.table("blocked_users").upsert(block_data).execute()
    
    return {"message": "User blocked"}


@router.delete("/users/{target_id}/block")
async def unblock_user(
    target_id: str,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Unblock a user"""
    
    db.table("blocked_users").delete().eq("blocker_id", user_id).eq("blocked_id", target_id).execute()
    
    return {"message": "User unblocked"}


@router.get("/blocked-users")
async def get_blocked_users(
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get list of blocked users"""
    
    result = db.table("blocked_users").select(
        "*, blocked_user:users(id, full_name, avatar_url)"
    ).eq("blocker_id", user_id).execute()
    
    return result.data


# ============================================
# AUDITORIUMS
# ============================================

@router.get("/auditoriums")
async def get_auditoriums(
    faculty: Optional[str] = None,
    academic_level: Optional[str] = None,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get available auditoriums"""
    
    query = db.table("auditoriums").select("*")
    
    if faculty:
        query = query.eq("faculty", faculty)
    if academic_level:
        query = query.eq("academic_level", academic_level)
    
    result = query.execute()
    
    return result.data


# ============================================
# TYPING INDICATORS
# ============================================

@router.post("/conversations/{conversation_id}/typing")
async def set_typing_indicator(
    conversation_id: str,
    is_typing: bool = True,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Set typing indicator for user in conversation
    This will be used with real-time subscriptions on frontend
    """
    
    # Verify user is participant
    participant = db.table("conversation_participants").select("id").eq(
        "conversation_id", conversation_id
    ).eq("user_id", user_id).execute()
    
    if not participant.data:
        raise HTTPException(status_code=403, detail="Not a participant")
    
    # Upsert typing indicator
    typing_data = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "is_typing": is_typing,
        "updated_at": datetime.utcnow().isoformat()
    }
    
    if is_typing:
        # Insert/update typing indicator
        result = db.table("typing_indicators").upsert(typing_data).execute()
    else:
        # Remove typing indicator
        result = db.table("typing_indicators").delete().eq(
            "conversation_id", conversation_id
        ).eq("user_id", user_id).execute()
    
    return {"is_typing": is_typing}


@router.get("/conversations/{conversation_id}/typing")
async def get_typing_indicators(
    conversation_id: str,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Get who is currently typing in conversation
    """
    
    # Verify user is participant
    participant = db.table("conversation_participants").select("id").eq(
        "conversation_id", conversation_id
    ).eq("user_id", user_id).execute()
    
    if not participant.data:
        raise HTTPException(status_code=403, detail="Not a participant")
    
    # Get typing indicators (excluding current user)
    result = db.table("typing_indicators").select(
        "*, user:users(full_name, avatar_url)"
    ).eq("conversation_id", conversation_id).eq("is_typing", True).neq(
        "user_id", user_id
    ).execute()
    
    # Filter out stale indicators (older than 5 seconds)
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(seconds=5)).isoformat()
    
    typing_users = []
    for indicator in (result.data if hasattr(result, 'data') else []):
        if indicator.get("updated_at", "") > cutoff:
            typing_users.append(indicator)
    
    return typing_users


# ============================================
# SETTINGS & PREFERENCES
# ============================================

@router.put("/settings")
async def update_messaging_settings(
    enable_read_receipts: Optional[bool] = None,
    enable_typing_indicators: Optional[bool] = None,
    enable_message_notifications: Optional[bool] = None,
    enable_group_notifications: Optional[bool] = None,
    auto_download_media: Optional[bool] = None,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Update user's messaging settings"""
    
    settings_data = {}
    
    if enable_read_receipts is not None:
        settings_data["enable_read_receipts"] = enable_read_receipts
    if enable_typing_indicators is not None:
        settings_data["enable_typing_indicators"] = enable_typing_indicators
    if enable_message_notifications is not None:
        settings_data["enable_message_notifications"] = enable_message_notifications
    if enable_group_notifications is not None:
        settings_data["enable_group_notifications"] = enable_group_notifications
    if auto_download_media is not None:
        settings_data["auto_download_media"] = auto_download_media
    
    if not settings_data:
        raise HTTPException(status_code=400, detail="No settings to update")
    
    settings_data["updated_at"] = datetime.utcnow().isoformat()
    
    # Upsert user settings
    result = db.table("user_messaging_settings").upsert({
        "user_id": user_id,
        **settings_data
    }).execute()
    
    return result.data[0] if result.data else settings_data


@router.get("/settings")
async def get_messaging_settings(
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Get user's messaging settings"""
    
    result = db.table("user_messaging_settings").select("*").eq("user_id", user_id).execute()
    
    if result.data:
        return result.data[0]
    else:
        # Return default settings
        return {
            "user_id": user_id,
            "enable_read_receipts": True,
            "enable_typing_indicators": True,
            "enable_message_notifications": True,
            "enable_group_notifications": True,
            "auto_download_media": False
        }
