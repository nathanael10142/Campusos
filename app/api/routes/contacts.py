"""
Contacts & User Discovery API
Campus OS UNIGOM
"""

from fastapi import APIRouter, HTTPException, Depends, Header, Query, Request
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from uuid import uuid4
from app.core.database import get_db
from app.core.security import decode_token
from loguru import logger
import urllib.parse

router = APIRouter()


# ============================================
# MODELS
# ============================================

class UserSearchResult(BaseModel):
    id: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    faculty: Optional[str] = None
    academic_level: Optional[str] = None
    status: Optional[str] = None
    is_registered: bool = True
    is_blocked: bool = False


class ContactInvite(BaseModel):
    phone: str
    name: Optional[str] = None
    message: Optional[str] = None


class WhatsAppInviteResponse(BaseModel):
    invite_url: str
    phone: str
    message: str


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


def generate_whatsapp_invite_url(phone: str, message: str) -> str:
    """Generate WhatsApp invitation URL"""
    # Clean phone number (remove spaces, dashes, etc.)
    clean_phone = ''.join(filter(str.isdigit, phone))
    
    # Ensure phone starts with country code (243 for DRC)
    if not clean_phone.startswith('243'):
        if clean_phone.startswith('0'):
            clean_phone = '243' + clean_phone[1:]
        else:
            clean_phone = '243' + clean_phone
    
    # Encode message for URL
    encoded_message = urllib.parse.quote(message)
    
    # Generate WhatsApp URL
    whatsapp_url = f"https://wa.me/{clean_phone}?text={encoded_message}"
    
    return whatsapp_url


# ============================================
# CONTACT ROUTES
# ============================================

