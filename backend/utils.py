import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — all tuneable via environment variables
# ---------------------------------------------------------------------------
EMBEDDING_MODEL      = os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5")
EMBEDDING_DEVICE     = os.getenv("EMBEDDING_DEVICE", "cpu")
RERANKER_MODEL       = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-large")
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.7"))
RRF_K                = int(os.getenv("RRF_K", "60"))


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------
def build_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": EMBEDDING_DEVICE},
        encode_kwargs={"normalize_embeddings": True},  # required for cosine similarity
    )


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------
def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def clean_section_title(title: str) -> str:
    """Strip leading numbering (e.g. '1. ') from a markdown section title."""
    return re.sub(r"^\d+\.\s*", "", title).strip()


def strip_markdown_formatting(text: str) -> str:
    """Remove markdown formatting markers (**, *, etc.) from text."""
    return re.sub(r"\*\*(.*?)\*\*", r"\1", text).replace("*", "")


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def get_data_directory() -> Path:
    """Returns the path to the data directory containing Markdown workflows."""
    return Path(__file__).resolve().parent.parent / "data"


def get_index_path() -> Path:
    backend_dir = Path(__file__).resolve().parent
    return backend_dir.parent / "faiss_index"


# ---------------------------------------------------------------------------
# Vector store — cosine similarity via normalized embeddings + inner product
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Workflow discovery
# ---------------------------------------------------------------------------
_workflow_map_cache: dict[str, list[Path]] | None = None


