"""
Standalone RAGAS evaluation script for the Telecom Workflow Navigator.

DELIBERATELY SEPARATE from the main inference flow. main.py and rag.py never
import this file, and it is never invoked automatically as part of serving
a real user request — it is a one-way import (this script imports FROM
rag.py/utils.py) that you run manually, on demand:

    python evaluate_ragas.py
    python evaluate_ragas.py --dataset qna_eval_dataset.json --output eval_results.csv

WHY the real rag_answer() pipeline is used for evaluation (not a shortcut):
Each question in the eval dataset is run through the actual production
pipeline — same retrieval, same guardrails, same thresholds users
experience — so the evaluation numbers reflect real behavior, not an
idealized shortcut. Each question gets its own disposable session_id so
evaluation runs never pollute, or are polluted by, real conversation memory.

Requires (not part of the main app's dependencies — install separately):
    pip install ragas datasets

"""

import argparse
import csv
import json
import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# Compatibility shim: ragas 0.4.3's llms/base.py unconditionally imports
# ChatVertexAI from langchain_community.chat_models.vertexai — a submodule
# that no longer exists in newer langchain_community versions (Vertex AI
# support moved to a separate langchain-google-vertexai package). We never
# use Vertex AI anywhere in this project; this stub exists ONLY to satisfy
# that import statement so ragas can load at all. It is never instantiated.
# Deliberately NOT fixed by pinning langchain_community to an older version,
# since that package is also used by the main app's FAISS/retrieval code —
# downgrading it risks breaking things unrelated to this evaluation script.
if "langchain_community.chat_models.vertexai" not in sys.modules:
    _vertexai_stub_module = types.ModuleType("langchain_community.chat_models.vertexai")

    class ChatVertexAI:  # pragma: no cover — compatibility stub, never actually used
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "ChatVertexAI is a compatibility stub only — Vertex AI is not "
                "supported or used anywhere in this project."
            )

    _vertexai_stub_module.ChatVertexAI = ChatVertexAI
    sys.modules["langchain_community.chat_models.vertexai"] = _vertexai_stub_module

from guardrails import INTERNAL_LEAKAGE_REFUSAL, LOW_CONFIDENCE_REFUSAL, NO_HISTORY_REFUSAL
from rag import rag_answer, build_llm
from utils import build_embeddings

REFUSAL_MESSAGES = {INTERNAL_LEAKAGE_REFUSAL, LOW_CONFIDENCE_REFUSAL, NO_HISTORY_REFUSAL}


def load_eval_dataset(path: Path) -> list[dict]:
    if not path.exists():
        print(f"Eval dataset not found: {path}", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def run_inference_on_dataset(items: list[dict]) -> list[dict]:
    """
    Runs every eval question through the real rag_answer() pipeline and
    collects what RAGAS needs: the question, the generated answer, the
    contexts actually retrieved and used, and the ground-truth reference.
    """
    results = []
    for i, item in enumerate(items):
        eval_session_id = f"ragas-eval-{item.get('id', i)}"  # disposable, isolated per question
        outcome = rag_answer(item["question"], session_id=eval_session_id)

        answer = outcome["answer"]
        results.append({
            "id": item.get("id", f"qa_{i}"),
            "question": item["question"],
            "ground_truth": item["ground_truth"],
            "answer": answer,
            "retrieved_contexts": outcome.get("contexts", []),
            "refused": answer in REFUSAL_MESSAGES,
        })
        status = "REFUSED" if answer in REFUSAL_MESSAGES else "answered"
        print(f"[{i + 1}/{len(items)}] ({status}) {item['question'][:70]}")

    return results


def run_ragas_evaluation(results: list[dict]):
    """
    Scores the answerable (non-refused) subset with RAGAS's four core
    metrics. Refused answers are reported separately as a refusal rate,
    since faithfulness/relevancy metrics have no meaningful interpretation
    against a fixed refusal string — and because every question in this
    eval set is grounded in real docs, ANY refusal here is itself a
    finding worth surfacing directly (a false refusal = thresholds too
    strict / recall gap), not something to silently average away.

    NOTE ON RAGAS VERSION: this targets the modern RAGAS API (0.2+), which
    renamed dataset columns from question/answer/contexts/ground_truth to
    user_input/response/retrieved_contexts/reference. A fresh
    `pip install ragas` today installs this version. If you have an older
    ragas pinned, this will need the old column names instead — check with
    `pip show ragas`.
    """
    from ragas import evaluate, EvaluationDataset
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper

    scoreable = [r for r in results if not r["refused"]]
    refused = [r for r in results if r["refused"]]

    print(f"\n{len(refused)}/{len(results)} questions were refused by the system "
          f"(excluded from RAGAS scoring, reported separately below).")

    if not scoreable:
        print("No answerable questions to score — every question was refused. "
              "This likely means thresholds are set too strictly for this dataset.")
        return None, refused

    eval_rows = [
        {
            "user_input": r["question"],
            "response": r["answer"],
            # RAGAS expects a non-empty list of context strings per row
            "retrieved_contexts": r["retrieved_contexts"] or [""],
            "reference": r["ground_truth"],
        }
        for r in scoreable
    ]
    dataset = EvaluationDataset.from_list(eval_rows)

    # Reuse the SAME LLM/embeddings already configured for the app (Azure/Groq,
    # BAAI/bge-large-en-v1.5) rather than requiring a separate evaluation-only
    # API key — keeps eval consistent with what's actually running in production.
    ragas_llm = LangchainLLMWrapper(build_llm())
    ragas_embeddings = LangchainEmbeddingsWrapper(build_embeddings())

    metrics = [faithfulness, answer_relevancy, context_precision, context_recall]

    score = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=ragas_llm,
        embeddings=ragas_embeddings,
    )
    return score, refused


