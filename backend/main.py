import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from rag import rag_answer, memory_file_path
from utils import scan_available_workflows, get_index_path, build_embeddings
import db

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Telecom Workflow Navigator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    db.init_db()
    logger.info("SQLite database ready at %s", db.DB_PATH)


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=3, ge=1, le=20)
    session_id: str = Field(
        default="default",
        description="Frontend-generated session id, forwarded to Langfuse for trace grouping.",
    )


class SourceItem(BaseModel):
    workflow: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceItem]


class FeedbackRequest(BaseModel):
    message_id: str = Field(..., description="Frontend-generated id for the message")
    type: str = Field(..., description="'up', 'down', or 'comment'")
    comment: str | None = Field(default=None)
    session_id: str = Field(default="default", description="Session this feedback belongs to")
    question: str | None = Field(default=None, description="The user question this feedback is about")
    answer: str | None = Field(default=None, description="The assistant answer this feedback is about")


class FeedbackResponse(BaseModel):
    status: str
    id: int | None = None


class FeedbackItem(BaseModel):
    id: int
    session_id: str
    message_id: str
    type: str
    comment: str | None
    question: str | None
    answer: str | None
    created_at: str


class FeedbackListResponse(BaseModel):
    feedback: list[FeedbackItem]
    counts: dict[str, int]


class WorkflowsResponse(BaseModel):
    workflows: list[str]


class HistoryResponse(BaseModel):
    status: str


class IndexStatusResponse(BaseModel):
    status: str
    index_exists: bool
    total_chunks: int | None
    workflows_indexed: int | None
    embedding_model: str
    memory_turns: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    logger.info(
        "Received question: %s | session_id=%s", question, payload.session_id
    )

    try:
        result = rag_answer(
            question,
            top_k=payload.top_k,
            session_id=payload.session_id,
        )
    except Exception:
        logger.exception("rag_answer() failed for question: %s", question)
        raise HTTPException(status_code=500, detail="Something went wrong while answering the question.")

    if result.get("error") == "index_not_found":
        raise HTTPException(
            status_code=503,
            detail="The workflow index is not ready yet. Run ingest.py first.",
        )

    return AskResponse(
        answer=result["answer"],
        sources=[SourceItem(**source) for source in result["sources"]],
    )


@app.get("/api/workflows", response_model=WorkflowsResponse)
def get_workflows() -> WorkflowsResponse:
    """Returns available workflow display names from data/ directory dynamically."""
    workflow_map = scan_available_workflows()
    display_names = sorted(
        slug.replace("_", " ").title() for slug in workflow_map.keys()
    )
    return WorkflowsResponse(workflows=display_names)


@app.post("/api/feedback", response_model=FeedbackResponse)
def submit_feedback(payload: FeedbackRequest) -> FeedbackResponse:
    """Accepts user feedback on a message and persists it to SQLite."""
    if payload.type not in ("up", "down", "comment"):
        raise HTTPException(status_code=400, detail="type must be 'up', 'down', or 'comment'.")

    logger.info(
        "Feedback | session_id=%s | message_id=%s | type=%s | comment=%s",
        payload.session_id,
        payload.message_id,
        payload.type,
        payload.comment,
    )

    try:
        new_id = db.insert_feedback(
            session_id=payload.session_id,
            message_id=payload.message_id,
            type_=payload.type,
            comment=payload.comment,
            question=payload.question,
            answer=payload.answer,
        )
    except Exception:
        logger.exception("Failed to persist feedback to SQLite.")
        raise HTTPException(status_code=500, detail="Could not save feedback.")

    return FeedbackResponse(status="received", id=new_id)


@app.get("/api/feedback", response_model=FeedbackListResponse)
def list_feedback(session_id: str | None = None, limit: int = 100) -> FeedbackListResponse:
    """
    Returns recent feedback, newest first. Pass ?session_id=... to see one
    conversation's feedback only; omit it to see everything (demo/admin view).
    """
    rows = db.fetch_feedback(session_id=session_id, limit=limit)
    counts = db.feedback_counts()
    return FeedbackListResponse(feedback=rows, counts=counts)


@app.delete("/api/history", response_model=HistoryResponse)
def clear_history(session_id: str = "default") -> HistoryResponse:
    """
    Clears the server-side chat memory for one session only
    (memory/rag_memory_<session_id>.json). Other users' / other
    sessions' history is untouched.
    Called when user clicks New Chat so the next conversation
    starts with a completely clean context window.
    """
    path = memory_file_path(session_id)
    try:
        if path.exists():
            path.write_text("[]", encoding="utf-8")
            logger.info("Chat memory cleared for session_id=%s", session_id)
        else:
            logger.info("No chat memory found for session_id=%s — nothing to clear.", session_id)
    except Exception:
        logger.exception("Failed to clear chat memory for session_id=%s", session_id)
        raise HTTPException(status_code=500, detail="Could not clear chat history.")

    return HistoryResponse(status="cleared")


@app.get("/api/index/status", response_model=IndexStatusResponse)
def index_status(session_id: str = "default") -> IndexStatusResponse:
    """
    Returns real information about the FAISS index.
    Powers the header status badge and is useful for the panel demo.
    memory_turns reflects the given session's memory file (defaults to
    the "default" session if none is passed).
    """
    index_path = get_index_path()
    embedding_model = os.getenv(
        "EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5"
    )

    # Check memory turns for this session
    memory_path = memory_file_path(session_id)
    memory_turns = 0
    if memory_path.exists():
        import json
        try:
            data = json.loads(memory_path.read_text(encoding="utf-8"))
            memory_turns = len(data) if isinstance(data, list) else 0
        except Exception:
            memory_turns = 0

    if not index_path.exists():
        return IndexStatusResponse(
            status="index_not_found",
            index_exists=False,
            total_chunks=None,
            workflows_indexed=None,
            embedding_model=embedding_model,
            memory_turns=memory_turns,
        )

    # Load FAISS index to get chunk count
    try:
        from utils import load_vectorstore
        vectorstore = load_vectorstore(index_path)
        total_chunks = vectorstore.index.ntotal
    except Exception:
        total_chunks = None

    # Count workflows from data directory
    workflow_map = scan_available_workflows()
    workflows_indexed = len(workflow_map)

    return IndexStatusResponse(
        status="ok",
        index_exists=True,
        total_chunks=total_chunks,
        workflows_indexed=workflows_indexed,
        embedding_model=embedding_model,
        memory_turns=memory_turns,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)