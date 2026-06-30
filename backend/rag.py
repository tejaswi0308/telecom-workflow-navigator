import argparse
import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()

from langchain_groq import ChatGroq
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from utils import (
    build_retrieval_queries,
    clean_section_title,
    get_index_path,
    infer_workflow_type,
    load_vectorstore,
    merge_scored_results,
    normalize_text,
    strip_markdown_formatting,
    workflow_markdown_path,
)

MEMORY_TURNS = 6

# Follow-up detection — these are conversational pronouns and phrases that signal
# the question refers to a prior turn rather than being self-contained.
FOLLOW_UP_HINTS = (
    "it",
    "this",
    "that",
    "they",
    "them",
    "there",
    "he",
    "she",
    "who approves",
    "what happens next",
    "what happens after",
    "and then",
    "next step",
    "after that",
)

DEFINITION_HINTS = (
    "what is",
    "who is",
    "define",
    "what are",
)

PROCESS_HINTS = (
    "step",
    "steps",
    "process",
    "procedure",
    "sequence",
    "workflow",
    "how many",
)

# Complex query keywords that should always go to the LLM and never be
# intercepted by the programmatic direct-answer parser.
COMPLEX_QUERY_HINTS = (
    "approval",
    "hierarchy",
    "chain",
    "corporate",
    "executive",
    "actor",
    "complete",
    "full",
    "detail",
    "list all",
    "entire",
)


def build_llm() -> ChatGroq:
    model_name = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    return ChatGroq(
        model=model_name,
        temperature=0,
    )


def format_context(results) -> str:
    sections = []
    for index, (document, score) in enumerate(results, start=1):
        workflow = document.metadata.get("workflow", "Unknown")
        source = document.metadata.get("source", workflow)
        content = document.page_content.strip()
        sections.append(
            f"[{index}] Workflow: {workflow}\nSource: {source}\nScore: {score}\nContent:\n{content}"
        )
    return "\n\n".join(sections)


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


def is_explicit_topic_question(question: str) -> bool:
    """Uses dynamic workflow inference instead of hardcoded hints."""
    return infer_workflow_type(question) is not None


def is_follow_up_question(question: str) -> bool:
    lowered = question.lower()
    return any(hint in lowered for hint in FOLLOW_UP_HINTS)


def is_definition_question(question: str) -> bool:
    lowered = question.lower().strip()
    return any(lowered.startswith(hint) for hint in DEFINITION_HINTS)


def is_process_question(question: str) -> bool:
    lowered = question.lower().strip()
    return any(hint in lowered for hint in PROCESS_HINTS)


def is_complex_query(question: str) -> bool:
    """
    Returns True if the question contains keywords indicating it needs
    full LLM reasoning over retrieved context rather than programmatic parsing.
    These queries must never be intercepted by the direct-answer parser.
    """
    lowered = question.lower()
    return any(hint in lowered for hint in COMPLEX_QUERY_HINTS)


def build_answering_hint(question: str) -> str:
    lowered = question.lower()
    hints = []

    if any(keyword in lowered for keyword in ("sop", "procedure", "workflow", "steps", "how do")):
        hints.append(
            "Treat this as a process question and summarize the workflow steps in order, "
            "even if the word SOP does not appear in the docs."
        )

    if any(keyword in lowered for keyword in ("billing", "commercial", "revenue", "rfi b", "rfi(b)")):
        hints.append(
            "Focus on commercial and billing checkpoints such as Service Order, RFI(P), "
            "RFI(B), OBRM, and approval gates."
        )

    if any(keyword in lowered for keyword in ("edge case", "exception", "what if", "if rejected", "fallback")):
        hints.append(
            "Include rejection loops, alternate paths, and exception handling when they "
            "are present in the context."
        )

    if any(keyword in lowered for keyword in ("approval", "hierarchy", "chain", "corporate", "executive", "actor")):
        hints.append(
            "List all actors and their roles in the approval chain in the order they appear. "
            "Include both Circle-level and Corporate/National-level approvers. "
            "Note any rejection or rework paths at each approval stage."
        )

    if not hints:
        return ""

    return " ".join(hints)


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

    lowered = question.lower()
    if "step" in lowered:
        match = re.search(
            r"step\s+(?:'|\")?([^'\"?]+?)(?:'|\")?(om\s+and\s+where|\s+where|\?|$)",
            question,
            flags=re.I,
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
        key=lambda section: score_section(question, section[0], section[1]),
    )

    if score_section(question, best_title, best_content) <= 0:
        return markdown

    return best_content or markdown


