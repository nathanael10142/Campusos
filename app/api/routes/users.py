"""
User management routes
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from app.models.user import UserUpdate, UserResponse
from app.core.database import get_db_session, get_db
from app.core.db_wrapper import DatabaseWrapper
from app.core.security import decode_token

router = APIRouter()


def get_current_user_id(authorization: str = Header(...)) -> str:
    """Extract user ID from token"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    token = authorization.split(" ")[1]
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return payload.get("sub")


@router.get("/profile", response_model=UserResponse)
async def get_profile(db: DatabaseWrapper = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    """Get user profile"""
    user = db.table("users").select("*").eq("id", user_id).execute()
    
    if not user.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_data = user.data[0]
    # Convert UUID to string for Pydantic validation
    user_data["id"] = str(user_data["id"])
    return UserResponse(**user_data)


@router.put("/profile", response_model=UserResponse)
async def update_profile(
    updates: UserUpdate,
    db: DatabaseWrapper = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """Update user profile"""
    
    update_data = updates.dict(exclude_unset=True)
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    result = db.table("users").update(update_data).eq("id", user_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_data = result.data[0]
    # Convert UUID to string for Pydantic validation
    user_data["id"] = str(user_data["id"])
    return UserResponse(**user_data)


@router.get("/balance")
async def get_balance(db: DatabaseWrapper = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    """Get Batera Coins balance"""
    user = db.table("users").select("batera_coins").eq("id", user_id).execute()
    
    if not user.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "batera_coins": user.data[0]["batera_coins"],
        "usd_equivalent": user.data[0]["batera_coins"] * 0.5
    }
