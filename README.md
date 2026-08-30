# Telecom Workflow Navigator

A Retrieval-Augmented Generation (RAG) based conversational assistant that answers natural-language questions about complex, multi-actor operational workflows — with source citations, and built-in safeguards against hallucinated responses.

Built as part of an industry internship project involving a telecom infrastructure organization managing tens of thousands of operational sites across multiple regions.

---

## 📌 The Problem

Large operational organizations often run on multi-actor, multi-stage approval workflows — provisioning requests, upgrades, amendments, and cancellations — documented only as static, unstructured PDF flowcharts.

Finding an answer to an operational question (a specific step, an approving actor, or the outcome of a rejection) typically requires manually searching dense documents or relying on the tribal knowledge of experienced staff — a process that doesn't scale and leaves no auditable trail.

**Telecom Workflow Navigator** replaces that with an instant, natural-language, source-cited question-answering system that is grounded strictly in the actual workflow documentation, and explicitly refuses to answer rather than fabricate a response when the evidence is insufficient.

---

## 🏗️ Architecture

```
Workflow PDFs
      │
      ▼
Structured Markdown (header-aware chunking)
      │
      ▼
┌─────────────────────────────────────────────┐
│              Hybrid Retrieval                │
│   FAISS (dense/semantic)  +  BM25 (sparse)   │
└─────────────────────────────────────────────┘
      │
      ▼
Reciprocal Rank Fusion (RRF)
      │
      ▼
Cross-Encoder Reranking (BAAI/bge-reranker-large)
      │
      ▼
Confidence Threshold Gate ──► [insufficient evidence] ──► Refusal
      │
      ▼ [confident]
LLM Generation (context-grounded, refusal-capable prompt)
      │
      ▼
Source-Cited Response
```

Every stage is traced end-to-end via **Langfuse**, and the whole pipeline is scored quantitatively via **RAGAS**.

### Five-layer system design

| Layer | Responsibility |
|---|---|
| **Presentation** | React chat UI — source citations, session handling, feedback |
| **Application** | FastAPI backend — `/api/ask`, `/api/feedback`, `/api/workflows`, `/api/index/status` |
| **Retrieval** | Hybrid search (FAISS + BM25) → RRF → Cross-Encoder reranking → confidence gating |
| **Knowledge** | Offline ingestion — Markdown chunking, embedding generation, FAISS index build |
| **Persistence & Observability** | SQLite (feedback), per-session JSON (conversation memory), Langfuse (tracing) |

---

## ✨ Key Features

- **Hybrid retrieval** — combines dense semantic search (FAISS) with sparse keyword search (BM25), merged via Reciprocal Rank Fusion, so both paraphrased and exact-term queries are handled well
- **Cross-Encoder reranking** — rescoring the merged shortlist with `BAAI/bge-reranker-large` for higher precision than either retrieval method alone
- **Confidence-gated generation** — a per-chunk relevance threshold that causes the system to refuse rather than guess when retrieved evidence is weak; relaxed intelligently for broad/comparative questions that require synthesizing multiple only-moderately-relevant chunks
- **Deterministic, code-level guardrails** — regex-based checks (not just prompt instructions) block internal-implementation leakage and unresolved-context questions before any LLM call is made
- **Conversational memory** — session-scoped follow-up handling, including pronoun resolution, relative-position references ("what's the step after that?"), and meta-conversation questions ("what did we just discuss?")
- **Deterministic bypass paths** — full "list the steps" and "which workflow(s) contain X" question types are answered by direct document parsing rather than chunk-level retrieval, since no single chunk can represent an entire workflow
- **LLM-provider agnostic** — a single `build_llm()` factory abstracts the LLM backend, so the retrieval pipeline required zero changes when migrating providers
- **Full observability** — every pipeline stage (retrieval, RRF, reranking, generation) is traced in Langfuse with latency and token-usage metrics
- **Quantitative evaluation** — a RAGAS-based harness scores Faithfulness, Answer Relevancy, Context Precision, and Context Recall against a curated evaluation dataset

---

## 📊 Evaluation Results