def extract_numbered_steps(section_text: str) -> list[str]:
    steps: list[str] = []
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        match = re.match(r"^\d+\.\s+(.+)$", line)
        if not match:
            continue

        step_text = match.group(1).strip()
        step_text = step_text.replace("**", "")
        step_text = re.sub(r"\s+\*\(.*\)\*$", "", step_text).strip()
        steps.append(step_text)

    return steps


def extract_numbered_step_pairs(section_text: str) -> list[tuple[int, str]]:
    steps: list[tuple[int, str]] = []
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        match = re.match(r"^(\d+)\.\s+(.+)$", line)
        if not match:
            continue

        step_number = int(match.group(1))
        step_text = match.group(2).strip()
        step_text = step_text.replace("**", "")
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
            step_normalized = normalize_text(step_text)
            if target_normalized and target_normalized in step_normalized:
                surrounding_steps: list[str] = []
                step_position = index - 1
                for surrounding_index, surrounding_text in step_pairs[
                    max(0, step_position - 1): min(len(step_pairs), step_position + 2)
                ]:
                    surrounding_steps.append(f"{surrounding_index}. {surrounding_text}")
                return clean_section_title(title), index, surrounding_steps

    return None


def select_matching_workflow_result(question: str, results):
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


def build_process_direct_answer(question: str, results) -> tuple[str, str] | None:
    selected = select_matching_workflow_result(question, results)
    if not selected:
        return None

    document, _score, markdown_path, markdown = selected
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
    steps = extract_numbered_steps(section)

    if not steps:
        steps = extract_numbered_steps(markdown)

    if not steps:
        return None

    title = f"Based on the provided context, the {workflow} workflow has {len(steps)} steps:"
    lines = [title, ""]
    for index, step in enumerate(steps, start=1):
        lines.append(f"{index}. {step}")
    return "\n".join(lines), workflow


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


def _has_structured_content(text: str) -> bool:
    """
    Returns True if the answer contains structured markdown formatting
    (bold markers, arrows, approval chains) that should be preserved.
    Stripping such answers would destroy meaningful structure.
    """
    if re.search(r"\*\*[^*]+\*\*", text):
        return True
    if "→" in text or "->" in text:
        return True
    return False


def _build_langfuse_handler() -> CallbackHandler | None:
    """
    Initialises the Langfuse singleton (if credentials are present) and
    returns a CallbackHandler bound to it. Returns None if Langfuse is not
    configured, so tracing is optional rather than a hard requirement.
    """
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")

    if not public_key or not secret_key:
        return None

    Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        host=os.getenv("LANGFUSE_BASE_URL"),
    )
    return CallbackHandler()


