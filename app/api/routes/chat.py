from fastapi import APIRouter

from app.core.agent import run_agent
from app.models.schemas import ChatRequest, ChatResponse
from app.utils.logger import get_logger

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])
logger = get_logger(__name__)

# In-memory session history (in production, use Redis or Firestore)
chat_histories: dict[str, list[dict[str, str]]] = {}

@router.post("/", response_model=ChatResponse)
async def chat_with_agent(request: ChatRequest):
    """
    Send a natural language message to the Retail Analytics Agent.
    The agent can query inventory, generate forecasts, create reports,
    extract data from pasted text, and provide insights.
    """
    session_id = request.session_id or "default"
    
    # Retrieve or initialize chat history
    history = chat_histories.get(session_id, [])
    
    # Keep last 10 messages for context window management
    history = history[-10:]
    
    logger.info("chat_request", session_id=session_id, message_length=len(request.message))
    
    try:
        result = run_agent(
            message=request.message,
            chat_history=history,
        )
        
        # Update history
        history.append({"role": "user", "content": request.message})
        history.append({"role": "assistant", "content": result["response"]})
        chat_histories[session_id] = history
        
        return ChatResponse(
            response=result["response"],
            session_id=session_id,
            tools_used=result["tools_used"],
            data=None, # Could parse structured data from response if needed
            intermediate_steps=result.get("intermediate_steps"),
        )
        
    except Exception as e:
        logger.error("chat_error", session_id=session_id, error=str(e))
        return ChatResponse(
            response=f"I'm sorry, I encountered an error while processing your request: {str(e)}",
            session_id=session_id,
            tools_used=[],
        )