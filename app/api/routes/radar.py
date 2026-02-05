"""
Radar alerts routes - Campus notifications system
"""

from fastapi import APIRouter, HTTPException, status, Depends, Header, Query
from typing import List, Optional
from app.core.database import get_db_session
from app.core.security import decode_token
from datetime import datetime
from pydantic import BaseModel
from enum import Enum

router = APIRouter()


class AlertType(str, Enum):
    exam = "exam"
    course_change = "course_change"
    event = "event"
    emergency = "emergency"
    maintenance = "maintenance"
    announcement = "announcement"
    deadline = "deadline"


class AlertPriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class RadarAlertCreate(BaseModel):
    title: str
    message: str
    type: AlertType
    priority: AlertPriority
    target_faculty: Optional[str] = None
    target_level: Optional[str] = None
    target_course: Optional[str] = None
    expires_at: Optional[datetime] = None


class RadarAlertResponse(BaseModel):
    id: str
    title: str
    message: str
    type: str
    priority: str
    target_faculty: Optional[str]
    target_level: Optional[str]
    target_course: Optional[str]
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]
    created_by: Optional[str]
    views_count: int


def get_current_user_id(authorization: str = Header(...)) -> str:
    """Extract user ID from token"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    token = authorization.split(" ")[1]
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return payload.get("sub")


@router.get("/alerts", response_model=List[RadarAlertResponse])
async def get_radar_alerts(
    db_session = Depends(get_db_session),
    faculty: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    active_only: bool = Query(True)
):
    """Get radar alerts with optional filtering"""
    from app.core.db_wrapper import DatabaseWrapper
    db = DatabaseWrapper(db_session)
    
    # Build filters
    filters = {}
    if active_only:
        filters["is_active"] = True
    
    # Get all alerts with base filters
    alerts = db.select("radar_alerts", columns="*", filters=filters if filters else None)
    
    # Filter by faculty and level in Python (for OR conditions)
    filtered_alerts = []
    for alert in alerts:
        faculty_match = not faculty or not alert.get("target_faculty") or alert.get("target_faculty") == faculty
        level_match = not level or not alert.get("target_level") or alert.get("target_level") == level
        
        if faculty_match and level_match:
            filtered_alerts.append(alert)
    
    # Filter out expired alerts
    now = datetime.utcnow()
    active_alerts = []
    
    for alert in filtered_alerts:
        if alert.get("expires_at"):
            expires = datetime.fromisoformat(alert["expires_at"].replace("Z", "+00:00"))
            if expires > now:
                active_alerts.append(alert)
        else:
            active_alerts.append(alert)
    
    # Sort by created_at descending
    active_alerts.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    # Convert UUID objects to strings for Pydantic validation
    for alert in active_alerts:
        if 'id' in alert and hasattr(alert['id'], '__str__'):
            alert['id'] = str(alert['id'])
        if 'created_by' in alert and alert['created_by'] and hasattr(alert['created_by'], '__str__'):
            alert['created_by'] = str(alert['created_by'])
    
    return active_alerts[:50]


@router.get("/alerts/{alert_id}", response_model=RadarAlertResponse)
async def get_radar_alert(alert_id: str, db_session = Depends(get_db_session)):
    """Get single radar alert"""
    from app.core.db_wrapper import DatabaseWrapper
    db = DatabaseWrapper(db_session)
    result = db.select("radar_alerts", columns="*", filters={"id": alert_id})
    
    if not result:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    # Convert UUID to string for Pydantic validation
    alert_data = result[0]
    if 'id' in alert_data and hasattr(alert_data['id'], '__str__'):
        alert_data['id'] = str(alert_data['id'])
    if 'created_by' in alert_data and alert_data['created_by'] and hasattr(alert_data['created_by'], '__str__'):
        alert_data['created_by'] = str(alert_data['created_by'])
    
    return alert_data


@router.post("/alerts/{alert_id}/view")
async def mark_alert_viewed(
    alert_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """Mark alert as viewed by user"""
    db = get_db()
    
    # Check if already viewed
    existing = db.select("radar_views", columns="*", filters={"alert_id": alert_id, "user_id": user_id})
    
    if not existing:
        # Create view record
        db.insert("radar_views", {
            "user_id": user_id,
            "alert_id": alert_id,
            "viewed_at": datetime.utcnow().isoformat()
        })
        
        # Increment view count
        alert = db.select("radar_alerts", columns="views_count", filters={"id": alert_id})
        current_count = alert[0].get("views_count", 0) if alert else 0
        
        db.update("radar_alerts", {"views_count": current_count + 1}, {"id": alert_id})
    
    return {"message": "Alert marked as viewed"}


@router.get("/alerts/user/{user_id}/unread")
async def get_unread_alerts(user_id: str):
    """Get count of unread alerts for user"""
    db = get_db()
    
    # Get all active alerts
    all_alerts = db.select("radar_alerts", columns="id", filters={"is_active": True})
    
    # Get viewed alerts
    viewed = db.select("radar_views", columns="alert_id", filters={"user_id": user_id})
    viewed_ids = [v["alert_id"] for v in viewed]
    
    # Calculate unread
    unread_count = len([a for a in all_alerts if a["id"] not in viewed_ids])
    
    return {"unread_count": unread_count}