def save_results_csv(results: list[dict], ragas_scores, output_path: Path) -> None:
    # Match scores back to results by POSITION, not by re-finding the
    # question text — this is robust regardless of what RAGAS names its
    # columns (which changed once already between versions), and avoids a
    # subtle bug if two questions in the eval set were ever identical text.
    scoreable_ids = [r["id"] for r in results if not r["refused"]]
    scores_by_id: dict[str, dict] = {}
    if ragas_scores is not None:
        try:
            df = ragas_scores.to_pandas()
            for eval_id, (_, row) in zip(scoreable_ids, df.iterrows()):
                scores_by_id[eval_id] = row.to_dict()
        except Exception:
            pass  # fall back to just writing inference-level results

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "question", "ground_truth", "answer", "refused",
            "retrieved_context_count", "faithfulness", "answer_relevancy",
            "context_precision", "context_recall",
        ])
        for r in results:
            row_scores = scores_by_id.get(r["id"], {})
            writer.writerow([
                r["id"], r["question"], r["ground_truth"], r["answer"], r["refused"],
                len(r["retrieved_contexts"]),
                row_scores.get("faithfulness", ""),
                row_scores.get("answer_relevancy", ""),
                row_scores.get("context_precision", ""),
                row_scores.get("context_recall", ""),
            ])
    print(f"\nPer-question results saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="RAGAS evaluation for the Telecom Workflow Navigator")
    parser.add_argument("--dataset", default="qna_eval_dataset.json", help="Path to the eval dataset JSON")
    parser.add_argument("--output", default="eval_results.csv", help="Path to write per-question CSV results")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    output_path = Path(args.output)

    items = load_eval_dataset(dataset_path)
    print(f"Loaded {len(items)} evaluation questions from {dataset_path}\n")

    print("Running each question through the real rag_answer() pipeline...")
    results = run_inference_on_dataset(items)

    print("\nRunning RAGAS evaluation on the answerable subset...")
    ragas_scores, refused = run_ragas_evaluation(results)

    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Total questions:     {len(items)}")
    print(f"Answered:            {len(items) - len(refused)}")
    print(f"Refused:             {len(refused)}")
    if refused:
        print("\nRefused questions (review these — every item in this dataset")
        print("is grounded in real docs, so a refusal here may indicate")
        print("thresholds are too strict, not that the question is unanswerable):")
        for r in refused:
            print(f"  - [{r['id']}] {r['question']}")

    if ragas_scores is not None:
        print("\nRAGAS scores (averaged over answerable questions):")
        print(ragas_scores)

    save_results_csv(results, ragas_scores, output_path)


if __name__ == "__main__":
    main()