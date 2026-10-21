"""GEPA optimization of the extraction prompt.

Scope note: GEPA optimizes ONE thing here -- the instruction text of the
extractor. It cannot affect margins, spacing, fonts, or emphasis, because those
are not in the prompt. That is the point of the architecture: the optimizer is
pointed only at the part that is genuinely a language problem.

With four examples this is a smoke test of the harness, not an optimization.
A real run needs 20-50 labeled documents and a held-out set.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import dspy

from evals.fixtures import FIXTURES
from evals.metric import metric
from evals.run import configure
from legaldoc.extract import Extractor

OUT = Path(__file__).parent.parent / "build"


def examples() -> list[dspy.Example]:
    return [
        dspy.Example(source_text=f["source_text"], gold=f["gold"]).with_inputs(
            "source_text"
        )
        for f in FIXTURES
    ]


def main() -> int:
    configure()

    reflection_model = os.environ.get("LEGALDOC_REFLECTION_MODEL", "qwen3.8-max")
    reflection_lm = dspy.LM(
        f"openai/{reflection_model}",
        api_base="https://api.shisa.ai/v1",
        api_key=os.environ["SHISA_API_KEY"],
        max_tokens=16000,
        temperature=1.0,
    )

    exs = examples()
    # Leave-one-out is not meaningful at this size; optimize on all and report
    # that the score is in-sample.
    trainset, valset = exs, exs

    gepa = dspy.GEPA(
        metric=metric,
        # exactly one of auto / max_metric_calls / max_full_evals may be set
        reflection_lm=reflection_lm,
        max_metric_calls=int(os.environ.get("LEGALDOC_GEPA_CALLS", "40")),
        num_threads=4,
        track_stats=True,
        log_dir=str(OUT / "gepa"),
    )

    student = Extractor()
    print(f"optimizing with reflection model: {reflection_model}")
    optimized = gepa.compile(student, trainset=trainset, valset=valset)

    OUT.mkdir(parents=True, exist_ok=True)
    prompt = optimized.predict.signature.instructions
    (OUT / "optimized_prompt.txt").write_text(prompt)
    print(f"\noptimized prompt written to {OUT / 'optimized_prompt.txt'}")
    print("\n--- optimized instructions ---")
    print(prompt[:3000])

    # Re-score before and after.
    for label, program in (("baseline", Extractor()), ("optimized", optimized)):
        scores = []
        for fx in FIXTURES:
            pred = program(source_text=fx["source_text"])
            s, _ = __import__("evals.metric", fromlist=["score"]).score(
                fx["gold"], pred.document, pred.error
            )
            scores.append(s)
        mean = sum(scores) / len(scores)
        print(f"{label:10s} mean={mean:.3f}  per-example={[round(s,3) for s in scores]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
