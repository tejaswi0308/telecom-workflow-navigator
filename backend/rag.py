import argparse
import json
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from langchain_groq import ChatGroq
from langfuse import Langfuse
from langfuse.callback import CallbackHandler

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
def build_llm() -> ChatGroq:
    model_name = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    return ChatGroq(model=model_name, temperature=TEMPERATURE)


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
# Memory — file based (will be replaced by DB in DB track)
# ---------------------------------------------------------------------------
def memory_file_path() -> Path:
    return Path(__file__).resolve().parent / "rag_memory.json"


def load_chat_memory() -> list[dict[str, str]]:
    path = memory_file_path()
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


def save_chat_memory(turns: list[dict[str, str]]) -> None:
    path = memory_file_path()
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
    callbacks = [langfuse_handler] if langfuse_handler else []
    response = llm.invoke(prompt, config={"callbacks": callbacks})
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
def _build_langfuse() -> tuple[Langfuse | None, CallbackHandler | None]:
    """
    Initialises Langfuse client and callback handler.
    Returns (None, None) if credentials are not configured.
    """
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        return None, None

    client = Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        host=os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
    )
    # CallbackHandler picks up credentials from the Langfuse singleton above
    handler = CallbackHandler()
    return client, handler


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

    Pipeline:
        1. Load FAISS vectorstore
        2. Load chat memory
        3. Rewrite follow-up questions
        4. Dense retrieval (FAISS cosine) + BM25 keyword retrieval
        5. RRF merge of dense + BM25 results
        6. Similarity threshold filtering
        7. CrossEncoder reranking
        8. LLM generation with full Langfuse tracing
    """
    # ── Langfuse setup ────────────────────────────────────────────────────
    langfuse_client, langfuse_handler = _build_langfuse()

    # Start a top-level trace using the low-level SDK
    trace_id = None
    if langfuse_client:
        t = langfuse_client.trace(
            name="rag_answer",
            session_id=session_id,
            input={"question": question, "top_k": top_k},
        )
        trace_id = t.id

    def log_span(name: str, input_data: dict, output_data: dict, metadata: dict | None = None):
        """Helper to log a span to Langfuse if tracing is active."""
        if langfuse_client and trace_id:
            langfuse_client.span(
                trace_id=trace_id,
                name=name,
                input=input_data,
                output=output_data,
                metadata=metadata or {},
            )

    # ── 1. Load vectorstore ───────────────────────────────────────────────
    index_path = get_index_path()
    try:
        vectorstore = load_vectorstore(index_path)
    except FileNotFoundError as exc:
        return {"answer": str(exc), "sources": [], "error": "index_not_found"}

    # ── 2. Load memory ────────────────────────────────────────────────────
    history = load_chat_memory()

    # ── 3. Rewrite follow-up ──────────────────────────────────────────────
    standalone_question = rewrite_question(
        question, history, verbose=verbose, langfuse_handler=langfuse_handler,
    )

    if trace_id and standalone_question != question:
        log_span(
            "question_rewrite",
            input_data={"original": question},
            output_data={"rewritten": standalone_question},
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
        return {"answer": answer, "sources": [], "error": None}

    # ── 4. Workflow routing ───────────────────────────────────────────────
    inferred_wf = infer_workflow_type(question) or infer_workflow_type(standalone_question)
    if verbose and inferred_wf:
        print(f"Router → target slug: {inferred_wf}")

    # ── 5. Dense retrieval (FAISS cosine) ─────────────────────────────────
    candidate_k = max(top_k * 5, top_k + 10)
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

    # Deduplicate dense candidates keeping best score
    seen_dense: dict[str, tuple] = {}
    for doc, score in dense_candidates:
        key = doc.page_content.strip()
        if key not in seen_dense or score > seen_dense[key][1]:  # higher = better (cosine)
            seen_dense[key] = (doc, score)
    dense_results = sorted(seen_dense.values(), key=lambda x: x[1], reverse=True)[:candidate_k]

    # Apply threshold on cosine similarity scores — before RRF merge
    # Filters out chunks that are not similar enough to the query
    pre_threshold_count = len(dense_results)
    dense_results = apply_threshold(
        dense_results,
        threshold=SIMILARITY_THRESHOLD,
        higher_is_better=True,  # cosine — higher is better
    )
    logger.debug(
        "Cosine threshold %.2f: kept %d/%d dense chunks.",
        SIMILARITY_THRESHOLD, len(dense_results), pre_threshold_count,
    )

    # Log dense retrieval to Langfuse
    log_span(
        "dense_retrieval",
        input_data={"query": standalone_question, "candidate_k": candidate_k},
        output_data={
            "chunks": [
                {
                    "workflow": doc.metadata.get("workflow", "Unknown"),
                    "score": round(float(score), 4),
                    "preview": doc.page_content[:200],
                }
                for doc, score in dense_results[:top_k]
            ]
        },
        metadata={"retrieval_type": "dense_cosine", "inferred_workflow": inferred_wf},
    )

    # ── 6. BM25 retrieval ─────────────────────────────────────────────────
    # Get all documents from vectorstore for BM25
    all_docs = [doc for doc, _ in dense_candidates]
    bm25_results = bm25_search(standalone_question, all_docs, top_k=candidate_k)

    # Log BM25 retrieval to Langfuse
    log_span(
        "bm25_retrieval",
        input_data={"query": standalone_question},
        output_data={
            "chunks": [
                {
                    "workflow": doc.metadata.get("workflow", "Unknown"),
                    "score": round(float(score), 4),
                    "preview": doc.page_content[:200],
                }
                for doc, score in bm25_results[:top_k]
            ]
        },
        metadata={"retrieval_type": "bm25_keyword"},
    )

    # ── 7. RRF merge ──────────────────────────────────────────────────────
    merged_results = merge_rrf(
        [dense_results, bm25_results],
        top_k=candidate_k,
    )

    log_span(
        "rrf_merge",
        input_data={
            "dense_count": len(dense_results),
            "bm25_count": len(bm25_results),
        },
        output_data={
            "merged_count": len(merged_results),
            "top_chunks": [
                {
                    "workflow": doc.metadata.get("workflow", "Unknown"),
                    "rrf_score": round(float(score), 6),
                }
                for doc, score in merged_results[:top_k]
            ],
        },
    )

    # ── 8. Threshold logging in Langfuse ─────────────────────────────────
    # Threshold was already applied on cosine scores before RRF merge.
    # Here we just log the score distribution for observability.
    above = [(doc, score) for doc, score in merged_results if score >= SIMILARITY_THRESHOLD]
    below = [(doc, score) for doc, score in merged_results if score < SIMILARITY_THRESHOLD]

    log_span(
        "threshold_analysis",
        input_data={"reference_threshold": SIMILARITY_THRESHOLD},
        output_data={
            "total_chunks": len(merged_results),
            "above_threshold": [
                {"workflow": doc.metadata.get("workflow", "Unknown"), "score": round(float(s), 6)}
                for doc, s in above
            ],
            "below_threshold": [
                {"workflow": doc.metadata.get("workflow", "Unknown"), "score": round(float(s), 6)}
                for doc, s in below
            ],
        },
        metadata={"chunks_above": len(above), "chunks_below": len(below)},
    )

    if not merged_results:
        return {"answer": "No relevant context found.", "sources": [], "error": None}

    # ── 9. CrossEncoder reranking ─────────────────────────────────────────
    reranked_results = rerank_results(standalone_question, merged_results, top_k=top_k)

    log_span(
        "crossencoder_rerank",
        input_data={"question": standalone_question, "chunks_in": len(merged_results)},
        output_data={
            "final_chunks": [
                {
                    "rank": i + 1,
                    "workflow": doc.metadata.get("workflow", "Unknown"),
                    "reranker_score": round(float(score), 4),
                    "preview": doc.page_content[:200],
                }
                for i, (doc, score) in enumerate(reranked_results)
            ]
        },
    )

    results = reranked_results

    # ── 10. Direct answer parser (simple list questions) ──────────────────
    use_direct_parser = (
        is_process_question(standalone_question)
        and any(
            kw in standalone_question.lower()
            for kw in ("list", "show me", "what are the steps", "sequence of steps")
        )
        and not is_complex_query(standalone_question)
    )

    if use_direct_parser:
        direct_answer = build_process_direct_answer(standalone_question, results)
        if direct_answer:
            answer_text, matched_workflow = direct_answer
            history.append({"user": question, "assistant": answer_text})
            save_chat_memory(history)

            sources = [
                {"workflow": doc.metadata.get("workflow", "Unknown"), "score": float(score)}
                for doc, score in results
                if doc.metadata.get("workflow") == matched_workflow
            ]
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

    callbacks = [langfuse_handler] if langfuse_handler else []

    # Generation span — LLM-specific with all characteristics
    generation_id = None
    if langfuse_client and trace_id:
        gen = langfuse_client.generation(
            trace_id=trace_id,
            name="llm_generation",
            model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            model_parameters={
                "temperature": TEMPERATURE,
                "top_k": top_k,
            },
            input=prompt,
        )
        generation_id = gen.id

    response = llm.invoke(prompt, config={"callbacks": callbacks})
    answer = response.content.strip()

    # Log token usage to Langfuse generation span
    if langfuse_client and generation_id:
        usage = getattr(response, "usage_metadata", None)
        langfuse_client.generation(
            id=generation_id,
            output=answer,
            usage={
                "input":  getattr(usage, "input_tokens", None),
                "output": getattr(usage, "output_tokens", None),
                "total":  getattr(usage, "total_tokens", None),
            } if usage else {},
        )

    # Strip citations [1], [2] from answer just in case LLM still adds them
    answer = re.sub(r"\[\d+\]", "", answer).strip()

    if _has_structured_content(answer):
        answer_clean = answer
    else:
        answer_clean = strip_markdown_formatting(answer)

    history.append({"user": question, "assistant": answer_clean})
    save_chat_memory(history)

    sources = []
    seen: set[str] = set()
    for document, score in results:
        workflow = document.metadata.get("workflow", "Unknown")
        if workflow in seen:
            continue
        seen.add(workflow)
        sources.append({"workflow": workflow, "score": float(score)})

    # Finalise trace
    if langfuse_client and trace_id:
        langfuse_client.trace(
            id=trace_id,
            output={"answer": answer_clean, "sources": sources},
        )
        langfuse_client.flush()

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