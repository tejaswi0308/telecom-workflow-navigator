import argparse

try:
    from backend.utils import build_retrieval_queries, get_index_path, load_vectorstore, merge_scored_results, strip_markdown_formatting
except ImportError:
    from utils import build_retrieval_queries, get_index_path, load_vectorstore, merge_scored_results, strip_markdown_formatting    


def search(query: str, top_k: int = 3) -> None:
    index_path = get_index_path()

    print(f"Loading FAISS index from {index_path}...")
    vectorstore = load_vectorstore(index_path)

    print(f"Searching for: {query}")
    candidate_k = max(top_k * 3, top_k + 5)
    candidates = []
    for retrieval_query in build_retrieval_queries(query):
        candidates.extend(vectorstore.similarity_search_with_score(retrieval_query, k=candidate_k))
    results = merge_scored_results(candidates, top_k)

    if not results:
        print("No matches found.")
        return

    for rank, (document, score) in enumerate(results, start=1):
        workflow = document.metadata.get("workflow", "Unknown")
        source = document.metadata.get("source", workflow)
        content = strip_markdown_formatting(document.page_content.strip()).replace("\n", " ")
        preview = content[:500] + ("..." if len(content) > 500 else "")

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