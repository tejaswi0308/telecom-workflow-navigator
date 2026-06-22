import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS


load_dotenv()


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


def search(query: str, top_k: int = 3) -> None:
    backend_dir = Path(__file__).resolve().parent
    index_path = backend_dir.parent / "faiss_index"

    print(f"Loading FAISS index from {index_path}...")
    vectorstore = load_vectorstore(index_path)

    print(f"Searching for: {query}")
    results = vectorstore.similarity_search_with_score(query, k=top_k)

    if not results:
        print("No matches found.")
        return

    for rank, (document, score) in enumerate(results, start=1):
        workflow = document.metadata.get("workflow", "Unknown")
        source = document.metadata.get("source", workflow)
        content = document.page_content.strip().replace("\n", " ")
        preview = content[:300] + ("..." if len(content) > 300 else "")

        print(f"\nResult {rank}")
        print(f"Workflow: {workflow}")
        print(f"Source: {source}")
        print(f"Score: {score}")
        print(f"Preview: {preview}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Search indexed telecom workflows")
    parser.add_argument("query", help="Search text to look up in the FAISS index")
    parser.add_argument("--top-k", type=int, default=3, help="Number of matches to show")
    args = parser.parse_args()

    search(args.query, top_k=args.top_k)


if __name__ == "__main__":
    main()