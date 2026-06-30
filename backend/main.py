import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from rag import rag_answer
from utils import scan_available_workflows

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

# Vite dev server runs on 5173 by default — allow it to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The user's question")
    top_k: int = Field(default=8, ge=1, le=20, description="Number of chunks to retrieve")


class SourceItem(BaseModel):
    workflow: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceItem]


class FeedbackRequest(BaseModel):
    message_id: str = Field(..., description="Frontend-generated id for the message")
    type: str = Field(..., description="'up', 'down', or 'comment'")
    comment: str | None = Field(default=None, description="Optional free text feedback")


class FeedbackResponse(BaseModel):
    status: str


class WorkflowsResponse(BaseModel):
    workflows: list[str]


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
    """
    Returns the list of available workflow display names, derived dynamically
    from the markdown files in the data directory — no hardcoded list.
    """
    workflow_map = scan_available_workflows()
    display_names = sorted(
        slug.replace("_", " ").title() for slug in workflow_map.keys()
    )
    return WorkflowsResponse(workflows=display_names)


@app.post("/api/feedback", response_model=FeedbackResponse)
def submit_feedback(payload: FeedbackRequest) -> FeedbackResponse:
    """
    Accepts user feedback (thumbs up/down/comment) on a message.
    Currently just logs it — wire to a database later.
    """
    if payload.type not in ("up", "down", "comment"):
        raise HTTPException(status_code=400, detail="type must be 'up', 'down', or 'comment'.")

    logger.info(
        "Feedback received | message_id=%s | type=%s | comment=%s",
        payload.message_id,
        payload.type,
        payload.comment,
    )

    # TODO: persist to database once one is connected
    return FeedbackResponse(status="received")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)