def scan_available_workflows() -> dict[str, list[Path]]:
    global _workflow_map_cache
    if _workflow_map_cache is not None:
        return _workflow_map_cache

    data_dir = get_data_directory()
    workflow_map: dict[str, list[Path]] = {}

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
    Dynamically infers the target workflow by calculating the intersection
    between the unique words in the user's query and the actual discovered filenames.
    """
    query_words = set(normalize_text(question).split())
    workflow_map = scan_available_workflows()
    matches: list[tuple[int, str]] = []

    for slug in workflow_map.keys():
        slug_words = set(slug.split("_"))
        score = len(query_words & slug_words)
        if score > 0:
            matches.append((score, slug))

    if not matches:
        return None

    matches.sort(key=lambda item: (item[0], len(item[1])), reverse=True)

    if len(matches) == 1 or matches[0][0] > matches[1][0]:
        return matches[0][1]

    if matches[0][0] == matches[1][0]:
        tied = [m for m in matches if m[0] == matches[0][0]]
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

    data_dir = get_data_directory()
    slug = re.sub(r"[^a-z0-9]+", "_", workflow_type.lower()).strip("_")
    matches = sorted(data_dir.glob(f"*{slug}*.md"))
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# Query expansion
# ---------------------------------------------------------------------------
def build_retrieval_queries(question: str) -> list[str]:
    """Return domain query variants to enrich dense retrieval matching."""
    lowered = question.lower().strip()
    queries = [question]
    expansions: list[str] = []

    if any(k in lowered for k in ("sop", "procedure", "workflow", "steps")):
        expansions.append("procedure sequencing milestones deployment steps")

    if any(k in lowered for k in ("antenna", "tower", "equipment", "loading")):
        expansions.append("structural upgrade technical criteria physical assets verification")

    if any(k in lowered for k in ("billing", "commercial", "commercial trigger", "revenue")):
        expansions.append("financial activation ledger sync account clearance transactional state")

    if any(k in lowered for k in ("edge case", "exception", "what if", "if rejected", "fallback")):
        expansions.append("rejection routing error state condition path logic rollback loop")

    if any(k in lowered for k in ("cancellation", "cancel", "termination", "tenancy")):
        expansions.append("administrative teardown contract termination deactivation record closure")

    if any(k in lowered for k in ("share", "sharing")):
        expansions.append("co-location allocation technical review parameter authorization")

    if any(k in lowered for k in ("disconnect", "reconnect", "hold", "unhold")):
        expansions.append("temporary suspension restoration status code intervention utility state")

    if any(k in lowered for k in ("approval", "hierarchy", "chain", "corporate", "executive", "actor", "approves", "who")):
        expansions.append("approval chain actors roles authorization decision hierarchy escalation")

    for expansion in expansions:
        expanded = f"{question} {expansion}"
        if expanded not in queries:
            queries.append(expanded)

    return queries


# ---------------------------------------------------------------------------
# BM25 retrieval
# ---------------------------------------------------------------------------
def build_bm25_retriever(documents: list, top_k: int):
    """
    Builds a BM25 keyword retriever from a list of LangChain documents.
    Returns None if rank_bm25 is not installed.
    """
    try:
        from langchain_community.retrievers import BM25Retriever
        retriever = BM25Retriever.from_documents(documents, k=top_k)
        return retriever
    except ImportError:
        logger.warning("rank_bm25 not installed — BM25 retrieval disabled. pip install rank_bm25")
        return None


def bm25_search(query: str, documents: list, top_k: int) -> list[tuple]:
    """
    Runs BM25 keyword search over documents using BM25Okapi directly.
    Returns real BM25 scores — higher = better.
    """
    if not documents:
        return []

    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        logger.warning("rank_bm25 not installed — BM25 retrieval disabled. pip install rank_bm25")
        return []

    tokenized_corpus = [doc.page_content.lower().split() for doc in documents]
    bm25 = BM25Okapi(tokenized_corpus)
    tokenized_query = query.lower().split()
    scores = bm25.get_scores(tokenized_query)

    doc_scores = sorted(
        zip(documents, scores),
        key=lambda x: x[1],
        reverse=True,
    )
    return [(doc, float(score)) for doc, score in doc_scores[:top_k]]


# ---------------------------------------------------------------------------
# RRF merge — combines dense + BM25 ranked lists
# ---------------------------------------------------------------------------
def merge_rrf(
    all_result_lists: list[list[tuple]],
    top_k: int,
    k: int = RRF_K,
) -> list[tuple]:
    """
    Reciprocal Rank Fusion — merges multiple ranked result lists into one.
    Rewards documents that appear consistently across multiple retrieval systems.

    Args:
        all_result_lists: list of ranked (document, score) lists
                          one list per retrieval system / query variant
        top_k:            number of final results to return
        k:                RRF smoothing constant (default 60)

    Returns:
        Merged list of (document, rrf_score) tuples, sorted best-first.
        Higher RRF score = better.
    """
    rrf_scores: dict[str, float] = {}
    doc_map: dict[str, object] = {}

    for result_list in all_result_lists:
        for rank, (document, _score) in enumerate(result_list, start=1):
            key = (
                document.metadata.get("workflow", ""),
                document.page_content.strip()
            )
            key_str = str(key)
            rrf_scores[key_str] = rrf_scores.get(key_str, 0.0) + 1.0 / (k + rank)
            if key_str not in doc_map:
                doc_map[key_str] = document

    sorted_keys = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)
    return [(doc_map[key], rrf_scores[key]) for key in sorted_keys[:top_k]]


# ---------------------------------------------------------------------------
# Legacy merge — kept for search.py and debug routes
# ---------------------------------------------------------------------------
def merge_scored_results(scored_results, top_k: int) -> list[tuple]:
    """Merge duplicate documents from multiple queries — keep best L2 score."""
    best_by_key: dict = {}

    for document, score in scored_results:
        workflow = document.metadata.get("workflow", "Unknown")
        source = document.metadata.get("source", workflow)
        key = (workflow, source, document.page_content.strip())
        current = best_by_key.get(key)
        if current is None or score < current[1]:
            best_by_key[key] = (document, score)

    merged = sorted(best_by_key.values(), key=lambda item: item[1])
    return merged[:top_k]


# ---------------------------------------------------------------------------
# Similarity threshold filter
# ---------------------------------------------------------------------------
def apply_threshold(
    results: list[tuple],
    threshold: float = SIMILARITY_THRESHOLD,
    higher_is_better: bool = True,
) -> list[tuple]:
    """
    Filters results by similarity score threshold.

    Args:
        results:          list of (document, score) tuples
        threshold:        minimum acceptable score
        higher_is_better: True for cosine/RRF (higher = better)
                          False for L2 distance (lower = better)

    Returns:
        Filtered list. Falls back to all results if everything filtered out.
    """
    if higher_is_better:
        filtered = [(doc, score) for doc, score in results if score >= threshold]
    else:
        filtered = [(doc, score) for doc, score in results if score <= threshold]

    if not filtered:
        logger.warning(
            "Threshold %.2f filtered ALL results — returning unfiltered top results.", threshold
        )
        return results

    logger.debug(
        "Threshold %.2f kept %d/%d chunks.", threshold, len(filtered), len(results)
    )
    return filtered


# ---------------------------------------------------------------------------
# CrossEncoder reranker
# ---------------------------------------------------------------------------
_reranker_cache = None  # loaded once, reused across all requests (see _get_reranker)


def _get_reranker():
    """
    Lazily loads and caches the CrossEncoder reranker model.
    Loading this model from disk takes several seconds to tens of seconds —
    doing it once at first use (instead of on every request) is what keeps
    reranking fast after the initial warm-up.
    """
    global _reranker_cache
    if _reranker_cache is None:
        from sentence_transformers import CrossEncoder
        logger.info("Loading CrossEncoder reranker model '%s' (one-time load)...", RERANKER_MODEL)
        _reranker_cache = CrossEncoder(RERANKER_MODEL)
        logger.info("CrossEncoder reranker model loaded and cached.")
    return _reranker_cache


def rerank_results(
    question: str,
    results: list[tuple],
    top_k: int,
) -> list[tuple]:
    """
    Reranks retrieved chunks using a CrossEncoder model.
    CrossEncoder reads question + chunk together → more accurate relevance score.

    Args:
        question: the user's question
        results:  list of (document, score) tuples from retrieval
        top_k:    number of results to return after reranking

    Returns:
        Reranked list of (document, reranker_score) tuples, best-first.
        Returns original results if sentence_transformers not installed.
    """
    if not results:
        return results

    try:
        reranker = _get_reranker()
    except ImportError:
        logger.warning("sentence_transformers not installed — reranking disabled.")
        return results[:top_k]
    except Exception:
        logger.exception("Failed to load CrossEncoder reranker model — returning original results.")
        return results[:top_k]

    try:
        pairs = [(question, doc.page_content) for doc, _ in results]
        scores = reranker.predict(pairs)

        ranked = sorted(
            zip(results, scores),
            key=lambda x: x[1],
            reverse=True,  # higher CrossEncoder score = better
        )
        # Return (document, crossencoder_score) — not original RRF score
        return [(item[0][0], float(item[1])) for item in ranked[:top_k]]

    except Exception:
        logger.exception("CrossEncoder reranking failed — returning original results.")
        return results[:top_k]