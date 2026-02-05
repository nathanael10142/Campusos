"""
Payments and Batera Coins routes
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import List
from pydantic import BaseModel
from datetime import datetime
from app.core.database import get_db
from app.core.security import decode_token
from loguru import logger

router = APIRouter()


class CoinPackage(BaseModel):
    id: str
    coins: float
    price_usd: float
    bonus: float
    popular: bool


class PurchaseRequest(BaseModel):
    package_id: str
    payment_method: str  # mobile_money, bank_transfer, etc.
    phone_number: str = None


class Transaction(BaseModel):
    id: str
    user_id: str
    type: str
    amount: float
    description: str
    created_at: str


def get_current_user_id(authorization: str = Header(...)) -> str:
    """Extract user ID from token"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    token = authorization.split(" ")[1]
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return payload.get("sub")


@router.get("/packages", response_model=List[CoinPackage])
async def get_coin_packages():
    """Get available Batera Coins packages"""
    db = get_db()
    packages = db.table("coin_packages").select("*").eq("active", True).execute()
    
    return packages.data


@router.post("/purchase")
async def purchase_coins(
    purchase: PurchaseRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Purchase Batera Coins"""
    db = get_db()
    
    # Get package
    package = db.table("coin_packages").select("*").eq("id", purchase.package_id).execute()
    
    if not package.data:
        raise HTTPException(status_code=404, detail="Package not found")
    
    package_data = package.data[0]
    
    # Create pending transaction
    transaction = {
        "user_id": user_id,
        "type": "purchase",
        "package_id": purchase.package_id,
        "coins": package_data["coins"],
        "amount_usd": package_data["price_usd"],
        "payment_method": purchase.payment_method,
        "phone_number": purchase.phone_number,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat()
    }
    
    result = db.table("purchase_transactions").insert(transaction).execute()
    
    logger.info(f"💰 New purchase request: {user_id} - {package_data['coins']} coins")
    
    return {
        "success": True,
        "transaction_id": result.data[0]["id"],
        "status": "pending",
        "message": "Votre demande d'achat a été enregistrée. Nathanael va vérifier votre paiement manuellement.",
        "instructions": f"Envoyez {package_data['price_usd']} USD au numéro {purchase.phone_number} puis contactez l'administrateur."
    }


@router.get("/transactions", response_model=List[Transaction])
async def get_transactions(
    limit: int = 50,
    user_id: str = Depends(get_current_user_id)
):
    """Get user transaction history"""
    db = get_db()
    
    transactions = db.table("transactions")\
        .select("*")\
        .eq("user_id", user_id)\
        .order("created_at", desc=True)\
        .limit(limit)\
        .execute()
    
    return transactions.data
