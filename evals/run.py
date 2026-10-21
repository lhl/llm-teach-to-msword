"""Baseline: run the extractor over the fixtures and report per-component scores."""

from __future__ import annotations

import json
import os
import sys

import dspy

from evals.fixtures import FIXTURES
from evals.metric import WEIGHTS, score
from legaldoc.extract import Extractor

MODEL = os.environ.get("LEGALDOC_MODEL", "qwen38-flash-next-nvfp4")


def configure(model: str = MODEL) -> None:
    lm = dspy.LM(
        f"openai/{model}",
        api_base="https://api.shisa.ai/v1",
        api_key=os.environ["SHISA_API_KEY"],
        max_tokens=8000,
        temperature=0.0,
    )
    dspy.configure(lm=lm)


def main() -> int:
    configure()
    extractor = Extractor()
    total = 0.0
    rows = []
    for i, fx in enumerate(FIXTURES):
        pred = extractor(source_text=fx["source_text"])
        s, fb = score(fx["gold"], pred.document, pred.error)
        total += s
        rows.append({"fixture": i, "score": round(s, 3), "feedback": fb})
        print(f"fixture {i}: {s:.3f}")
        print(f"  {fb}")
        print()

    print(f"mean score: {total / len(FIXTURES):.3f}")
    print("weights:", json.dumps(WEIGHTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
