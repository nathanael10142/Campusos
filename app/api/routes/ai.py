"""
AI services routes - Le moteur Batera Intelligence
"""

from fastapi import APIRouter, HTTPException, status, Depends, Header
from app.models.ai import (
    AIQuestionRequest, AIQuestionResponse, AIServiceType,
    MindMapRequest, MindMapResponse,
    VoiceRequest, VoiceResponse,
    ScholarSearchRequest, ScholarSearchResponse, ScholarPaper,
    CodeSolverRequest, CodeSolverResponse,
    PredictorRequest, PredictorResponse
)
from app.core.database import get_db
from app.core.security import decode_token
from app.core.config import settings
import google.generativeai as genai
from datetime import datetime
from loguru import logger
import httpx

router = APIRouter()

# Configure Google AI
genai.configure(api_key=settings.GOOGLE_AI_API_KEY)


def get_current_user_id(authorization: str = Header(...)) -> str:
    """Extract user ID from token"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    token = authorization.split(" ")[1]
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return payload.get("sub")


def check_user_balance(user_id: str, cost: float):
    """Check if user has enough Batera Coins"""
    db = get_db()
    user = db.table("users").select("batera_coins").eq("id", user_id).execute()
    
    if not user.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    balance = user.data[0]["batera_coins"]
    
    if balance < cost:
        raise HTTPException(
            status_code=402,
            detail=f"Solde insuffisant. Vous avez {balance} Batera Coins mais cette action coûte {cost} Coins."
        )
    
    return balance


def deduct_coins(user_id: str, cost: float):
    """Deduct Batera Coins from user"""
    db = get_db()
    user = db.table("users").select("batera_coins").eq("id", user_id).execute()
    current_balance = user.data[0]["batera_coins"]
    new_balance = current_balance - cost
    
    db.table("users").update({"batera_coins": new_balance}).eq("id", user_id).execute()
    
    # Log transaction
    db.table("transactions").insert({
        "user_id": user_id,
        "type": "debit",
        "amount": cost,
        "description": "Service IA utilisé",
        "created_at": datetime.utcnow().isoformat()
    }).execute()


@router.post("/oracle", response_model=AIQuestionResponse)
async def ask_oracle(
    request: AIQuestionRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Pose une question à Oracle (l'IA Batera)
    """
    cost = 0.5 if request.difficulty == "simple" else 1.0
    
    # Check balance
    check_user_balance(user_id, cost)
    
    try:
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-pro')
        
        # Construct prompt with local context
        system_prompt = """Tu es Oracle, l'assistant IA de Campus OS UNIGOM développé par Nathanael Batera Akilimali. 
        Tu aides les étudiants de l'Université de Goma (UNIGOM) avec leurs études. 
        Réponds en français, de manière claire et pédagogique. 
        Utilise parfois des expressions locales comme 'Kaka' (frère) pour créer de la proximité.
        N'oublie jamais que tu es l'intelligence Batera, conçue à Goma."""
        
        user_prompt = f"""Question de l'étudiant: {request.question}
        
Contexte: {request.context or 'Aucun contexte fourni'}
Cours: {request.course or 'Non spécifié'}

Fournis une réponse détaillée et pédagogique."""
        
        # Generate response
        response = model.generate_content(f"{system_prompt}\n\n{user_prompt}")
        answer_text = response.text
        
        # Clean response to remove any Google branding
        answer_text = answer_text.replace("Google", "Batera")
        answer_text = answer_text.replace("Gemini", "Oracle")
        
        # Deduct coins
        deduct_coins(user_id, cost)
        
        # Log AI usage
        db = get_db()
        db.table("ai_usage").insert({
            "user_id": user_id,
            "service": AIServiceType.ORACLE.value,
            "question": request.question,
            "response": answer_text,
            "cost": cost,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        
        logger.info(f"✅ Oracle question answered for user {user_id}")
        
        return AIQuestionResponse(
            question=request.question,
            answer=answer_text,
            cost=cost,
            service=AIServiceType.ORACLE,
            timestamp=datetime.utcnow(),
            tokens_used=len(answer_text.split())
        )
        
    except Exception as e:
        logger.error(f"Oracle error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erreur de calcul dans le noyau Batera v15. Nathanael a été notifié."
        )


@router.post("/mindmap", response_model=MindMapResponse)
async def generate_mindmap(
    request: MindMapRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Génère un diagramme Batera MindMap
    """
    cost = 1.0
    check_user_balance(user_id, cost)
    
    try:
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = f"""Génère un diagramme Mermaid.js pour visualiser ce sujet: {request.topic}
        
Contexte: {request.context or 'Aucun'}

Crée un diagramme de type flowchart ou mindmap qui structure l'information de manière claire et logique.
Retourne UNIQUEMENT le code Mermaid, sans explications."""
        
        response = model.generate_content(prompt)
        diagram_code = response.text.strip()
        
        # Extract only Mermaid code if wrapped in markdown
        if "```mermaid" in diagram_code:
            diagram_code = diagram_code.split("```mermaid")[1].split("```")[0].strip()
        elif "```" in diagram_code:
            diagram_code = diagram_code.split("```")[1].split("```")[0].strip()
        
        deduct_coins(user_id, cost)
        
        # Log usage
        db = get_db()
        db.table("ai_usage").insert({
            "user_id": user_id,
            "service": AIServiceType.MINDMAP.value,
            "question": request.topic,
            "response": diagram_code,
            "cost": cost,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        
        return MindMapResponse(
            topic=request.topic,
            diagram_code=diagram_code,
            format="mermaid",
            cost=cost,
            timestamp=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"MindMap error: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la génération du diagramme")


@router.post("/scholar", response_model=ScholarSearchResponse)
async def search_scholar(
    request: ScholarSearchRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Recherche académique Batera Scholar Search
    """
    cost = 2.0
    check_user_balance(user_id, cost)
    
    try:
        # Use Semantic Scholar API (free)
        async with httpx.AsyncClient() as client:
            url = "https://api.semanticscholar.org/graph/v1/paper/search"
            params = {
                "query": request.query,
                "limit": request.max_results,
                "fields": "title,authors,year,abstract,url,citationCount"
            }
            
            if request.year_from:
                params["year"] = f"{request.year_from}-"
            
            response = await client.get(url, params=params, timeout=30.0)
            data = response.json()
        
        papers = []
        for paper in data.get("data", []):
            papers.append(ScholarPaper(
                title=paper.get("title", ""),
                authors=[a.get("name", "") for a in paper.get("authors", [])],
                year=paper.get("year"),
                abstract=paper.get("abstract"),
                url=paper.get("url"),
                pdf_url=paper.get("openAccessPdf", {}).get("url") if paper.get("openAccessPdf") else None,
                citations=paper.get("citationCount", 0)
            ))
        
        deduct_coins(user_id, cost)
        
        # Log usage
        db = get_db()
        db.table("ai_usage").insert({
            "user_id": user_id,
            "service": AIServiceType.SCHOLAR.value,
            "question": request.query,
            "response": f"{len(papers)} papers found",
            "cost": cost,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        
        return ScholarSearchResponse(
            query=request.query,
            results=papers,
            count=len(papers),
            cost=cost,
            timestamp=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"Scholar search error: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la recherche académique")


@router.post("/code-solver", response_model=CodeSolverResponse)
async def solve_code(
    request: CodeSolverRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Batera Code-Solver: Déboggage et correction de code
    """
    cost = 1.0
    check_user_balance(user_id, cost)
    
    try:
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = f"""Tu es un expert en programmation {request.language}. 
        
Analyse ce code et corrige les erreurs:

```{request.language}
{request.code}
```

Problème décrit: {request.problem_description or 'Aucune description'}

Fournis:
1. Le code corrigé
2. Une explication des erreurs trouvées
3. Des suggestions d'amélioration

Format ta réponse ainsi:
### CODE CORRIGÉ
[code corrigé ici]

### EXPLICATION
[explication ici]

### SUGGESTIONS
- [suggestion 1]
- [suggestion 2]
"""
        
        response = model.generate_content(prompt)
        result = response.text
        
        # Parse response
        parts = result.split("###")
        fixed_code = request.code  # Default
        explanation = ""
        suggestions = []
        
        for part in parts:
            if "CODE CORRIGÉ" in part or "CODE CORRIGE" in part:
                fixed_code = part.split("```")[1].strip() if "```" in part else part.strip()
            elif "EXPLICATION" in part:
                explanation = part.replace("EXPLICATION", "").strip()
            elif "SUGGESTIONS" in part:
                sugg_text = part.replace("SUGGESTIONS", "").strip()
                suggestions = [s.strip("- ").strip() for s in sugg_text.split("\n") if s.strip()]
        
        deduct_coins(user_id, cost)
        
        # Log usage
        db = get_db()
        db.table("ai_usage").insert({
            "user_id": user_id,
            "service": AIServiceType.CODE_SOLVER.value,
            "question": f"Code debug: {request.language}",
            "response": explanation,
            "cost": cost,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        
        return CodeSolverResponse(
            original_code=request.code,
            fixed_code=fixed_code,
            explanation=explanation,
            suggestions=suggestions[:5],  # Max 5
            cost=cost,
            timestamp=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"Code solver error: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de l'analyse du code")


@router.post("/predictor", response_model=PredictorResponse)
async def predict_exam(
    request: PredictorRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Batera Predictor: Prédiction des dates d'examens
    """
    cost = 3.0
    check_user_balance(user_id, cost)
    
    try:
        # Get historical data
        db = get_db()
        history = db.table("exam_history").select("*").eq("course", request.course).eq("faculty", request.faculty).execute()
        
        model = genai.GenerativeModel('gemini-pro')
        
        history_text = "\n".join([f"- {h['date']}: {h['type']}" for h in history.data]) if history.data else "Aucun historique disponible"
        
        prompt = f"""Tu es un système de prédiction des examens pour l'UNIGOM.

Cours: {request.course}
Faculté: {request.faculty}
Niveau: {request.academic_level}

Historique des examens passés:
{history_text}

Sur base de l'historique et du calendrier académique typique congolais (3 sessions par an), 
prédis la date probable du prochain examen.

Format ta réponse:
DATE: [date prédite au format YYYY-MM-DD ou "Indéterminé"]
CONFIANCE: [pourcentage]
RAISONNEMENT: [explication courte]
"""
        
        response = model.generate_content(prompt)
        result = response.text
        
        # Parse response
        predicted_date = None
        confidence = 0.5
        reasoning = result
        
        for line in result.split("\n"):
            if "DATE:" in line:
                predicted_date = line.split("DATE:")[1].strip()
            elif "CONFIANCE:" in line:
                conf_str = line.split("CONFIANCE:")[1].strip().replace("%", "")
                try:
                    confidence = float(conf_str) / 100
                except:
                    confidence = 0.5
            elif "RAISONNEMENT:" in line:
                reasoning = line.split("RAISONNEMENT:")[1].strip()
        
        deduct_coins(user_id, cost)
        
        # Log usage
        db.table("ai_usage").insert({
            "user_id": user_id,
            "service": AIServiceType.PREDICTOR.value,
            "question": f"Prediction: {request.course}",
            "response": predicted_date or "Indéterminé",
            "cost": cost,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        
        return PredictorResponse(
            course=request.course,
            predicted_date=predicted_date,
            confidence=confidence,
            reasoning=reasoning,
            cost=cost,
            timestamp=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"Predictor error: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la prédiction")