def rag_answer(question: str, top_k: int = 8, verbose: bool = False) -> dict:
    """
    Core RAG entry point. Returns a structured result instead of printing,
    so it can be reused by both the CLI (main()) and the FastAPI layer.

    Return shape:
    {
        "answer": str,
        "sources": [{"workflow": str, "score": float}, ...],
        "error": str | None,   # set if something went wrong, answer/sources still safe defaults
    }
    """
    langfuse_handler = _build_langfuse_handler()

    index_path = get_index_path()

    try:
        vectorstore = load_vectorstore(index_path)
    except FileNotFoundError as exc:
        return {"answer": str(exc), "sources": [], "error": "index_not_found"}

    history = load_chat_memory()
    standalone_question = rewrite_question(
        question,
        history,
        verbose=verbose,
        langfuse_handler=langfuse_handler,
    )

    if (
        is_follow_up_question(standalone_question)
        and not is_explicit_topic_question(standalone_question)
        and not history
    ):
        answer = (
            "I'm sorry, but your question refers to a previous topic, and there is no "
            "active chat history saved. Could you please specify which workflow you are "
            "talking about?"
        )
        return {"answer": answer, "sources": [], "error": None}

    # Dynamic workflow router — no hardcoded strings
    inferred_wf = infer_workflow_type(question) or infer_workflow_type(standalone_question)
    if verbose and inferred_wf:
        print(f"Dynamic Router isolated target slug: {inferred_wf}")

    candidate_k = max(top_k * 3, top_k + 5)
    candidates = []
    for retrieval_query in build_retrieval_queries(standalone_question):
        candidates.extend(
            vectorstore.similarity_search_with_score(retrieval_query, k=candidate_k)
        )

    # Filter to inferred workflow if confident, else use all candidates
    if inferred_wf:
        filtered = [
            pair for pair in candidates
            if inferred_wf == pair[0].metadata.get("workflow_slug", "")
        ]
        results = merge_scored_results(filtered, top_k) if filtered else merge_scored_results(candidates, top_k)
    else:
        results = merge_scored_results(candidates, top_k)

    if not results:
        return {"answer": "No relevant context found.", "sources": [], "error": None}

    # Direct answer parser — only for simple list/step questions.
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

            sources = []
            for document, score in results:
                workflow = document.metadata.get("workflow", "Unknown")
                if workflow == matched_workflow:
                    sources.append({"workflow": workflow, "score": float(score)})

            return {"answer": answer_text, "sources": sources, "error": None}

    # LLM path — used for all complex, approval, hierarchy, and general questions
    context = format_context(results)
    llm = build_llm()

    prompt = (
        "You are a telecom workflow assistant. Use the conversation history for follow-up "
        "questions, but answer using only the provided context. If the answer is not in the "
        "context, say that you could not find it. Be concise, accurate, and reference the "
        "workflow names when useful. When you reference a context chunk, cite it using the "
        "bracketed index from the Context (for example: [1], [2]).\n"
        f"Answering guidance: {build_answering_hint(standalone_question)}\n\n"
        f"Conversation History:\n{format_chat_history(history)}\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {standalone_question}\n\n"
        "Answer:"
    )

    callbacks = [langfuse_handler] if langfuse_handler else []
    response = llm.invoke(prompt, config={"callbacks": callbacks})

    answer = response.content.strip()

    if _has_structured_content(answer):
        answer_clean = answer
    else:
        answer_clean = strip_markdown_formatting(answer)

    history.append({"user": question, "assistant": answer_clean})
    save_chat_memory(history)

    sources = []
    seen = set()
    for document, score in results:
        workflow = document.metadata.get("workflow", "Unknown")
        if workflow in seen:
            continue
        seen.add(workflow)
        sources.append({"workflow": workflow, "score": float(score)})

    return {"answer": answer_clean, "sources": sources, "error": None}


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG query over indexed telecom workflows")
    parser.add_argument("question", help="Question to answer from the workflow index")
    parser.add_argument("--top-k", type=int, default=4, help="Number of documents to retrieve")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print internal retrieval and rewrite logs",
    )
    args = parser.parse_args()

    result = rag_answer(args.question, top_k=args.top_k, verbose=args.verbose)

    print("\nAnswer")
    print(result["answer"])

    if result["sources"]:
        print("\nSources")
        for idx, source in enumerate(result["sources"], start=1):
            print(f"- [{idx}] {source['workflow']} (score: {source['score']})")


if __name__ == "__main__":
    main()