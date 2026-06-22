import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq


load_dotenv()

MEMORY_TURNS = 6
WORKFLOW_TOPIC_HINTS = (
    "amendment",
    "disconnect reconnect",
    "hold unhold",
    "mobile dg",
    "share",
    "so cancellation",
    "sr cancellation",
    "tenancy cancellation",
    "upgrade",
)
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


def build_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
    )


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
        sections.append(
            f"[{index}] Workflow: {workflow}\nSource: {source}\nScore: {score}\nContent:\n{document.page_content.strip()}"
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
    lowered = question.lower()
    return any(hint in lowered for hint in WORKFLOW_TOPIC_HINTS)


def is_follow_up_question(question: str) -> bool:
    lowered = question.lower()
    return any(hint in lowered for hint in FOLLOW_UP_HINTS)


def is_definition_question(question: str) -> bool:
    lowered = question.lower().strip()
    return any(lowered.startswith(hint) for hint in DEFINITION_HINTS)


def extract_explicit_workflow(question: str) -> str | None:
    """Return a normalized workflow hint if the question explicitly mentions one."""
    lowered = question.lower()
    for hint in WORKFLOW_TOPIC_HINTS:
        if hint in lowered:
            return hint
    return None


def rewrite_question(question: str, history: list[dict[str, str]], verbose: bool = False) -> str:
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

    response = llm.invoke(prompt)
    rewritten = response.content.strip()
    if verbose and rewritten and rewritten != question:
        print(f"Rewritten question: {rewritten}")
    return rewritten or question


def rag_answer(question: str, top_k: int = 4, verbose: bool = False) -> None:
    backend_dir = Path(__file__).resolve().parent
    index_path = backend_dir.parent / "faiss_index"

    vectorstore = load_vectorstore(index_path)

    history = load_chat_memory()
    standalone_question = rewrite_question(question, history, verbose=verbose)

    # Bias retrieval toward an explicitly named workflow when present.
    explicit_wf = extract_explicit_workflow(standalone_question)
    # Retrieve extra candidates so we can filter down to the requested workflow
    candidate_k = max(top_k * 3, top_k + 5)
    candidates = vectorstore.similarity_search_with_score(standalone_question, k=candidate_k)

    if explicit_wf:
        filtered = [pair for pair in candidates if explicit_wf in pair[0].metadata.get("workflow", "").lower()]
        if filtered:
            results = filtered[:top_k]
        else:
            # fallback to top candidates if no filtered matches
            results = candidates[:top_k]
    else:
        results = candidates[:top_k]

    if not results:
        print("No relevant context found.")
        return

    context = format_context(results)
    llm = build_llm()

    prompt = (
        "You are a telecom workflow assistant. Use the conversation history for follow-up "
        "questions, but answer using only the provided context. If the answer is not in the "
        "context, say that you could not find it. Be concise, accurate, and reference the "
        "workflow names when useful. When you reference a context chunk, cite it using the "
        "bracketed index from the Context (for example: [1], [2]).\n\n"
        f"Conversation History:\n{format_chat_history(history)}\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {standalone_question}\n\n"
        "Answer:"
    )

    response = llm.invoke(prompt)

    print("\nAnswer")
    answer = response.content.strip()
    print(answer)

    history.append({"user": question, "assistant": answer})
    save_chat_memory(history)

    print("\nSources")
    seen = set()
    for idx, (document, score) in enumerate(results, start=1):
        workflow = document.metadata.get("workflow", "Unknown")
        if workflow in seen:
            continue
        seen.add(workflow)
        print(f"- [{idx}] {workflow} (score: {score})")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG query over indexed telecom workflows")
    parser.add_argument("question", help="Question to answer from the workflow index")
    parser.add_argument("--top-k", type=int, default=4, help="Number of documents to retrieve")
    parser.add_argument("--verbose", action="store_true", help="Print internal retrieval and rewrite logs")
    args = parser.parse_args()

    rag_answer(args.question, top_k=args.top_k, verbose=args.verbose)


if __name__ == "__main__":
    main()