from pathlib import Path

from dotenv import load_dotenv
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS


load_dotenv()

# ── 1. Load all markdown files from data folder ──────────────────────────────
print("Loading workflow markdown files...")

backend_dir = Path(__file__).resolve().parent
data_path = backend_dir.parent / "data"

loader = DirectoryLoader(
    str(data_path),
    glob="**/*.md",
    loader_cls=TextLoader,
    loader_kwargs={"encoding": "utf-8"},
    show_progress=True,
)

documents = loader.load()

print(f"Loaded {len(documents)} workflow files")

# ── 2. Split by markdown headers and tag metadata ────────────────────────────
print("Chunking by headers and tagging metadata...")

headers_to_split_on = [
    ("#", "workflow_title"),
    ("##", "section"),
    ("###", "step"),
]

splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=headers_to_split_on,
    strip_headers=False
)

all_chunks = []

for document in documents:
    workflow_name = Path(document.metadata["source"]).stem.replace("_", " ").title()
    chunks = splitter.split_text(document.page_content)
    for chunk in chunks:
        # Add workflow name as metadata on every chunk
        chunk.metadata["workflow"] = workflow_name
        chunk.metadata["source"] = workflow_name
        all_chunks.append(chunk)

print(f"Total chunks created: {len(all_chunks)}")

# ── 3. Create embeddings ──────────────────────────────────────────────────────
print("Loading embedding model...")

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={"device": "cpu"}
)

# ── 4. Store in FAISS ─────────────────────────────────────────────────────────
print("Creating FAISS vector store... this may take a minute")

vectorstore = FAISS.from_documents(all_chunks, embeddings)

# Save locally
faiss_path = backend_dir.parent / "faiss_index"
vectorstore.save_local(faiss_path)

print(f"Vector store saved to {faiss_path}")
print(f"Total chunks indexed: {len(all_chunks)}")
print("Ingestion complete!")