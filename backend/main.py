import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from rag import rag_answer, memory_file_path
from utils import scan_available_workflows, get_index_path, build_embeddings

# Logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# App
app = FastAPI(title="Telecom Workflow Navigator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request / Response Models
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=8, ge=1, le=20)


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


class FeedbackResponse(BaseModel):
    status: str


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



# Routes
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    logger.info("Received question: %s", question)

    try:
        result = rag_answer(question, top_k=payload.top_k)
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
    """Accepts user feedback on a message. Logs it now, wire to DB later."""
    if payload.type not in ("up", "down", "comment"):
        raise HTTPException(status_code=400, detail="type must be 'up', 'down', or 'comment'.")

    logger.info(
        "Feedback | message_id=%s | type=%s | comment=%s",
        payload.message_id,
        payload.type,
        payload.comment,
    )

    # TODO: persist to database once connected
    return FeedbackResponse(status="received")


@app.delete("/api/history", response_model=HistoryResponse)
def clear_history() -> HistoryResponse:
    """
    Clears the server-side chat memory (rag_memory.json).
    Called when user clicks New Chat so the next conversation
    starts with a completely clean context window.
    """
    path = memory_file_path()
    try:
        if path.exists():
            path.write_text("[]", encoding="utf-8")
            logger.info("Chat memory cleared.")
        else:
            logger.info("Chat memory file does not exist — nothing to clear.")
    except Exception:
        logger.exception("Failed to clear chat memory.")
        raise HTTPException(status_code=500, detail="Could not clear chat history.")

    return HistoryResponse(status="cleared")


@app.get("/api/index/status", response_model=IndexStatusResponse)
def index_status() -> IndexStatusResponse:
    """
    Returns real information about the FAISS index.
    Powers the header status badge and is useful for the panel demo.
    """
    index_path = get_index_path()
    embedding_model = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )

    # Check memory turns
    memory_path = memory_file_path()
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