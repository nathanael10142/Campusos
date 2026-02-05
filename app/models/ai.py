"""
AI request/response models
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum


class AIServiceType(str, Enum):
    """Types of AI services"""
    ORACLE = "oracle"  # General questions
    MINDMAP = "mindmap"  # Diagram generation
    VOICE = "voice"  # Text-to-speech
    SCHOLAR = "scholar"  # Academic search
    CODE_SOLVER = "code_solver"  # Code debugging
    PREDICTOR = "predictor"  # Exam prediction


class QuestionDifficulty(str, Enum):
    """Question difficulty levels"""
    SIMPLE = "simple"
    COMPLEX = "complex"


class AIQuestionRequest(BaseModel):
    """AI question request"""
    question: str = Field(..., min_length=10, max_length=2000)
    context: Optional[str] = None
    course: Optional[str] = None
    difficulty: QuestionDifficulty = QuestionDifficulty.SIMPLE
    language: str = "fr"  # French by default


class AIQuestionResponse(BaseModel):
    """AI question response"""
    question: str
    answer: str
    cost: float
    service: AIServiceType
    timestamp: datetime
    tokens_used: int


class MindMapRequest(BaseModel):
    """Mind map generation request"""
    topic: str = Field(..., min_length=5, max_length=200)
    context: Optional[str] = None
    format: str = "mermaid"  # Default format


class MindMapResponse(BaseModel):
    """Mind map response"""
    topic: str
    diagram_code: str
    format: str
    cost: float
    timestamp: datetime


class VoiceRequest(BaseModel):
    """Text-to-speech request"""
    text: str = Field(..., min_length=10, max_length=5000)
    voice: str = "nathanael"  # Default voice
    language: str = "fr"


class VoiceResponse(BaseModel):
    """Text-to-speech response"""
    audio_url: str
    duration: float
    cost: float
    timestamp: datetime


class ScholarSearchRequest(BaseModel):
    """Academic search request"""
    query: str = Field(..., min_length=5, max_length=200)
    max_results: int = Field(default=10, ge=1, le=50)
    year_from: Optional[int] = None


class ScholarPaper(BaseModel):
    """Academic paper result"""
    title: str
    authors: List[str]
    year: Optional[int]
    abstract: Optional[str]
    url: Optional[str]
    pdf_url: Optional[str]
    citations: int


class ScholarSearchResponse(BaseModel):
    """Academic search response"""
    query: str
    results: List[ScholarPaper]
    count: int
    cost: float
    timestamp: datetime


class CodeSolverRequest(BaseModel):
    """Code debugging request"""
    code: str = Field(..., min_length=10, max_length=10000)
    language: str = "python"
    problem_description: Optional[str] = None


class CodeSolverResponse(BaseModel):
    """Code debugging response"""
    original_code: str
    fixed_code: str
    explanation: str
    suggestions: List[str]
    cost: float
    timestamp: datetime


class PredictorRequest(BaseModel):
    """Exam prediction request"""
    course: str
    faculty: str
    academic_level: str


class PredictorResponse(BaseModel):
    """Exam prediction response"""
    course: str
    predicted_date: Optional[str]
    confidence: float
    reasoning: str
    cost: float
    timestamp: datetime


class AIUsageStats(BaseModel):
    """AI usage statistics for a user"""
    total_questions: int
    total_spent: float
    services_used: Dict[str, int]
    last_used: Optional[datetime]
