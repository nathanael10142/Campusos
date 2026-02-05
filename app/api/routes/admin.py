"""
Admin Panel Routes - Batera Command Center
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import List, Dict
from pydantic import BaseModel
from datetime import datetime, timedelta
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import UserRole

router = APIRouter()


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    total_revenue: float
    total_ai_queries: int
    coins_in_circulation: float


class UserManagement(BaseModel):
    id: str
    email: str
    full_name: str
    status: str
    batera_coins: float
    total_spent: float
    created_at: str


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
            detail="Accès refusé. Seul Nathanael Batera peut accéder au panneau Batera Command."
        )
    
    return user_id


@router.get("/stats", response_model=AdminStats)
async def get_admin_stats(admin_id: str = Depends(get_current_admin_id)):
    """Get dashboard statistics"""
    db = get_db()
    
    # Total users
    users = db.table("users").select("id, status, batera_coins").execute()
    total_users = len(users.data)
    active_users = len([u for u in users.data if u["status"] == "active"])
    coins_in_circulation = sum([u["batera_coins"] for u in users.data])
    
    # Total revenue
    purchases = db.table("purchase_transactions").select("amount_usd").eq("status", "completed").execute()
    total_revenue = sum([p["amount_usd"] for p in purchases.data])
    
    # Total AI queries
    ai_usage = db.table("ai_usage").select("id").execute()
    total_ai_queries = len(ai_usage.data)
    
    return AdminStats(
        total_users=total_users,
        active_users=active_users,
        total_revenue=total_revenue,
        total_ai_queries=total_ai_queries,
        coins_in_circulation=coins_in_circulation
    )


@router.get("/users", response_model=List[UserManagement])
async def list_users(
    status: str = None,
    limit: int = 100,
    admin_id: str = Depends(get_current_admin_id)
):
    """List all users with management info"""
    db = get_db()
    
    query = db.table("users").select("*")
    
    if status:
        query = query.eq("status", status)
    
    users = query.limit(limit).execute()
    
    result = []
    for user in users.data:
        # Get total spent
        transactions = db.table("transactions").select("amount").eq("user_id", user["id"]).eq("type", "debit").execute()
        total_spent = sum([t["amount"] for t in transactions.data])
        
        result.append(UserManagement(
            id=user["id"],
            email=user["email"],
            full_name=user["full_name"],
            status=user["status"],
            batera_coins=user["batera_coins"],
            total_spent=total_spent,
            created_at=user["created_at"]
        ))
    
    return result


@router.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: str,
    reason: str,
    admin_id: str = Depends(get_current_admin_id)
):
    """Suspend a user account"""
    db = get_db()
    
    result = db.table("users").update({"status": "suspended"}).eq("id", user_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Log admin action
    db.table("admin_logs").insert({
        "admin_id": admin_id,
        "action": "suspend_user",
        "target_user_id": user_id,
        "reason": reason,
        "created_at": datetime.utcnow().isoformat()
    }).execute()
    
    return {"success": True, "message": f"Utilisateur suspendu. Raison: {reason}"}


@router.post("/users/{user_id}/activate")
async def activate_user(
    user_id: str,
    admin_id: str = Depends(get_current_admin_id)
):
    """Activate a user account"""
    db = get_db()
    
    result = db.table("users").update({"status": "active"}).eq("id", user_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"success": True, "message": "Utilisateur activé"}


@router.post("/users/{user_id}/add-coins")
async def add_coins(
    user_id: str,
    amount: float,
    reason: str,
    admin_id: str = Depends(get_current_admin_id)
):
    """Add Batera Coins to user account"""
    db = get_db()
    
    # Get current balance
    user = db.table("users").select("batera_coins").eq("id", user_id).execute()
    
    if not user.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    new_balance = user.data[0]["batera_coins"] + amount
    
    # Update balance
    db.table("users").update({"batera_coins": new_balance}).eq("id", user_id).execute()
    
    # Log transaction
    db.table("transactions").insert({
        "user_id": user_id,
        "type": "credit",
        "amount": amount,
        "description": f"Ajouté par admin: {reason}",
        "created_at": datetime.utcnow().isoformat()
    }).execute()
    
    return {"success": True, "new_balance": new_balance}


@router.get("/purchases")
async def list_pending_purchases(admin_id: str = Depends(get_current_admin_id)):
    """List pending purchase transactions"""
    db = get_db()
    
    purchases = db.table("purchase_transactions")\
        .select("*")\
        .eq("status", "pending")\
        .order("created_at", desc=True)\
        .execute()
    
    return purchases.data


@router.post("/purchases/{transaction_id}/approve")
async def approve_purchase(
    transaction_id: str,
    admin_id: str = Depends(get_current_admin_id)
):
    """Approve a pending purchase"""
    db = get_db()
    
    # Get transaction
    transaction = db.table("purchase_transactions").select("*").eq("id", transaction_id).execute()
    
    if not transaction.data:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    trans_data = transaction.data[0]
    
    # Add coins to user
    user = db.table("users").select("batera_coins").eq("id", trans_data["user_id"]).execute()
    new_balance = user.data[0]["batera_coins"] + trans_data["coins"]
    
    db.table("users").update({"batera_coins": new_balance}).eq("id", trans_data["user_id"]).execute()
    
    # Update transaction status
    db.table("purchase_transactions").update({
        "status": "completed",
        "approved_by": admin_id,
        "approved_at": datetime.utcnow().isoformat()
    }).eq("id", transaction_id).execute()
    
    # Log credit transaction
    db.table("transactions").insert({
        "user_id": trans_data["user_id"],
        "type": "credit",
        "amount": trans_data["coins"],
        "description": f"Achat approuvé: {trans_data['coins']} Coins",
        "created_at": datetime.utcnow().isoformat()
    }).execute()
    
    return {"success": True, "message": "Achat approuvé et coins ajoutés"}


@router.get("/ai-usage")
async def get_ai_usage_stats(
    days: int = 30,
    admin_id: str = Depends(get_current_admin_id)
):
    """Get AI usage statistics"""
    db = get_db()
    
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    
    usage = db.table("ai_usage")\
        .select("service, cost, created_at")\
        .gte("created_at", since)\
        .execute()
    
    # Aggregate by service
    stats = {}
    total_cost = 0
    
    for record in usage.data:
        service = record["service"]
        cost = record["cost"]
        
        if service not in stats:
            stats[service] = {"count": 0, "total_cost": 0}
        
        stats[service]["count"] += 1
        stats[service]["total_cost"] += cost
        total_cost += cost
    
    return {
        "period_days": days,
        "total_queries": len(usage.data),
        "total_cost": total_cost,
        "by_service": stats
    }
