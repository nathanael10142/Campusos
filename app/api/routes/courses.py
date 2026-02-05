"""
Courses and syllabus routes
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import List
from pydantic import BaseModel
from app.core.database import get_db_session
from app.core.security import decode_token

router = APIRouter()


class Course(BaseModel):
    id: str
    name: str
    code: str
    faculty: str
    academic_level: str
    professor: str
    description: str


class CoursesResponse(BaseModel):
    courses: List[Course]


class SyllabusFile(BaseModel):
    id: str
    course_id: str
    title: str
    file_url: str
    file_type: str
    uploaded_at: str


def get_current_user_id(authorization: str = Header(...)) -> str:
    """Extract user ID from token"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    token = authorization.split(" ")[1]
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return payload.get("sub")


@router.get("", response_model=CoursesResponse)
async def list_courses(
    db_session = Depends(get_db_session),
    faculty: str = None,
    academic_level: str = None,
    level: str = None,  # Alias for academic_level
    page: int = 1,
    limit: int = 20
):
    """List available courses"""
    from app.core.db_wrapper import DatabaseWrapper
    db = DatabaseWrapper(db_session)
    
    filters = {}
    if faculty:
        filters["faculty"] = faculty
    
    # Use academic_level from either parameter
    level_filter = academic_level or level
    if level_filter:
        filters["academic_level"] = level_filter
    
    result = db.select("courses", columns="*", filters=filters if filters else None)
    
    # Simple pagination (since no database-level pagination implemented)
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_result = result[start_idx:end_idx]
    
    # Convert UUID objects to strings for Pydantic validation
    for course in paginated_result:
        if 'id' in course and hasattr(course['id'], '__str__'):
            course['id'] = str(course['id'])
    
    return {"courses": paginated_result}


@router.get("/{course_id}", response_model=Course)
async def get_course(
    course_id: str,
    db_session = Depends(get_db_session)
):
    """Get course details"""
    from app.core.db_wrapper import DatabaseWrapper
    db = DatabaseWrapper(db_session)
    course = db.select("courses", columns="*", filters={"id": course_id})
    
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Convert UUID to string for Pydantic validation
    course_data = course[0]
    if 'id' in course_data and hasattr(course_data['id'], '__str__'):
        course_data['id'] = str(course_data['id'])
    
    return course_data


@router.get("/{course_id}/syllabus", response_model=List[SyllabusFile])
async def get_course_syllabus(
    course_id: str,
    db_session = Depends(get_db_session)
):
    """Get course syllabus files"""
    from app.core.db_wrapper import DatabaseWrapper
    db = DatabaseWrapper(db_session)
    files = db.select("syllabus", columns="*", filters={"course_id": course_id})
    
    # Convert UUID objects to strings for Pydantic validation
    for file in files:
        if 'id' in file and hasattr(file['id'], '__str__'):
            file['id'] = str(file['id'])
        if 'course_id' in file and hasattr(file['course_id'], '__str__'):
            file['course_id'] = str(file['course_id'])
    
    return files
