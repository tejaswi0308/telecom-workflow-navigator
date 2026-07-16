import argparse
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from utils import (
    SIMILARITY_THRESHOLD,
    apply_threshold,
    bm25_search,
    build_retrieval_queries,
    clean_section_title,
    get_index_path,
    infer_workflow_type,
    load_vectorstore,
    merge_rrf,
    normalize_text,
    rerank_results,
    scan_available_workflows,
    strip_markdown_formatting,
    workflow_markdown_path,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — all tuneable via environment variables
# ---------------------------------------------------------------------------
MEMORY_TURNS  = int(os.getenv("MEMORY_TURNS", "6"))
DEFAULT_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
TEMPERATURE   = float(os.getenv("LLM_TEMPERATURE", "0.2"))

# ---------------------------------------------------------------------------
# Hint tuples — conversational signal detection
# ---------------------------------------------------------------------------
FOLLOW_UP_HINTS = (
    "it", "this", "that", "they", "them", "there", "he", "she",
    "who approves", "what happens next", "what happens after",
    "and then", "next step", "after that",
)

DEFINITION_HINTS = ("what is", "who is", "define", "what are")

PROCESS_HINTS = (
    "step", "steps", "process", "procedure",
    "sequence", "workflow", "how many",
)

COMPLEX_QUERY_HINTS = (
    "approval", "hierarchy", "chain", "corporate", "executive",
    "actor", "complete", "full", "detail", "list all", "entire",
)


# ---------------------------------------------------------------------------
# LLM builder
# ---------------------------------------------------------------------------
def build_llm():
    """
    Builds the chat LLM based on LLM_PROVIDER env var:
      LLM_PROVIDER=azure  -> ChatOpenAI pointed at Azure's v1 unified endpoint
                             (org credentials, e.g. *.services.ai.azure.com/openai/v1)
      LLM_PROVIDER=groq   -> ChatGroq (fallback / local dev)
    Defaults to "azure".
    """
    provider = os.getenv("LLM_PROVIDER", "azure").lower()

    if provider == "azure":
        required_vars = [
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_DEPLOYMENT_NAME",
        ]
        missing = [v for v in required_vars if not os.getenv(v)]
        if missing:
            raise RuntimeError(
                f"LLM_PROVIDER=azure but missing env vars: {', '.join(missing)}. "
                "Check your .env file."
            )
        return ChatOpenAI(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            base_url=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            temperature=TEMPERATURE,
        )

    if provider == "groq":
        model_name = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        return ChatGroq(model=model_name, temperature=TEMPERATURE)

    raise ValueError(f"Unknown LLM_PROVIDER '{provider}'. Use 'azure' or 'groq'.")


def current_model_name() -> str:
    """Returns the active model/deployment name, for Langfuse generation logging."""
    provider = os.getenv("LLM_PROVIDER", "azure").lower()
    if provider == "azure":
        return os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "azure-openai")
    return os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")


# ---------------------------------------------------------------------------
# Context formatting — no chunk index numbers sent to LLM
# ---------------------------------------------------------------------------
def format_context(results: list[tuple]) -> str:
    """
    Formats retrieved chunks as context for the LLM prompt.
    Chunk index numbers removed from content — LLM should not cite [1], [2] etc.
    """
    sections = []
    for document, score in results:
        workflow = document.metadata.get("workflow", "Unknown")
        content = document.page_content.strip()
        sections.append(
            f"Workflow: {workflow}\nScore: {score:.4f}\nContent:\n{content}"
        )
    return "\n\n---\n\n".join(sections)


# ---------------------------------------------------------------------------
# Memory — file based, one file per session (will be replaced by DB in DB track)
# ---------------------------------------------------------------------------
_SAFE_SESSION_ID_RE = re.compile(r"[^A-Za-z0-9_-]")


def _sanitize_session_id(session_id: str) -> str:
    """
    Prevents path traversal / invalid filenames. Falls back to 'default'
    if the sanitized id is empty.
    """
    cleaned = _SAFE_SESSION_ID_RE.sub("_", str(session_id or "").strip())
    return cleaned or "default"


