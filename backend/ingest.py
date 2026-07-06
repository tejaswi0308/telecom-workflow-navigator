from pathlib import Path

from dotenv import load_dotenv
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS


load_dotenv()

# Acronyms that .title() lowercases incorrectly
ACRONYMS = ["Dg", "So ", "Sr "]

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
    stem = Path(document.metadata["source"]).stem
    workflow_name = stem.replace("_", " ").title()

    for acronym in ACRONYMS:
        workflow_name = workflow_name.replace(acronym, acronym.upper())

    workflow_slug = stem.lower().replace("_workflow", "")
    chunks = splitter.split_text(document.page_content)

    for chunk in chunks:
        chunk.metadata["workflow"]      = workflow_name
        chunk.metadata["source"]        = workflow_name
        chunk.metadata["workflow_slug"] = workflow_slug

    all_chunks.extend(chunks)

print(f"Total chunks created: {len(all_chunks)}")

# ── 3. Create embeddings ──────────────────────────────────────────────────────
print("Loading embedding model...")

embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-large-en-v1.5",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

# ── 4. Store in FAISS ─────────────────────────────────────────────────────────
print("Creating FAISS vector store... this may take a minute")

vectorstore = FAISS.from_documents(all_chunks, embeddings)

faiss_path = backend_dir.parent / "faiss_index"
vectorstore.save_local(faiss_path)

print(f"Vector store saved to {faiss_path}")
print(f"Total chunks indexed: {len(all_chunks)}")
print("Ingestion complete!")