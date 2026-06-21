"""Repeatable retrieval evaluation for policy RAG changes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable, Iterable


DEFAULT_CASES = Path("data/evaluation/retrieval_cases.json")


def load_cases(path: Path = DEFAULT_CASES) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def evaluate_retrieval(
    cases: Iterable[dict],
    search: Callable,
    *,
    k: int = 5,
) -> dict:
    """Calculate source hit-rate@k and mean reciprocal rank."""
    details = []
    reciprocal_ranks = []
    for case in cases:
        results = search(case["query"], k=k)
        sources = [doc.metadata.get("source", "") for doc, _ in results]
        expected = set(case["relevant_sources"])
        first_rank = next((i for i, source in enumerate(sources, 1) if source in expected), None)
        reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)
        details.append({
            "query": case["query"],
            "expected": sorted(expected),
            "retrieved": sources,
            "first_relevant_rank": first_rank,
            "hit": first_rank is not None,
        })

    count = len(details)
    return {
        "cases": count,
        f"hit_rate@{k}": round(sum(item["hit"] for item in details) / count, 4) if count else 0.0,
        "mrr": round(sum(reciprocal_ranks) / count, 4) if count else 0.0,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate TrustNova policy retrieval")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    from src.rag.hybrid_retriever import hybrid_search

    report = evaluate_retrieval(load_cases(args.cases), hybrid_search, k=args.k)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