def memory_dir_path() -> Path:
    directory = Path(__file__).resolve().parent / "memory"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def memory_file_path(session_id: str = "default") -> Path:
    safe_id = _sanitize_session_id(session_id)
    return memory_dir_path() / f"rag_memory_{safe_id}.json"


def load_chat_memory(session_id: str = "default") -> list[dict[str, str]]:
    path = memory_file_path(session_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    turns: list[dict[str, str]] = []
    for item in data[-MEMORY_TURNS:]:
        if isinstance(item, dict) and "user" in item and "assistant" in item:
            turns.append({"user": str(item["user"]), "assistant": str(item["assistant"])})
    return turns


def save_chat_memory(turns: list[dict[str, str]], session_id: str = "default") -> None:
    path = memory_file_path(session_id)
    path.write_text(json.dumps(turns[-MEMORY_TURNS:], indent=2), encoding="utf-8")


def format_chat_history(turns: list[dict[str, str]]) -> str:
    if not turns:
        return "No previous conversation."
    sections = []
    for index, turn in enumerate(turns, start=1):
        sections.append(f"Turn {index}\nUser: {turn['user']}\nAssistant: {turn['assistant']}")
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Question classification helpers
# ---------------------------------------------------------------------------
def is_explicit_topic_question(question: str) -> bool:
    return infer_workflow_type(question) is not None


def is_follow_up_question(question: str) -> bool:
    lowered = question.lower()
    return any(hint in lowered for hint in FOLLOW_UP_HINTS)


def is_definition_question(question: str) -> bool:
    return any(question.lower().strip().startswith(hint) for hint in DEFINITION_HINTS)


def is_process_question(question: str) -> bool:
    return any(hint in question.lower().strip() for hint in PROCESS_HINTS)


def is_complex_query(question: str) -> bool:
    return any(hint in question.lower() for hint in COMPLEX_QUERY_HINTS)


# ---------------------------------------------------------------------------
# Answering hints — domain-specific guidance injected into prompt
# ---------------------------------------------------------------------------
def build_answering_hint(question: str) -> str:
    lowered = question.lower()
    hints = []

    if any(k in lowered for k in ("sop", "procedure", "workflow", "steps", "how do")):
        hints.append(
            "Treat this as a process question and summarize the workflow steps in order, "
            "even if the word SOP does not appear in the docs."
        )
    if any(k in lowered for k in ("billing", "commercial", "revenue", "rfi b", "rfi(b)")):
        hints.append(
            "Focus on commercial and billing checkpoints such as Service Order, RFI(P), "
            "RFI(B), OBRM, and approval gates."
        )
    if any(k in lowered for k in ("edge case", "exception", "what if", "if rejected", "fallback")):
        hints.append(
            "Include rejection loops, alternate paths, and exception handling when they "
            "are present in the context."
        )
    if any(k in lowered for k in ("approval", "hierarchy", "chain", "corporate", "executive", "actor")):
        hints.append(
            "List all actors and their roles in the approval chain in the order they appear. "
            "Include both Circle-level and Corporate/National-level approvers. "
            "Note any rejection or rework paths at each approval stage."
        )
    return " ".join(hints)


# ---------------------------------------------------------------------------
# Markdown section helpers (direct answer parser)
# ---------------------------------------------------------------------------
def split_markdown_sections(markdown: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if heading_match:
            if current_title is not None:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = heading_match.group(2).strip()
            current_lines = []
            continue
        if current_title is not None:
            current_lines.append(line)

    if current_title is not None:
        sections.append((current_title, "\n".join(current_lines).strip()))

    return sections


def extract_target_step_phrase(question: str) -> str | None:
    quoted_matches = re.findall(r'"([^"]+)"|\'([^\']+)\'', question)
    for double_quoted, single_quoted in quoted_matches:
        phrase = double_quoted or single_quoted
        if phrase.strip():
            return phrase.strip()

    if "step" in question.lower():
        match = re.search(
            r"step\s+(?:'|\")?([^'\"?]+?)(?:'|\")?(om\s+and\s+where|\s+where|\?|$)",
            question, flags=re.I,
        )
        if match:
            return match.group(1).strip()
    return None


def score_section(question: str, title: str, content: str) -> int:
    question_tokens = set(normalize_text(question).split())
    title_tokens = set(normalize_text(title).split())
    content_tokens = set(normalize_text(content).split())

    score = len(question_tokens & title_tokens) * 4
    score += len(question_tokens & content_tokens)

    if any(token in title.lower() for token in ("workflow", "steps", "variant")):
        score += 2
    if re.search(r"^\d+\.\s+", content, flags=re.M):
        score += 3
    return score


def select_best_section(question: str, markdown: str) -> str:
    sections = split_markdown_sections(markdown)
    if not sections:
        return markdown
    best_title, best_content = max(
        sections,
        key=lambda s: score_section(question, s[0], s[1]),
    )
    if score_section(question, best_title, best_content) <= 0:
        return markdown
    return best_content or markdown


def extract_numbered_steps(section_text: str) -> list[str]:
    steps = []
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        match = re.match(r"^\d+\.\s+(.+)$", line)
        if not match:
            continue
        step_text = match.group(1).strip().replace("**", "")
        step_text = re.sub(r"\s+\*\(.*\)\*$", "", step_text).strip()
        steps.append(step_text)
    return steps


def extract_numbered_step_pairs(section_text: str) -> list[tuple[int, str]]:
    steps = []
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        match = re.match(r"^(\d+)\.\s+(.+)$", line)
        if not match:
            continue
        step_number = int(match.group(1))
        step_text = match.group(2).strip().replace("**", "")
        step_text = re.sub(r"\s+\*\(.*\)\*$", "", step_text).strip()
        steps.append((step_number, step_text))
    return steps


def find_step_location(question: str, markdown: str) -> tuple[str, int, list[str]] | None:
    target_phrase = extract_target_step_phrase(question)
    if not target_phrase:
        return None

    target_normalized = normalize_text(target_phrase)
    sections = split_markdown_sections(markdown)

    for title, content in sections:
        step_pairs = extract_numbered_step_pairs(content)
        for index, step_text in step_pairs:
            if target_normalized and target_normalized in normalize_text(step_text):
                step_position = index - 1
                surrounding = [
                    f"{si}. {st}"
                    for si, st in step_pairs[
                        max(0, step_position - 1): min(len(step_pairs), step_position + 2)
                    ]
                ]
                return clean_section_title(title), index, surrounding
    return None


def select_matching_workflow_result(question: str, results: list[tuple]):
    for document, score in results:
        workflow = document.metadata.get("workflow", "Unknown")
        markdown_path = workflow_markdown_path(workflow)
        if not markdown_path or not markdown_path.exists():
            continue
        markdown = markdown_path.read_text(encoding="utf-8")
        if find_step_location(question, markdown):
            return document, score, markdown_path, markdown

    if not results:
        return None

    document, score = results[0]
    workflow = document.metadata.get("workflow", "Unknown")
    markdown_path = workflow_markdown_path(workflow)
    if not markdown_path or not markdown_path.exists():
        return None
    markdown = markdown_path.read_text(encoding="utf-8")
    return document, score, markdown_path, markdown


def build_process_direct_answer(question: str, results: list[tuple]) -> tuple[str, str] | None:
    selected = select_matching_workflow_result(question, results)
    if not selected:
        return None

    document, _score, _path, markdown = selected
    workflow = document.metadata.get("workflow", "Unknown")

    step_location = find_step_location(question, markdown)
    if step_location:
        section_title, step_number, surrounding_steps = step_location
        lines = [
            f"Based on the provided context, the step '{extract_target_step_phrase(question)}' "
            f"appears in {section_title}.",
            f"It occurs at step {step_number}.",
            "",
            "Nearby steps:",
        ]
        lines.extend(surrounding_steps)
        return "\n".join(lines), workflow

    section = select_best_section(question, markdown)
    steps = extract_numbered_steps(section) or extract_numbered_steps(markdown)
    if not steps:
        return None

    lines = [f"Based on the provided context, the {workflow} workflow has {len(steps)} steps:", ""]
    for i, step in enumerate(steps, start=1):
        lines.append(f"{i}. {step}")
    return "\n".join(lines), workflow


# ---------------------------------------------------------------------------
# Question rewriting for follow-ups
# ---------------------------------------------------------------------------
def rewrite_question(
    question: str,
    history: list[dict[str, str]],
    verbose: bool = False,
    langfuse_handler=None,
) -> str:
    if (
        not history
        or not is_follow_up_question(question)
        or is_explicit_topic_question(question)
        or is_definition_question(question)
    ):
        return question

    llm = build_llm()
    prompt = (
        "Rewrite the user's follow-up into a standalone question using the conversation "
        "history. Keep workflow names and entities explicit. Return only the rewritten "
        "question, with no extra text.\n\n"
        f"Conversation History:\n{format_chat_history(history)}\n\n"
        f"Follow-up Question: {question}\n\n"
        "Standalone Question:"
    )
    # No callbacks — avoids blank traces in Langfuse
    response = llm.invoke(prompt, config={"callbacks": []})
    rewritten = response.content.strip()
    if verbose and rewritten and rewritten != question:
        print(f"Rewritten question: {rewritten}")
    return rewritten or question


# ---------------------------------------------------------------------------
# Structured content check
# ---------------------------------------------------------------------------
def _has_structured_content(text: str) -> bool:
    if re.search(r"\*\*[^*]+\*\*", text):
        return True
    if "→" in text or "->" in text:
        return True
    return False


# ---------------------------------------------------------------------------
# Langfuse setup
# ---------------------------------------------------------------------------
def _build_langfuse() -> tuple:
    """
    Initialises Langfuse client for manual tracing.
    Lazy import — avoids SDK auto-init blank traces on module load.
    Returns (client, None) if configured, (None, None) if not.
    """
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        return None, None

    from langfuse import Langfuse  # lazy import — only when credentials exist
    client = Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        host=os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
    )
    return client, None


# ---------------------------------------------------------------------------
# Core RAG answer function
# ---------------------------------------------------------------------------
def rag_answer(
    question: str,
    top_k: int = DEFAULT_TOP_K,
    verbose: bool = False,
    session_id: str = "default",
) -> dict:
    """
    Core RAG entry point. Returns a structured dict:
    {
        "answer":  str,
        "sources": [{"workflow": str, "score": float}, ...],
        "error":   str | None,
    }
    """
    # ── Langfuse setup ────────────────────────────────────────────────────
    langfuse_client, langfuse_handler = _build_langfuse()

    trace_id = None
    trace_obj = None
    trace_metadata: dict[str, object] = {
        "session_id": session_id,
        "question": question,
        "question_length": len(question),
        "question_word_count": len(question.split()),
        "top_k": top_k,
    }

    def ensure_trace() -> str | None:
        nonlocal trace_id, trace_obj
        if trace_id or not langfuse_client:
            return trace_id

        trace_obj = langfuse_client.trace(
            name="rag_answer",
            session_id=session_id,
            input={"question": question, "top_k": top_k},
            metadata=dict(trace_metadata),
        )
        trace_id = trace_obj.id
        return trace_id

    def finalize_trace(answer_text: str, sources: list[dict], extra_metadata: dict | None = None) -> None:
        current_trace_id = ensure_trace()
        if not langfuse_client or not current_trace_id or not trace_obj:
            return

        final_metadata = dict(trace_metadata)
        if extra_metadata:
            final_metadata.update(extra_metadata)

        trace_obj.update(
            metadata=final_metadata,
            output={"answer": answer_text, "sources": sources},
        )
        langfuse_client.flush()

    def log_span(name: str, input_data: dict, output_data: dict, start_time=None, end_time=None, metadata: dict | None = None):
        """Helper to log a span to Langfuse if tracing is active with precise metrics."""
        current_trace_id = ensure_trace()
        if langfuse_client and current_trace_id:
            langfuse_client.span(
                trace_id=current_trace_id,
                name=name,
                input=input_data,
                output=output_data,
                start_time=start_time,
                end_time=end_time,
                metadata=metadata or {},
            )

    # ── 1. Load vectorstore ───────────────────────────────────────────────
    index_path = get_index_path()
    try:
        vectorstore = load_vectorstore(index_path)
    except FileNotFoundError as exc:
        return {"answer": str(exc), "sources": [], "error": "index_not_found"}

    # ── 2. Load memory ────────────────────────────────────────────────────
    history = load_chat_memory(session_id)
    trace_metadata.update(
        {
            "history_turns": len(history),
            "is_follow_up_question": is_follow_up_question(question),
            "is_explicit_topic_question": is_explicit_topic_question(question),
        }
    )

    # ── 3. Rewrite follow-up ──────────────────────────────────────────────
    standalone_question = rewrite_question(
        question, history, verbose=verbose, langfuse_handler=langfuse_handler,
    )
    trace_metadata.update(
        {
            "standalone_question": standalone_question,
            "standalone_question_length": len(standalone_question),
            "rewritten_question": standalone_question != question,
        }
    )

    if standalone_question != question:
        log_span(
            "question_rewrite",
            input_data={"original": question},
            output_data={"rewritten": standalone_question},
            metadata={
                "rewrite_applied": True,
                "rewrite_reason": "follow_up_question",
            },
        )

    if (
        is_follow_up_question(standalone_question)
        and not is_explicit_topic_question(standalone_question)
        and not history
    ):
        answer = (
            "I'm sorry, but your question refers to a previous topic and there is no "
            "active chat history. Could you please specify which workflow you are asking about?"
        )
        finalize_trace(answer, [], extra_metadata={"answer_mode": "follow_up_without_history"})
        return {"answer": answer, "sources": [], "error": None}

    # ── 4. Workflow routing ───────────────────────────────────────────────
    inferred_wf = infer_workflow_type(question) or infer_workflow_type(standalone_question)
    trace_metadata.update(
        {
            "inferred_workflow": inferred_wf,
            "standalone_question_is_follow_up": is_follow_up_question(standalone_question),
            "standalone_question_is_explicit_topic": is_explicit_topic_question(standalone_question),
        }
    )
    if verbose and inferred_wf:
        print(f"Router → target slug: {inferred_wf}")

    # ── 5. Dense retrieval (FAISS cosine) + threshold ────────────────────
    t_dense_start = datetime.now(timezone.utc)
    candidate_k = max(top_k * 5, top_k + 10)
    trace_metadata["candidate_k"] = candidate_k
    dense_candidates: list[tuple] = []

    for retrieval_query in build_retrieval_queries(standalone_question):
        dense_candidates.extend(
            vectorstore.similarity_search_with_score(retrieval_query, k=candidate_k)
        )

    # Filter to inferred workflow if confident
    if inferred_wf:
        filtered_dense = [
            pair for pair in dense_candidates
            if inferred_wf == pair[0].metadata.get("workflow_slug", "")
        ]
        dense_candidates = filtered_dense if filtered_dense else dense_candidates

    # Deduplicate keeping best cosine score per chunk
    seen_dense: dict[str, tuple] = {}
    for doc, score in dense_candidates:
        key = doc.page_content.strip()
        if key not in seen_dense or score > seen_dense[key][1]:
            seen_dense[key] = (doc, score)
    dense_deduped = sorted(seen_dense.values(), key=lambda x: x[1], reverse=True)
    trace_metadata["dense_candidate_count"] = len(dense_candidates)
    trace_metadata["dense_deduped_count"] = len(dense_deduped)

    # Apply cosine similarity threshold AFTER dedup
    pre_threshold_count = len(dense_deduped)
    dense_results = apply_threshold(
        dense_deduped,
        threshold=SIMILARITY_THRESHOLD,
        higher_is_better=True,
    )
    trace_metadata["dense_result_count"] = len(dense_results)
    t_dense_end = datetime.now(timezone.utc)

    # ── 6. BM25 retrieval (independent) ──────────────────────────────────
    t_bm25_start = datetime.now(timezone.utc)
    all_docs_only = [doc for doc, _ in dense_deduped]
    bm25_results = bm25_search(standalone_question, all_docs_only, top_k=candidate_k)
    trace_metadata["bm25_result_count"] = len(bm25_results)
    t_bm25_end = datetime.now(timezone.utc)

    # ── 7. RRF merge (dense + BM25) ───────────────────────────────────────
    t_rrf_start = datetime.now(timezone.utc)
    merged_results = merge_rrf(
        [dense_results, bm25_results],
        top_k=10,
    )
    trace_metadata["merged_result_count"] = len(merged_results)
    t_rrf_end = datetime.now(timezone.utc)

    if not merged_results:
        answer = "No relevant context found."
        finalize_trace(answer, [], extra_metadata={"answer_mode": "no_context"})
        return {"answer": answer, "sources": [], "error": None}

    # ── 8. CrossEncoder reranking ─────────────────────────────────────────
    t_rerank_start = datetime.now(timezone.utc)
    reranked_results = rerank_results(standalone_question, merged_results, top_k=top_k)

    results = reranked_results
    trace_metadata["reranked_result_count"] = len(results)
    t_rerank_end = datetime.now(timezone.utc)

    # ── Log all retrieval spans WITH exact performance timestamps ─────────
    log_span(
        "dense_retrieval",
        input_data={
            "query": standalone_question,
            "candidate_k": candidate_k,
            "threshold": SIMILARITY_THRESHOLD,
        },
        output_data={
            "total_before_threshold": pre_threshold_count,
            "total_after_threshold": len(dense_results),
            "chunks": [
                {
                    "rank": i + 1,
                    "workflow": doc.metadata.get("workflow", "Unknown"),
                    "cosine_score": round(float(score), 4),
                    "preview": doc.page_content[:200],
                }
                for i, (doc, score) in enumerate(dense_results[:top_k])
            ],
        },
        start_time=t_dense_start,
        end_time=t_dense_end,
        metadata={"retrieval_type": "dense_cosine", "inferred_workflow": inferred_wf},
    )

    log_span(
        "bm25_retrieval",
        input_data={"query": standalone_question, "total_docs": len(all_docs_only)},
        output_data={
            "total_results": len(bm25_results),
            "chunks": [
                {
                    "rank": i + 1,
                    "workflow": doc.metadata.get("workflow", "Unknown"),
                    "bm25_score": round(float(score), 4),
                    "preview": doc.page_content[:200],
                }
                for i, (doc, score) in enumerate(bm25_results[:top_k])
            ],
        },
        start_time=t_dense_end,
        end_time=t_bm25_end,
        metadata={"retrieval_type": "bm25_keyword"},
    )

    log_span(
        "rrf_merge",
        input_data={
            "dense_chunks": len(dense_results),
            "bm25_chunks": len(bm25_results),
        },
        output_data={
            "merged_count": len(merged_results),
            "top_chunks": [
                {
                    "rank": i + 1,
                    "workflow": doc.metadata.get("workflow", "Unknown"),
                    "rrf_score": round(float(score), 6),
                }
                for i, (doc, score) in enumerate(merged_results[:top_k])
            ],
        },
        start_time=t_bm25_end,
        end_time=t_rrf_end,
    )

    log_span(
        "crossencoder_rerank",
        input_data={
            "question": standalone_question,
            "chunks_in": len(merged_results),
            "top_k": 3,
        },
        output_data={
            "final_top_k_chunks": [
                {
                    "rank": i + 1,
                    "workflow": doc.metadata.get("workflow", "Unknown"),
                    "crossencoder_score": round(float(score), 4),
                    "content": doc.page_content[:300],
                }
                for i, (doc, score) in enumerate(reranked_results)
            ]
        },
        start_time=t_rrf_end,
        end_time=t_rerank_end,
    )

    # ── 10. Direct answer parser (simple list questions) ──────────────────
    use_direct_parser = (
        is_process_question(standalone_question)
        and any(
            kw in standalone_question.lower()
            for kw in ("list", "show me", "what are the steps", "sequence of steps")
        )
        and not is_complex_query(standalone_question)
    )
    trace_metadata["use_direct_parser"] = use_direct_parser

    if use_direct_parser:
        direct_answer = build_process_direct_answer(standalone_question, results)
        if direct_answer:
            answer_text, matched_workflow = direct_answer
            history.append({"user": question, "assistant": answer_text})
            save_chat_memory(history, session_id)

            sources = [
                {"workflow": doc.metadata.get("workflow", "Unknown"), "score": float(score)}
                for doc, score in results
                if doc.metadata.get("workflow") == matched_workflow
            ]
            finalize_trace(
                answer_text,
                sources,
                extra_metadata={
                    "answer_mode": "direct_parser",
                    "matched_workflow": matched_workflow,
                },
            )
            return {"answer": answer_text, "sources": sources, "error": None}

    # ── 11. LLM generation ────────────────────────────────────────────────
    context = format_context(results)
    llm = build_llm()

    prompt = (
        "You are a telecom workflow assistant. Use the conversation history for follow-up "
        "questions, but answer using only the provided context. "
        "If the answer is not in the context, say you could not find it. "
        "Be concise and accurate. Reference workflow names when useful. "
        "Do NOT include citation numbers like [1] or [2] in your answer.\n"
        f"Answering guidance: {build_answering_hint(standalone_question)}\n\n"
        f"Conversation History:\n{format_chat_history(history)}\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {standalone_question}\n\n"
        "Answer:"
    )

    # Log exact context sent to LLM — BEFORE calling LLM
    log_span(
        "context_sent_to_llm",
        input_data={"question": standalone_question},
        output_data={
            "final_chunks_count": len(results),
            "chunks": [
                {
                    "rank": i + 1,
                    "workflow": doc.metadata.get("workflow", "Unknown"),
                    "crossencoder_score": round(float(score), 4),
                    "content": doc.page_content.strip(),
                }
                for i, (doc, score) in enumerate(results)
            ],
            "full_context": context,
        },
    )

    # Generation span — LLM-specific with all characteristics
    generation_client = None
    current_trace_id = ensure_trace()
    if langfuse_client and current_trace_id:
        generation_client = langfuse_client.generation(
            trace_id=current_trace_id,
            name="llm_generation",
            model=current_model_name(),
            model_parameters={
                "temperature": TEMPERATURE,
                "top_k": top_k,
            },
            input=prompt,
            metadata={
                "session_id": session_id,
                "history_turns": len(history),
                "inferred_workflow": inferred_wf,
                "candidate_k": candidate_k,
                "dense_result_count": len(dense_results),
                "bm25_result_count": len(bm25_results),
                "merged_result_count": len(merged_results),
                "reranked_result_count": len(results),
                "use_direct_parser": use_direct_parser,
            },
        )

    response = llm.invoke(prompt, config={"callbacks": []})
    answer = response.content.strip()

    # Log token usage
    if generation_client:
        token_usage = response.response_metadata.get("token_usage", {})
        generation_client.update(
            output=answer,
            usage={
                "input": token_usage.get("prompt_tokens"),
                "output": token_usage.get("completion_tokens"),
                "total": token_usage.get("total_tokens"),
            },
        )

    # Strip citations [1], [2] from answer just in case LLM still adds them
    answer = re.sub(r"\[\d+\]", "", answer).strip()

    if _has_structured_content(answer):
        answer_clean = answer
    else:
        answer_clean = strip_markdown_formatting(answer)

    history.append({"user": question, "assistant": answer_clean})
    save_chat_memory(history, session_id)

    sources = []
    seen: set[str] = set()
    for document, score in results:
        workflow = document.metadata.get("workflow", "Unknown")
        if workflow in seen:
            continue
        seen.add(workflow)
        sources.append({"workflow": workflow, "score": float(score)})

    # Finalise trace
    finalize_trace(
        answer_clean,
        sources,
        extra_metadata={
            "answer_mode": "llm",
            "answer_length": len(answer_clean),
            "source_count": len(sources),
        },
    )

    return {"answer": answer_clean, "sources": sources, "error": None}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="RAG query over indexed telecom workflows")
    parser.add_argument("question", help="Question to answer from the workflow index")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--session", default="cli-session")
    args = parser.parse_args()

    result = rag_answer(
        args.question,
        top_k=args.top_k,
        verbose=args.verbose,
        session_id=args.session,
    )

    print("\nAnswer")
    print(result["answer"])

    if result["sources"]:
        print("\nSources")
        for idx, source in enumerate(result["sources"], start=1):
            print(f"- [{idx}] {source['workflow']} (score: {source['score']:.4f})")


if __name__ == "__main__":
    main()