@router.get("/search")
async def search_users(
    query: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Search for users by name, email, or phone
    Returns registered users from the database
    """
    
    try:
        # Search in database
        # Using ilike for case-insensitive search
        search_pattern = f"%{query}%"
        
        # Search by name, email, or phone
        result = db.table("users").select(
            "id, full_name, email, phone, avatar_url, faculty, academic_level, status"
        ).or_(
            f"full_name.ilike.{search_pattern},"
            f"email.ilike.{search_pattern},"
            f"phone.ilike.{search_pattern}"
        ).neq("id", user_id).limit(limit).execute()
        
        users = result.data if hasattr(result, 'data') else (result if isinstance(result, list) else [])
        
        # Check if any users are blocked
        if users:
            user_ids = [u["id"] for u in users]
            blocked_result = db.table("blocked_users").select("blocked_id").eq(
                "blocker_id", user_id
            ).in_("blocked_id", user_ids).execute()
            
            blocked_data = blocked_result.data if hasattr(blocked_result, 'data') else []
            blocked_ids = {b["blocked_id"] for b in blocked_data}
            
            # Mark blocked users
            for user in users:
                user["is_blocked"] = user["id"] in blocked_ids
                user["is_registered"] = True
        
        return users
    
    except Exception as e:
        logger.error(f"Error searching users: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to search users: {str(e)}")


@router.get("/faculty-contacts")
async def get_faculty_contacts(
    faculty: Optional[str] = None,
    academic_level: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Get contacts from same faculty/academic level
    Useful for creating study groups
    """
    
    try:
        # If faculty/level not provided, get from current user
        # Exception: admins (role == 'admin') may request broader results
        if (not faculty or not academic_level) and role != 'admin':
            user = db.table("users").select("faculty, academic_level").eq("id", user_id).execute()
            if user.data:
                faculty = faculty or user.data[0].get("faculty")
                academic_level = academic_level or user.data[0].get("academic_level")
        
        # Build query
        query = db.table("users").select(
            "id, full_name, email, phone, avatar_url, faculty, academic_level, status"
        ).neq("id", user_id)
        
        if faculty:
            query = query.eq("faculty", faculty)
        if academic_level:
            query = query.eq("academic_level", academic_level)
        # If role == 'admin' and no faculty/academic_level filters provided,
        # admin will receive a broader set (no additional filtering).
        
        result = query.limit(limit).execute()
        
        users = result.data if hasattr(result, 'data') else (result if isinstance(result, list) else [])
        
        # Check blocked users
        if users:
            user_ids = [u["id"] for u in users]
            blocked_result = db.table("blocked_users").select("blocked_id").eq(
                "blocker_id", user_id
            ).in_("blocked_id", user_ids).execute()
            
            blocked_data = blocked_result.data if hasattr(blocked_result, 'data') else []
            blocked_ids = {b["blocked_id"] for b in blocked_data}
            
            for user in users:
                user["is_blocked"] = user["id"] in blocked_ids
                user["is_registered"] = True
        
        return users
    
    except Exception as e:
        logger.error(f"Error fetching faculty contacts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch contacts: {str(e)}")


@router.get("/recent")
async def get_recent_contacts(
    limit: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Get recent contacts (users you've chatted with)
    """
    
    try:
        # Get conversations user is part of
        participant_result = db.table("conversation_participants").select(
            "conversation_id"
        ).eq("user_id", user_id).execute()
        
        participant_data = participant_result.data if hasattr(participant_result, 'data') else []
        
        if not participant_data:
            return []
        
        conversation_ids = [p["conversation_id"] for p in participant_data]
        
        # Get direct conversations only
        conv_result = db.table("conversations").select("id").eq(
            "type", "direct"
        ).in_("id", conversation_ids).order("last_message_at", desc=True).limit(limit).execute()
        
        direct_conv_ids = [c["id"] for c in (conv_result.data if hasattr(conv_result, 'data') else [])]
        
        if not direct_conv_ids:
            return []
        
        # Get other participants in these conversations
        other_participants_result = db.table("conversation_participants").select(
            "user_id, conversation_id"
        ).in_("conversation_id", direct_conv_ids).neq("user_id", user_id).execute()
        
        other_participants = other_participants_result.data if hasattr(other_participants_result, 'data') else []
        
        if not other_participants:
            return []
        
        # Get unique user IDs
        user_ids = list({p["user_id"] for p in other_participants})
        
        # Get user details
        users_result = db.table("users").select(
            "id, full_name, email, phone, avatar_url, faculty, academic_level, status"
        ).in_("id", user_ids).execute()
        
        users = users_result.data if hasattr(users_result, 'data') else []
        
        # Check blocked users
        if users:
            blocked_result = db.table("blocked_users").select("blocked_id").eq(
                "blocker_id", user_id
            ).in_("blocked_id", user_ids).execute()
            
            blocked_data = blocked_result.data if hasattr(blocked_result, 'data') else []
            blocked_ids = {b["blocked_id"] for b in blocked_data}
            
            for user in users:
                user["is_blocked"] = user["id"] in blocked_ids
                user["is_registered"] = True
        
        return users
    
    except Exception as e:
        logger.error(f"Error fetching recent contacts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch recent contacts: {str(e)}")


@router.post("/invite-whatsapp", response_model=WhatsAppInviteResponse)
async def generate_whatsapp_invite(
    invite: ContactInvite,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Generate WhatsApp invitation link for non-registered contacts
    """
    
    try:
        # Get current user info
        user = db.table("users").select("full_name").eq("id", user_id).execute()
        user_name = user.data[0]["full_name"] if user.data else "un étudiant"
        
        # Default invitation message
        if not invite.message:
            invite.message = (
                f"Salut! {user_name} t'invite à rejoindre Campus OS UNIGOM. "
                f"C'est la plateforme de communication universitaire avec l'Intelligence Batera. "
                f"Télécharge l'app et connecte-toi avec tes camarades! 🎓"
            )
        
        # Generate WhatsApp URL
        whatsapp_url = generate_whatsapp_invite_url(invite.phone, invite.message)
        
        # Log invitation attempt
        invite_log = {
            "id": str(uuid4()),
            "inviter_id": user_id,
            "phone": invite.phone,
            "name": invite.name,
            "invited_at": datetime.utcnow().isoformat(),
            "invitation_type": "whatsapp"
        }
        
        db.table("contact_invitations").insert(invite_log).execute()
        
        return WhatsAppInviteResponse(
            invite_url=whatsapp_url,
            phone=invite.phone,
            message=invite.message
        )
    
    except Exception as e:
        logger.error(f"Error generating WhatsApp invite: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate invite: {str(e)}")


@router.get("/invited")
async def get_invited_contacts(
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Get list of contacts you've invited
    """
    
    try:
        result = db.table("contact_invitations").select(
            "*"
        ).eq("inviter_id", user_id).order("invited_at", desc=True).limit(limit).execute()
        
        return result.data if hasattr(result, 'data') else []
    
    except Exception as e:
        logger.error(f"Error fetching invited contacts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch invited contacts: {str(e)}")


@router.post("/sync-phone-contacts")
async def sync_phone_contacts(
    request: Request,
    db=Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Sync phone contacts and find which ones are registered on Campus OS
    Returns: registered users and non-registered contacts
    """
    
    try:
        # Read body flexibly: accept raw JSON list or object with a phone list
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail='Invalid JSON body')

        if isinstance(body, list):
            phone_numbers = body
        elif isinstance(body, dict):
            # Support several possible keys
            phone_numbers = body.get('phone_numbers') or body.get('phones') or body.get('numbers')
            if phone_numbers is None:
                raise HTTPException(status_code=400, detail='Missing phone numbers in request body')
        else:
            raise HTTPException(status_code=400, detail='Invalid request body format')

        # Clean phone numbers
        clean_numbers = []
        for phone in phone_numbers:
            if not isinstance(phone, str):
                continue
            clean = ''.join(filter(str.isdigit, phone))
            if not clean:
                continue
            if clean.startswith('0'):
                clean = '243' + clean[1:]
            elif not clean.startswith('243'):
                clean = '243' + clean
            clean_numbers.append(clean)
        
        # Search for registered users
        result = db.table("users").select(
            "id, full_name, email, phone, avatar_url, faculty, academic_level, status"
        ).in_("phone", clean_numbers).neq("id", user_id).execute()
        
        registered_users = result.data if hasattr(result, 'data') else []
        
        # Find registered phone numbers
        registered_phones = {u.get("phone") for u in registered_users if u.get("phone")}
        
        # Find non-registered contacts
        non_registered = [
            {"phone": phone, "is_registered": False}
            for phone in clean_numbers
            if phone not in registered_phones
        ]
        
        # Check blocked users
        if registered_users:
            user_ids = [u["id"] for u in registered_users]
            blocked_result = db.table("blocked_users").select("blocked_id").eq(
                "blocker_id", user_id
            ).in_("blocked_id", user_ids).execute()
            
            blocked_data = blocked_result.data if hasattr(blocked_result, 'data') else []
            blocked_ids = {b["blocked_id"] for b in blocked_data}
            
            for user in registered_users:
                user["is_blocked"] = user["id"] in blocked_ids
                user["is_registered"] = True
        
        return {
            "registered": registered_users,
            "non_registered": non_registered
        }
    
    except Exception as e:
        logger.error(f"Error syncing phone contacts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to sync contacts: {str(e)}")
