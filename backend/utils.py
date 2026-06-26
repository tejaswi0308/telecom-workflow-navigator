from pathlib import Path
import re

from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

load_dotenv()


def build_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(   
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
    )


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def clean_section_title(title: str) -> str:
    """Strip leading numbering (e.g. '1. ') from a markdown section title."""
    return re.sub(r"^\d+\.\s*", "", title).strip()


def get_data_directory() -> Path:
    """Returns the path to the data directory containing Markdown workflows."""
    return Path(__file__).resolve().parent.parent / "data"


def get_index_path() -> Path:
    backend_dir = Path(__file__).resolve().parent
    return backend_dir.parent / "faiss_index"


def load_vectorstore(index_path: Path) -> FAISS:
    if not index_path.exists():
        raise FileNotFoundError(
            f"FAISS index not found at {index_path}. Run ingest.py first."
        )

    return FAISS.load_local(
        str(index_path),
        build_embeddings(),
        allow_dangerous_deserialization=True,
    )


def strip_markdown_formatting(text: str) -> str:
    """Remove markdown formatting markers (**, *, etc.) from text."""
    return re.sub(r"\*\*(.*?)\*\*", r"\1", text).replace("*", "")


_workflow_map_cache: dict[str, list[Path]] | None = None

def scan_available_workflows() -> dict[str, list[Path]]:
    global _workflow_map_cache
    if _workflow_map_cache is not None:
        return _workflow_map_cache
    
    data_dir = get_data_directory()
    workflow_map = {}
    if not data_dir.exists():
        return workflow_map
    for file_path in data_dir.glob("*.md"):
        slug = file_path.stem.lower().replace("_workflow", "")
        if slug not in workflow_map:
            workflow_map[slug] = []
        workflow_map[slug].append(file_path)
    
    _workflow_map_cache = workflow_map
    return _workflow_map_cache


def infer_workflow_type(question: str) -> str | None:
    """
    Dynamically infers the target workflow by calculating the mathematical intersection
    between the unique words in the user's query and the actual discovered filenames.
    """
    query_words = set(normalize_text(question).split())

    workflow_map = scan_available_workflows()
    matches: list[tuple[int, str]] = []

    for slug in workflow_map.keys():
        # Split slug into words — e.g. "elevar_sr_cancellation" → {"elevar", "sr", "cancellation"}
        slug_words = set(slug.split("_"))

        score = len(query_words & slug_words)
        if score > 0:
            matches.append((score, slug))

    if not matches:
        return None

    # Sort primarily by token match score (descending), secondary by character length (descending)
    matches.sort(key=lambda item: (item[0], len(item[1])), reverse=True)

    # If the top match has a strictly higher token score than the second match, return it immediately
    if len(matches) == 1 or matches[0][0] > matches[1][0]:
        return matches[0][1]

    # Handle a true token score tie
    if matches[0][0] == matches[1][0]:
        tied = [m for m in matches if m[0] == matches[0][0]]
        # Prefer the longer/more specific file slug name
        tied.sort(key=lambda m: len(m[1]), reverse=True)
        
        if len(tied[0][1]) > len(tied[1][1]):
            return tied[0][1]
            
    return None


def workflow_markdown_path(workflow_type: str) -> Path | None:
    """Dynamically resolves a workflow type slug back to its absolute markdown file path."""
    workflow_map = scan_available_workflows()
    candidates = workflow_map.get(workflow_type, [])

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # Fallback glob matching if slugs diverge slightly
    data_dir = get_data_directory()
    slug = re.sub(r"[^a-z0-9]+", "_", workflow_type.lower()).strip("_")
    matches = sorted(data_dir.glob(f"*{slug}*.md"))
    return matches[0] if matches else None


def build_retrieval_queries(question: str) -> list[str]:
    """Return neutral domain query variants to enrich dense retrieval matching."""
    lowered = question.lower().strip()
    queries = [question]
    expansions: list[str] = []

    if any(keyword in lowered for keyword in ("sop", "procedure", "workflow", "steps")):
        expansions.append("procedure sequencing milestones deployment steps")

    if any(keyword in lowered for keyword in ("antenna", "tower", "equipment", "loading")):
        expansions.append("structural upgrade technical criteria physical assets verification")

    if any(keyword in lowered for keyword in ("billing", "commercial", "commercial trigger", "revenue")):
        expansions.append("financial activation ledger sync account clearance transactional state")

    if any(keyword in lowered for keyword in ("edge case", "exception", "what if", "if rejected", "fallback")):
        expansions.append("rejection routing error state condition path logic rollback loop")

    if any(keyword in lowered for keyword in ("cancellation", "cancel", "termination", "tenancy")):
        expansions.append("administrative teardown contract termination deactivation record closure")

    if any(keyword in lowered for keyword in ("share", "sharing")):
        expansions.append("co-location allocation technical review parameter authorization")

    if any(keyword in lowered for keyword in ("disconnect", "reconnect", "hold", "unhold")):
        expansions.append("temporary suspension restoration status code intervention utility state")

    # Approval hierarchy queries — enrich with actor and chain terminology
    if any(keyword in lowered for keyword in ("approval", "hierarchy", "chain", "corporate", "executive", "actor", "approves", "who")):
        expansions.append("approval chain actors roles authorization decision hierarchy escalation")

    for expansion in expansions:
        expanded_query = f"{question} {expansion}"
        if expanded_query not in queries:
            queries.append(expanded_query)

    return queries


def merge_scored_results(scored_results, top_k: int):
    """Merge duplicate documents from multiple queries and keep the best score."""
    best_by_key = {}

    for document, score in scored_results:
        workflow = document.metadata.get("workflow", "Unknown")
        source = document.metadata.get("source", workflow)
        key = (workflow, source, document.page_content.strip())
        current = best_by_key.get(key)
        if current is None or score < current[1]:
            best_by_key[key] = (document, score)

    merged = sorted(best_by_key.values(), key=lambda item: item[1])
    return merged[:top_k]