Evaluated on a curated 20-question dataset (19 answerable, 1 refused) using the [RAGAS](https://docs.ragas.io/) framework:

| Metric | Score |
|---|---|
| **Faithfulness** | 0.9342 |
| **Answer Relevancy** | 0.8084 |
| **Context Precision** | 1.000 |
| **Context Recall** | 0.9737 |

Additionally validated through manual testing across **1,300+ domain-specific queries**, spanning workflow explanations, comparisons, follow-up conversations, and adversarial edge cases (internal-system probing, context-dependent questions with no prior turn, meta-conversation questions).

---

## 🛠️ Tech Stack

| Category | Tools |
|---|---|
| **Orchestration** | LangChain |
| **Retrieval** | FAISS, `rank_bm25` |
| **Embeddings / Reranking** | `BAAI/bge-large-en-v1.5`, `BAAI/bge-reranker-large` |
| **Backend** | FastAPI, Pydantic |
| **Frontend** | React, react-markdown |
| **Persistence** | SQLite |
| **Observability** | Langfuse |
| **Evaluation** | RAGAS |
| **LLM Provider** | Groq / Azure OpenAI (swappable) |

---

## 📁 Project Structure

```
telecom_workflow_navigator/
├── backend/
│   ├── main.py              # FastAPI: routes, request/response models
│   ├── rag.py                # Core pipeline: rag_answer() + routing
│   ├── utils.py               # Embeddings, FAISS I/O, BM25, RRF, rerank
│   ├── guardrails.py          # Deterministic pre-retrieval safety checks
│   ├── memory.py               # Per-session conversation memory
│   ├── db.py                    # SQLite persistence for feedback
│   ├── ingest.py                 # Markdown → chunks → embeddings → FAISS
│   ├── evaluate_ragas.py          # Standalone RAGAS evaluation harness
│   └── qna_eval_dataset.json       # Curated evaluation set
├── data/
│   └── *.md                          # Structured workflow Markdown documents
├── faiss_index/                        # Serialized FAISS vector store
└── frontend/
    └── src/
        └── components/                   # ChatPage, Sidebar, MessageBubble, etc.
```

> **Note:** The `data/` folder in this repo contains sample/synthetic workflow documents only. Original source documents used during development are proprietary and are not included.

---

## 🚀 Getting Started

### Prerequisites

- Python 3.12+
- Node.js (for the frontend)
- An LLM provider API key (Groq or Azure OpenAI)

### Backend Setup

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install fastapi uvicorn langchain langchain-community langchain-huggingface \
            langchain-openai langchain-groq langchain-text-splitters \
            faiss-cpu sentence-transformers rank-bm25 python-dotenv
```

Configure your `.env` file inside `backend/`:

```bash
LLM_PROVIDER=groq              # or "azure"
GROQ_MODEL=llama-3.1-8b-instant
# Azure vars if LLM_PROVIDER=azure:
# AZURE_OPENAI_API_KEY / _ENDPOINT / _DEPLOYMENT_NAME
```

Build the FAISS index from the workflow Markdown files:

```bash
python ingest.py
```

Run the API:

```bash
python main.py    # or: uvicorn main:app --reload
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev       # Vite dev server, defaults to :5173
```

### (Optional) Run Evaluation

```bash
cd backend
pip install ragas datasets
python evaluate_ragas.py --dataset qna_eval_dataset.json --output eval_results.csv
```

---

## 🔌 Core API

**`POST /api/ask`**
```json
{ "question": "string", "top_k": 3, "session_id": "string" }
```
```json
{ "answer": "string", "sources": [{ "workflow": "string", "score": 0.0 }] }
```

**`POST /api/feedback`**
```json
{ "message_id": "string", "type": "up|down|comment", "comment": "string|null" }
```

**`GET /api/workflows`** — returns display names of all indexed workflows
**`GET /api/index/status`** — returns FAISS index health, chunk counts, and embedding model info

---

## 🧠 Design Principles

1. **Refuse rather than fabricate** — if retrieved evidence doesn't clear a confidence threshold, the system returns a fixed refusal rather than letting the LLM guess.
2. **Defense in depth** — safety-critical checks (internal-system leakage, unresolved context) are enforced deterministically in code, with prompt-level instructions serving only as a secondary layer.
3. **Retrieval quality over raw model power** — significant engineering effort went into hybrid retrieval and reranking, since a RAG system's answer quality is bounded by what it retrieves, not just what it generates.
4. **Provider independence** — the LLM backend is abstracted so the retrieval pipeline is unaffected by provider migrations (validated in practice via a live provider migration with zero pipeline changes).

---

## 🔭 Future Scope

- Fine-tuning the embedding/reranker models on domain-specific terminology
- Extending beyond read-only Q&A into a decision-support tool with human-in-the-loop next-step recommendations
- Multilingual support
- An internal dashboard surfacing trace data and feedback trends over time

---

## 👤 Author

**Tejaswi Khandelwal**

Built as part of an academic industry internship program.
