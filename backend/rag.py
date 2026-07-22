import argparse
import logging
import os
import re
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from guardrails import (
    CONTEXT_GOVERNANCE_PROMPT,
    LOW_CONFIDENCE_REFUSAL,
    NO_HISTORY_REFUSAL,
    build_hint_matcher,
    check_pre_retrieval_guardrails,
    is_meta_conversation_question,
)
from memory import (
    MEMORY_TURNS,
    format_chat_history,
    load_chat_memory,
    memory_file_path,
    save_chat_memory,
)
from utils import (
    RERANK_THRESHOLD,
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
DEFAULT_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
TEMPERATURE   = float(os.getenv("LLM_TEMPERATURE", "0.2"))
CANDIDATE_K   = int(os.getenv("RAG_CANDIDATE_K", "5"))    # dense/BM25/RRF pool size
FINAL_K       = int(os.getenv("RAG_FINAL_K", "4"))        # chunks kept after cross-encoder rerank

# ---------------------------------------------------------------------------
# Hint tuples — conversational signal detection
# ---------------------------------------------------------------------------
FOLLOW_UP_HINTS = (
    "it", "this", "that", "they", "them", "there", "he", "she",
    "who approves", "what happens next", "what happens after",
    "and then", "next step", "after that",
)

# Relative-position follow-ups ("what is the step after X", "what comes
# after X", "what follows X") reference the PREVIOUS turn's topic just as
# much as a bare pronoun does, but none of them are literal substring
# matches for anything in FOLLOW_UP_HINTS above — enumerating every
# possible phrasing as an exact hint kept missing real variants (this
# exact pattern was reported failing for "what is the step after RFI(B)?").
# Using a wildcard regex instead of literal phrases, same fix as applied
# elsewhere in this file for the same underlying problem.
_RELATIVE_POSITION_RE = re.compile(
    r"\bstep\s+(?:after|before)\b"
    r"|\bcomes?\s+after\b"
    r"|\bwhat\s+follows\b"
    r"|\bfollow(?:s|ing)?\s+(?:after|that)\b"
    r"|\bprevious\s+step\b",
    re.IGNORECASE,
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
# Memory — see memory.py for all conversation-memory logic (load/save/format).
# Imported above: load_chat_memory, save_chat_memory, format_chat_history,
# memory_file_path, memory_dir_path, MEMORY_TURNS.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Question classification helpers
# ---------------------------------------------------------------------------
def is_explicit_topic_question(question: str) -> bool:
    return infer_workflow_type(question) is not None


_FOLLOW_UP_MATCHER = build_hint_matcher(FOLLOW_UP_HINTS)


def is_follow_up_question(question: str) -> bool:
    """
    Uses word-boundary matching, not substring matching. The previous
    version used `hint in lowered`, which meant short hints like "he"
    matched inside completely unrelated words like "the" — so nearly every
    English sentence (which almost always contains "the") was incorrectly
    flagged as a follow-up question. This silently caused standalone
    questions to go through unnecessary LLM-based rewriting whenever any
    conversation history existed, which is a real contributor to both the
    standalone-question regression and the follow-up regression reported.
    """
    return bool(_FOLLOW_UP_MATCHER.search(question)) or bool(_RELATIVE_POSITION_RE.search(question))


def is_definition_question(question: str) -> bool:
    return any(question.lower().strip().startswith(hint) for hint in DEFINITION_HINTS)


def is_process_question(question: str) -> bool:
    return any(hint in question.lower().strip() for hint in PROCESS_HINTS)


# The previous version of this check only matched 4 exact literal phrases
# ("list", "show me", "what are the steps", "sequence of steps") — so
# "Explain the Upgrade workflow", "Describe the Upgrade workflow", "Walk me
# through the Upgrade workflow", "Give me an overview of the Upgrade
# workflow", and "How does the Upgrade workflow work?" all fell through to
# normal RAG retrieval instead of the direct full-workflow parser, even
# though they express the exact same intent. Using regex with wildcards
# between key words (rather than literal substrings) so real phrasing that
# inserts a workflow name in between ("explain the UPGRADE workflow") still
# matches, instead of requiring an exact fixed phrase.
_FULL_WORKFLOW_INTENT_RE = re.compile(
    r"\blist\b"
    r"|\bshow\s+me\b"
    r"|\ball\s+(?:the\s+)?steps\b"
    r"|\bsequence\s+of\s+steps\b"
    r"|\bwhat\s+are\s+the\s+steps\b"
    r"|\bsteps\s+(?:for|in|of)\b"
    r"|\bcomplete\b.{0,40}\b(?:workflow|process)\b"
    r"|\bentire\b.{0,40}\b(?:workflow|process)\b"
    r"|\bstart\s+to\s+finish\b"
    r"|\bwalk\s+(?:me\s+)?through\b"
    r"|\boverview\s+of\b"
    r"|\bdescribe\b.{0,40}\b(?:workflow|process)\b"
    r"|\bexplain\b.{0,40}\b(?:workflow|process)\b"
    r"|\bhow\s+(?:does|do)\b.{0,40}\bwork\b",
    re.IGNORECASE,
)


def is_full_workflow_intent(question: str) -> bool:
    """True if the question intends a complete workflow explanation/listing,
    regardless of the specific wording used to ask for it."""
    return bool(_FULL_WORKFLOW_INTENT_RE.search(question))


# Comparative ("difference between X and Y") and aggregation ("which
# workflows contain Z") questions inherently need MULTIPLE only-moderately-
# relevant chunks assembled together — no single chunk can score high
# against "compare A and B" the way it could against a narrow single-fact
# question. These need different handling from the strict per-chunk
# rerank threshold (see the threshold gate in rag_answer for how this is used).
_BROAD_CONTEXT_RE = re.compile(
    r"\bdifference\s+between\b"
    r"|\bdiffers?\s+from\b|\bdiffering\s+from\b|\bdifferent\s+from\b|\bdiffers?\s+between\b"
    r"|\bstructurally\s+(?:similar|identical|different)\b"
    r"|\bcompare\b"
    r"|\bcompared\s+to\b"
    r"|\bversus\b|\bvs\.?\b"
    r"|\bin\s+both\b.{0,60}\band\b"
    r"|\bwhich\s+workflows?\s+(?:contains?|have|has|includes?|uses?)\b"
    r"|\bwhich\s+workflows?\b.{0,40}\bdescribed\s+as\b"
    r"|\bhow\s+many\s+workflows?\b"
    r"|\ball\s+workflows?\b"
    r"|\bsub-?variants?\b"
    r"|\bsub-?workflows?\b"
    r"|\bhow\s+many\b.{0,40}\b(?:are\s+there|does\b)\b",
    re.IGNORECASE,
)


def count_distinct_workflows_mentioned(question: str) -> int:
    """
    Counts how many distinct workflows are named in the question, using the
    same word-overlap approach as infer_workflow_type() but counting every
    workflow with a match instead of picking just the single best one.

    This exists because phrase-based detection ("difference between",
    "compare") is fundamentally fragile to real-world typos and rewording —
    a real reported case: "what is the difference BETTEN sr cancellation
    and so cancellation" (typo for "between") matched no phrase pattern at
    all, so the question was wrongly treated as narrow and refused, even
    though the exact same intent asked as a follow-up worked fine. Counting
    workflow NAME mentions is far more robust: it doesn't matter what word
    connects "SR Cancellation" and "SO Cancellation", or whether that
    connecting word is misspelled — both names being present is itself a
    strong, typo-proof signal that this is a comparative question.
    """
    query_words = set(normalize_text(question).split())
    workflow_map = scan_available_workflows()
    mentioned = 0
    for slug in workflow_map.keys():
        slug_words = set(slug.split("_"))
        # Subset, not overlap: "cancellation" alone overlaps with So/Sr/Tenancy
        # Cancellation all at once, which isn't actually distinguishing —
        # require every word of the slug to be present, not just one shared word.
        if slug_words.issubset(query_words):
            mentioned += 1
    return mentioned


def is_broad_context_question(question: str) -> bool:
    """
    True for questions that structurally need multiple, only-moderately-
    relevant chunks combined (full-workflow explanations, comparisons,
    aggregation across documents) — as opposed to narrow factual questions
    where a single chunk really should score highly if it's the right one.
    """
    return (
        is_full_workflow_intent(question)
        or is_complex_query(question)
        or bool(_BROAD_CONTEXT_RE.search(question))
        or count_distinct_workflows_mentioned(question) >= 2
    )


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


_SUBWORKFLOW_SECTION_RE = re.compile(
    r"^##\s*Sub-workflow\s+(\d+):\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)


def extract_subworkflow_sections(markdown: str) -> list[str]:
    """
    Extracts 'Sub-workflow N: Title' sections — used by documents (e.g.
    Disconnect/Reconnect) structured as several parallel independent
    sub-processes rather than one linear numbered step sequence, which
    extract_numbered_steps() cannot parse at all (it only recognizes bare
    "1. Step text" lines). Each sub-workflow is formatted as one summary
    line combining its title, responsible actor, and progression track.
    """
    matches = list(_SUBWORKFLOW_SECTION_RE.finditer(markdown))
    if not matches:
        return []

    sections = []
    for i, match in enumerate(matches):
        title = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        body = markdown[start:end]

        actor_match = re.search(r"-\s*Actor:\s*(.+)", body)
        progression_match = re.search(r"-\s*Progression Track:\s*(.+)", body)

        line = title
        if actor_match:
            line += f" (handled by {actor_match.group(1).strip()})"
        if progression_match:
            line += f" — {progression_match.group(1).strip()}"
        sections.append(line)

    return sections


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
    used_subworkflow_format = False
    if not steps:
        # Fall back to sub-workflow-style documents (parallel independent
        # processes rather than one linear numbered sequence) — see
        # extract_subworkflow_sections() for why this is a separate format.
        steps = extract_subworkflow_sections(markdown)
        used_subworkflow_format = bool(steps)
    if not steps:
        return None

    if used_subworkflow_format:
        lines = [
            f"The {workflow} workflow consists of {len(steps)} independent sub-workflows:", ""
        ]
    else:
        lines = [f"Based on the provided context, the {workflow} workflow has {len(steps)} steps:", ""]
    for i, step in enumerate(steps, start=1):
        lines.append(f"{i}. {step}")
    return "\n".join(lines), workflow


# ---------------------------------------------------------------------------
# Question rewriting for follow-ups
# ---------------------------------------------------------------------------
_PRONOUN_REFERENCE_HINTS = ("it", "this", "that", "they", "them", "there", "he", "she")
_PRONOUN_MATCHER = build_hint_matcher(_PRONOUN_REFERENCE_HINTS)


def has_unresolved_pronoun_reference(question: str) -> bool:
    """
    True if the question contains a bare pronoun/reference word that needs
    conversation history to resolve — distinct from is_explicit_topic_question,
    which only checks whether a workflow NAME is present. A question can do
    both at once: "How is THAT different from SR Cancellation?" names SR
    Cancellation explicitly, but "that" still needs resolving to whatever was
    discussed previously. Rewriting must not be skipped in that case.
    """
    return bool(_PRONOUN_MATCHER.search(question))


def rewrite_question(
    question: str,
    history: list[dict[str, str]],
    verbose: bool = False,
    langfuse_handler=None,
) -> str:
    if not history or is_definition_question(question):
        return question

    workflow_identifiable = is_explicit_topic_question(question)  # == infer_workflow_type(question) is not None
    looks_like_follow_up = is_follow_up_question(question)

    # Previously this only attempted rewriting when is_follow_up_question
    # matched a pronoun/phrase hint ("it", "that", "who approves", etc.).
    # That misses a real, distinct case: a question naming a specific but
    # workflow-AMBIGUOUS term ("what is the step after RFI(B)?" — RFI(B)
    # appears in both Share and Upgrade) has no pronoun and no follow-up
    # phrase, so it never looked like a follow-up — yet it still can't be
    # resolved to a single workflow without history. If the question can't
    # identify its own workflow AND history exists, that combination alone
    # is reason enough to attempt a history-informed rewrite, regardless of
    # whether it also happens to contain a pronoun.
    if not looks_like_follow_up and workflow_identifiable:
        return question  # fully self-contained — nothing for history to add

    # Previously this also skipped rewriting whenever is_explicit_topic_question
    # was true — but that's wrong when the question BOTH names a topic AND
    # contains an unresolved pronoun ("how is THAT different from SR
    # Cancellation?"). Only skip if there's truly nothing left to resolve.
    if workflow_identifiable and not has_unresolved_pronoun_reference(question):
        return question

    llm = build_llm()
    prompt = (
        "Rewrite the user's follow-up into a standalone question using the conversation "
        "history. Keep workflow names and entities explicit. "
        "IMPORTANT: when resolving a pronoun or reference (\"it\", \"that\", \"this\"), "
        "always resolve it to the MOST RECENT topic discussed in the conversation history "
        "below — not an earlier one, even if an earlier topic seems more prominent. "
        "The conversation may have moved from one workflow to another; always assume the "
        "reference points to whatever was discussed LAST, immediately before this question. "
        "Return only the rewritten question, with no extra text.\n\n"
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


def answer_from_conversation_memory(
    question: str,
    history: list[dict[str, str]],
    langfuse_handler=None,
) -> str:
    """
    Answers questions ABOUT the conversation itself (e.g. "summarize this
    conversation", "which workflow were we discussing") using ONLY the
    conversation history — never touches the document index, embeddings,
    retrieval, or reranking. This is a deliberately separate code path from
    the main RAG generation prompt, since the source of truth for these
    questions is what was actually said, not the workflow documents.
    """
    llm = build_llm()
    prompt = (
        "You are answering a question about the CONVERSATION ITSELF, not about "
        "telecom workflows or documents. Use ONLY the conversation history below "
        "to answer — do not invent, assume, or add anything that isn't actually "
        "present in the history. If the history doesn't contain enough to answer "
        "confidently, say so plainly.\n\n"
        f"Conversation History:\n{format_chat_history(history)}\n\n"
        f"Question: {question}\n\n"
        "Answer:"
    )
    response = llm.invoke(prompt, config={"callbacks": []})
    return response.content.strip()


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


def build_display_sources(
    scored_chunks: list[tuple],
    threshold: float,
    require_threshold: bool = True,
    min_floor: float = 0.05,
) -> list[dict]:
    """
    Builds the source list actually shown to the user in the UI: exactly
    ONE entry per workflow, at that workflow's single highest-scoring chunk.

    require_threshold=True (default — used for narrow factual questions):
    only workflows whose best chunk actually clears `threshold` are shown.
    A low score there genuinely signals the wrong/irrelevant chunk, so
    hiding it is the right call.

    require_threshold=False (used for broad/comparative/full-workflow
    questions): shows the best-scoring chunk per workflow even if it
    doesn't clear the strict `threshold` — for these question types, a
    moderate per-chunk score reflects question BREADTH (no single fragment
    can score high against "explain the whole workflow" or "compare X and
    Y"), not irrelevance. BUT this still requires clearing `min_floor` — a
    real reported bug showed workflows with a literal 0.000 score being
    displayed as if they were "evidence" for the answer, which is noise,
    not honesty. require_threshold=False relaxes the bar, it does not
    remove it entirely.

    This is still deliberately separate from what gets sent to the LLM as
    context (see is_broad_context_question in rag_answer) — this function
    only controls what's DISPLAYED as evidence, never what the LLM used to
    write the answer.
    """
    best_by_workflow: dict[str, float] = {}
    for doc, score in scored_chunks:
        workflow = doc.metadata.get("workflow", "Unknown")
        score = float(score)
        if require_threshold and score < threshold:
            continue
        if not require_threshold and score < min_floor:
            continue
        if workflow not in best_by_workflow or score > best_by_workflow[workflow]:
            best_by_workflow[workflow] = score

    return [
        {"workflow": workflow, "score": score}
        for workflow, score in sorted(best_by_workflow.items(), key=lambda item: item[1], reverse=True)
    ]


_WHICH_WORKFLOWS_CONTAIN_RE = re.compile(
    r"\bwhich\s+workflows?\s+(?:contains?|have|has|includes?|uses?|mentions?)\s+(.+?)\??\s*$",
    re.IGNORECASE,
)


def try_answer_workflow_aggregation_question(question: str) -> tuple[str, list[str]] | None:
    """
    'Which workflow(s) contain/have/include X' is fundamentally an
    exhaustive-match question — the correct answer requires checking EVERY
    workflow document, not finding the top-k most semantically similar
    chunks. A similarity-search pipeline structurally cannot guarantee this
    (it might easily surface chunks from only 2 of 4 workflows that
    actually contain the term, depending on incidental phrasing similarity).
    So for this specific question shape, we bypass retrieval entirely and
    do a direct, deterministic case-insensitive scan across every workflow
    source file — the same way a person would grep for the term.

    Returns (answer_text, matching_workflow_names) or None if the question
    doesn't match this pattern, or the term isn't found anywhere.
    """
    match = _WHICH_WORKFLOWS_CONTAIN_RE.search(question)
    if not match:
        return None
    term = match.group(1).strip().strip("?").strip()
    if not term or len(term) > 60:  # implausibly long "term" means the regex over-matched
        return None

    workflow_map = scan_available_workflows()
    term_lower = term.lower()
    matching_workflows: list[str] = []

    for slug, paths in workflow_map.items():
        for path in paths:
            try:
                content = path.read_text(encoding="utf-8").lower()
            except (OSError, UnicodeDecodeError):
                continue
            if term_lower in content:
                matching_workflows.append(slug.replace("_", " ").title())
                break

    if not matching_workflows:
        return None

    matching_workflows = sorted(set(matching_workflows))
    if len(matching_workflows) == 1:
        answer = f'Only the {matching_workflows[0]} workflow contains "{term}".'
    elif len(matching_workflows) == 2:
        answer = f'The following workflows contain "{term}": {matching_workflows[0]} and {matching_workflows[1]}.'
    else:
        listed = ", ".join(matching_workflows[:-1]) + f", and {matching_workflows[-1]}"
        answer = f'The following workflows contain "{term}": {listed}.'
    return answer, matching_workflows


def get_all_documents(vectorstore) -> list:
    """
    Returns every document chunk stored in the vectorstore — used to give
    BM25 an INDEPENDENT search pool, separate from whatever dense retrieval
    happened to narrow its own candidates down to. Previously BM25 searched
    only within dense's own deduplicated results, meaning BM25 could never
    recover a chunk dense missed — which defeats the entire point of hybrid
    retrieval (each method is supposed to catch what the other might not).
    """
    try:
        return list(vectorstore.docstore._dict.values())
    except AttributeError:
        # Degrade gracefully rather than crash if a different vectorstore
        # implementation doesn't expose docstore._dict the same way.
        return []


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
        return {"answer": str(exc), "sources": [], "error": "index_not_found", "contexts": []}

    # ── 2. Load memory ────────────────────────────────────────────────────
    history = load_chat_memory(session_id)
    early_inferred_wf = infer_workflow_type(question)
    early_is_explicit = is_explicit_topic_question(question)
    trace_metadata.update(
        {
            "history_turns": len(history),
            "is_follow_up_question": is_follow_up_question(question),
            "is_explicit_topic_question": early_is_explicit,
        }
    )

    # ── 3. Pre-retrieval guardrails (internal-leakage + no-history) ───────
    # Runs BEFORE the rewrite LLM call and BEFORE any retrieval, on the raw
    # question. This is deliberate: these are hard, deterministic refusals
    # that must not depend on the LLM choosing to refuse — they block the
    # question from ever reaching a place where an answer could be
    # fabricated. See guardrails.py for the full rationale.
    guardrail_refusal = check_pre_retrieval_guardrails(
        question=question,
        history=history,
        is_explicit_topic_question=early_is_explicit,
        inferred_workflow=early_inferred_wf,
    )
    if guardrail_refusal is not None:
        finalize_trace(
            guardrail_refusal, [],
            extra_metadata={
                "answer_mode": "guardrail_refusal",
                "guardrail_triggered": True,
            },
        )
        return {"answer": guardrail_refusal, "sources": [], "error": None, "contexts": []}

    # ── Meta-conversation routing ──────────────────────────────────────────
    # Questions ABOUT the conversation itself ("what did we discuss",
    # "summarize this conversation") are answered from session memory
    # DIRECTLY — they never reach document retrieval at all. The answer to
    # "which workflow were we talking about" lives in what was actually said
    # in this session, not in the workflow docs, so searching the docs for
    # it is both pointless and risks pulling in an unrelated "best available"
    # chunk. If there's no history, this falls back to the same no-history
    # refusal used elsewhere (check_pre_retrieval_guardrails already covers
    # most such cases, but this is a second, explicit guard specific to this
    # routing branch since meta-conversation intent is a distinct decision).
    if is_meta_conversation_question(question):
        if not history:
            finalize_trace(
                NO_HISTORY_REFUSAL, [],
                extra_metadata={"answer_mode": "meta_conversation_no_history"},
            )
            return {"answer": NO_HISTORY_REFUSAL, "sources": [], "error": None, "contexts": []}

        memory_answer = answer_from_conversation_memory(
            question, history, langfuse_handler=langfuse_handler,
        )
        save_chat_memory(history + [{"user": question, "assistant": memory_answer}], session_id)
        log_span(
            "meta_conversation_answer",
            input_data={"question": question},
            output_data={"answer": memory_answer},
            metadata={"history_turns": len(history), "bypassed_retrieval": True},
        )
        finalize_trace(
            memory_answer, [],
            extra_metadata={"answer_mode": "meta_conversation_from_memory"},
        )
        return {"answer": memory_answer, "sources": [], "error": None, "contexts": []}

    # ── Aggregation-question routing ────────────────────────────────────────
    # "Which workflows contain X" needs an exhaustive scan across every
    # workflow document, not a top-k similarity search — see
    # try_answer_workflow_aggregation_question() for why. This runs on the
    # raw question (not standalone_question) since it doesn't depend on
    # conversation history at all.
    aggregation_answer = try_answer_workflow_aggregation_question(question)
    if aggregation_answer is not None:
        answer_text, matched_workflows = aggregation_answer
        history.append({"user": question, "assistant": answer_text})
        save_chat_memory(history, session_id)
        sources = [{"workflow": wf, "score": 1.0} for wf in matched_workflows]
        log_span(
            "workflow_aggregation_scan",
            input_data={"question": question},
            output_data={"matched_workflows": matched_workflows},
            metadata={"bypassed_retrieval": True},
        )
        finalize_trace(
            answer_text, sources,
            extra_metadata={"answer_mode": "workflow_aggregation_scan"},
        )
        return {"answer": answer_text, "sources": sources, "error": None, "contexts": []}

    # ── 4. Rewrite follow-up ──────────────────────────────────────────────
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

    # ── 5. Workflow routing ───────────────────────────────────────────────
    inferred_wf = early_inferred_wf or infer_workflow_type(standalone_question)
    inferred_from_history = False
    if not inferred_wf and history:
        # The current question alone doesn't name a workflow — before
        # giving up, check what workflow the most recent turn was actually
        # about. This matters even when rewrite_question() didn't trigger
        # (e.g. relative-position phrasing not caught by is_follow_up_question
        # — a real reported case: "what is the step after RFI(B)?" after
        # discussing a specific workflow). Without this, such a question
        # searches the WHOLE corpus with no workflow scope at all, even
        # though a person would obviously read it as "in the workflow we
        # were just discussing".
        last_turn = history[-1]
        last_turn_text = f"{last_turn.get('user', '')} {last_turn.get('assistant', '')}"
        inferred_wf = infer_workflow_type(last_turn_text)
        inferred_from_history = bool(inferred_wf)

    trace_metadata.update(
        {
            "inferred_workflow": inferred_wf,
            "inferred_workflow_from_history_fallback": inferred_from_history,
            "standalone_question_is_follow_up": is_follow_up_question(standalone_question),
            "standalone_question_is_explicit_topic": is_explicit_topic_question(standalone_question),
        }
    )
    if verbose and inferred_wf:
        print(f"Router → target slug: {inferred_wf}")

    # ── 6. Dense retrieval (FAISS cosine) + threshold ────────────────────
    t_dense_start = datetime.now(timezone.utc)
    candidate_k = CANDIDATE_K
    trace_metadata["candidate_k"] = candidate_k
    dense_candidates: list[tuple] = []

    for retrieval_query in build_retrieval_queries(standalone_question):
        # With the index built as MAX_INNER_PRODUCT over normalized embeddings
        # (see ingest.py), this raw score IS exact cosine similarity — for
        # unit vectors, inner product and cosine similarity are the same
        # value by definition. No derived/transformed score needed here.
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

    # ── 7. BM25 retrieval (independent) ──────────────────────────────────
    t_bm25_start = datetime.now(timezone.utc)
    # BM25 now searches the FULL corpus independently of dense retrieval's
    # own results — get_all_documents() pulls every chunk from the
    # vectorstore directly. Optionally scoped to the inferred workflow
    # (same precision dense applies) when one is confidently known, but
    # computed independently rather than derived from dense's narrowed
    # candidate list, so BM25 can actually recover chunks dense missed.
    all_corpus_docs = get_all_documents(vectorstore)
    if inferred_wf:
        workflow_scoped_docs = [
            doc for doc in all_corpus_docs
            if doc.metadata.get("workflow_slug", "") == inferred_wf
        ]
        bm25_corpus = workflow_scoped_docs if workflow_scoped_docs else all_corpus_docs
    else:
        bm25_corpus = all_corpus_docs
    bm25_results = bm25_search(standalone_question, bm25_corpus, top_k=candidate_k)
    trace_metadata["bm25_result_count"] = len(bm25_results)
    trace_metadata["bm25_corpus_size"] = len(bm25_corpus)
    t_bm25_end = datetime.now(timezone.utc)

    # ── 8. RRF merge (dense + BM25) ───────────────────────────────────────
    t_rrf_start = datetime.now(timezone.utc)
    merged_results = merge_rrf(
        [dense_results, bm25_results],
        top_k=candidate_k,
    )
    trace_metadata["merged_result_count"] = len(merged_results)
    t_rrf_end = datetime.now(timezone.utc)

    if not merged_results:
        finalize_trace(
            LOW_CONFIDENCE_REFUSAL, [],
            extra_metadata={"answer_mode": "no_context", "refusal_reason": "no_merged_results"},
        )
        return {"answer": LOW_CONFIDENCE_REFUSAL, "sources": [], "error": None, "contexts": []}

    # ── 9. CrossEncoder reranking ─────────────────────────────────────────
    t_rerank_start = datetime.now(timezone.utc)
    reranked_results = rerank_results(standalone_question, merged_results, top_k=FINAL_K)
    trace_metadata["reranked_result_count"] = len(reranked_results)
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
                for i, (doc, score) in enumerate(dense_results[:candidate_k])
            ],
        },
        start_time=t_dense_start,
        end_time=t_dense_end,
        metadata={"retrieval_type": "dense_cosine", "inferred_workflow": inferred_wf},
    )

    log_span(
        "bm25_retrieval",
        input_data={"query": standalone_question, "total_docs": len(bm25_corpus)},
        output_data={
            "total_results": len(bm25_results),
            "chunks": [
                {
                    "rank": i + 1,
                    "workflow": doc.metadata.get("workflow", "Unknown"),
                    "bm25_score": round(float(score), 4),
                    "preview": doc.page_content[:200],
                }
                for i, (doc, score) in enumerate(bm25_results[:candidate_k])
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
                for i, (doc, score) in enumerate(merged_results[:candidate_k])
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
            "top_k": FINAL_K,
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

    # ── 10. Direct answer parser (attempted FIRST, before threshold gating) ─
    # This runs on reranked_results directly (pre-threshold) rather than
    # waiting for a confidence gate, because it works fundamentally
    # differently from the LLM generation path: once it identifies the
    # right workflow from even a single moderately-ranked chunk, it reads
    # the ENTIRE source markdown file directly and extracts the full step
    # list from there — it doesn't depend on any one chunk scoring high
    # against a broad "explain the whole workflow" question, which cross-
    # encoders structurally can't do well (no single fragment IS the whole
    # workflow, so no fragment scores high against that framing, even when
    # retrieval found exactly the right document).
    use_direct_parser = (
        is_process_question(standalone_question)
        and is_full_workflow_intent(standalone_question)
        and not is_complex_query(standalone_question)
    )
    trace_metadata["use_direct_parser"] = use_direct_parser

    if use_direct_parser:
        direct_answer = build_process_direct_answer(standalone_question, reranked_results)
        if direct_answer:
            answer_text, matched_workflow = direct_answer
            history.append({"user": question, "assistant": answer_text})
            save_chat_memory(history, session_id)

            matching_chunks = [
                (doc, score) for doc, score in reranked_results
                if doc.metadata.get("workflow") == matched_workflow
            ]
            # Unlike the LLM-generation path, the direct parser's correctness
            # does NOT depend on any individual chunk's rerank score — it
            # reads the whole source file directly once it identifies the
            # right workflow. A fragment naturally scores low against a
            # broad "explain everything" framing even when it's from
            # exactly the right document (see is_broad_context_question
            # above), so gating the source display on that score was
            # hiding evidence for answers that were already known correct.
            # Always show the matched workflow here, using its best
            # available score honestly — even if that score is low, it's
            # still telling the truth about which document the (correct)
            # answer came from.
            if matching_chunks:
                sources = build_display_sources(matching_chunks, RERANK_THRESHOLD, require_threshold=False)
            else:
                sources = []
            finalize_trace(
                answer_text,
                sources,
                extra_metadata={
                    "answer_mode": "direct_parser",
                    "matched_workflow": matched_workflow,
                },
            )
            return {
                "answer": answer_text,
                "sources": sources,
                "error": None,
                "contexts": [doc.page_content for doc, _ in reranked_results],
            }

    # ── 11. Post-rerank relevance threshold gate ────────────────────────────
    # This is the core hallucination-prevention mechanism for NARROW factual
    # questions, where a single chunk really should score high if it's the
    # right one — low score there genuinely signals irrelevant context.
    #
    # It is RELAXED for broad/comparative/aggregation questions (full-workflow
    # explanations that skipped or failed the direct parser above, "compare X
    # and Y", "which workflows contain Z") — these inherently need multiple
    # only-moderately-relevant chunks assembled together, and gating on any
    # one chunk's isolated score would refuse questions that are genuinely
    # answerable from the combined context. For these, we still pass
    # everything through the CONTEXT_GOVERNANCE_PROMPT, which explicitly
    # instructs the LLM to refuse honestly if the assembled context still
    # isn't sufficient — so this isn't an unguarded bypass, it's shifting
    # the "is this enough" judgment from a per-chunk number to the LLM's own
    # holistic read of all the assembled context together.
    broad_question = is_broad_context_question(standalone_question)
    trace_metadata["broad_context_question"] = broad_question

    qualified_results = [
        (doc, score) for doc, score in reranked_results if score >= RERANK_THRESHOLD
    ]
    top_rerank_score = round(float(reranked_results[0][1]), 4) if reranked_results else None
    trace_metadata.update(
        {
            "rerank_threshold": RERANK_THRESHOLD,
            "qualified_result_count": len(qualified_results),
            "top_rerank_score": top_rerank_score,
        }
    )

    if not qualified_results and not broad_question:
        finalize_trace(
            LOW_CONFIDENCE_REFUSAL, [],
            extra_metadata={
                "answer_mode": "low_confidence_refusal",
                "top_rerank_score": top_rerank_score,
            },
        )
        return {"answer": LOW_CONFIDENCE_REFUSAL, "sources": [], "error": None, "contexts": []}

    if broad_question and not qualified_results:
        # Nothing cleared the strict bar, but this is a broad question where
        # that's expected — fall back to the raw reranked set (still
        # genuinely the best-available evidence, just not all individually
        # "highly confident") and let the LLM judge sufficiency itself.
        results = reranked_results
    else:
        results = qualified_results

    # ── 12. LLM generation ────────────────────────────────────────────────
    context = format_context(results)
    llm = build_llm()

    prompt = (
        f"{CONTEXT_GOVERNANCE_PROMPT}\n\n"
        "You are a telecom workflow assistant. Use the conversation history for follow-up "
        "questions, but answer using only the provided context. "
        f'If the context does not fully answer the question, respond with EXACTLY this '
        f'phrase and nothing else: "{LOW_CONFIDENCE_REFUSAL}" — do not improvise your own '
        "wording for a refusal, and do not partially answer with a caveat; either answer "
        "properly from the context or use the exact refusal phrase above. "
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

    # If the LLM judged the context insufficient and used the refusal phrase,
    # sources must be empty too — a refusal should never be shown alongside
    # "N sources used", even if those sources technically cleared the
    # earlier rerank threshold. Confidence and displayed evidence must agree.
    if answer_clean.strip() == LOW_CONFIDENCE_REFUSAL:
        sources = []
    else:
        # Narrow questions: strict (a low score genuinely means wrong chunk).
        # Broad questions: show the best available evidence per workflow
        # even if it doesn't clear the strict bar — hiding sources entirely
        # for a correct, well-grounded broad answer looked unsupported and
        # was flagged as confusing on the frontend.
        sources = build_display_sources(results, RERANK_THRESHOLD, require_threshold=not broad_question)

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

    return {
        "answer": answer_clean,
        "sources": sources,
        "error": None,
        "contexts": [doc.page_content for doc, _ in results],
    }


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