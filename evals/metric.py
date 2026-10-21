"""The metric.

Design rule: every component is either exact or clearly defined. No LLM judge.
That matters because an LLM judge would let GEPA optimize against another
model's opinion, which is how prompt optimization produces prompts that game
the judge instead of producing correct documents.

Five components:

  valid          the JSON parses and satisfies the IR schema          (exact)
  grounded       every declared span appears in its own block's text  (exact)
  roles          block-role sequence similarity to gold               (defined)
  text           verbatim text fidelity to gold                       (defined)
  clean_render   renders, and the rendered .docx lints with 0 findings (exact)

`clean_render` is the one that ties the prompt to the lawyer's actual
complaint. A model that hallucinates a span, or emits double spaces, or
invents a blank paragraph, cannot score on it.
"""

from __future__ import annotations

import difflib
import re
import tempfile
from pathlib import Path

import dspy

from legaldoc.extract import ground_spans
from legaldoc.ir import Document
from legaldoc.lint import lint_docx
from legaldoc.render import UnmatchedMark, render
from legaldoc.spec import LITIGATION
from legaldoc.template import build_template

WEIGHTS = {
    "valid": 0.15,
    "grounded": 0.15,
    "roles": 0.15,
    "text": 0.15,
    "cases": 0.15,
    "clean_render": 0.25,
}

_TEMPLATE: Path | None = None


def _template() -> Path:
    global _TEMPLATE
    if _TEMPLATE is None or not _TEMPLATE.exists():
        _TEMPLATE = build_template(LITIGATION, Path(tempfile.mkdtemp()) / "tpl.docx")
    return _TEMPLATE


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


def _role_sequence(doc: Document) -> list[str]:
    out = []
    for b in doc.blocks:
        out.append(b.role if b.role != "heading" else f"heading{b.level}")
    return out


def _text_blocks(doc: Document) -> list[str]:
    out = []
    for b in doc.blocks:
        t = getattr(b, "text", None)
        if t:
            out.append(_norm(t))
    return out


def _text_fidelity(gold: Document, pred: Document) -> float:
    g, p = _text_blocks(gold), _text_blocks(pred)
    if not g:
        return 1.0
    if not p:
        return 0.0
    total = 0.0
    for gb in g:
        best = max(
            difflib.SequenceMatcher(None, gb, pb).ratio() for pb in p
        )
        total += best
    return total / len(g)


def _case_f1(gold: Document, pred: Document) -> float:
    def cases(d: Document) -> set[str]:
        out = set()
        for b in d.blocks:
            for c in getattr(b, "case_names", []) or []:
                out.add(_norm(c))
        return out

    g, p = cases(gold), cases(pred)
    if not g and not p:
        return 1.0
    if not g or not p:
        return 0.0
    tp = len(g & p)
    if tp == 0:
        return 0.0
    precision, recall = tp / len(p), tp / len(g)
    return 2 * precision * recall / (precision + recall)


def _clean_render(pred: Document) -> tuple[float, str]:
    try:
        out = render(pred, LITIGATION, _template(), Path(tempfile.mkdtemp()) / "p.docx")
    except UnmatchedMark as e:
        return 0.0, f"render failed: {e}"
    findings = lint_docx(out, LITIGATION)
    if not findings:
        return 1.0, ""
    # Collapse duplicates: the same code repeated 12 times is one lesson.
    by_code: dict[str, int] = {}
    for f in findings:
        by_code[f.code] = by_code.get(f.code, 0) + 1
    detail = ", ".join(f"{c} x{n}" for c, n in sorted(by_code.items()))
    sample = next(iter(findings))
    return 0.0, f"rendered document has format defects ({detail}); e.g. {sample}"


def score(gold: Document, pred: Document | None, error: str | None) -> tuple[float, str]:
    """Return (score in 0..1, feedback for the optimizer)."""
    if pred is None:
        return 0.0, (
            f"The output could not be used: {error}. "
            "Return one JSON object matching the schema exactly."
        )

    parts: dict[str, float] = {}
    notes: list[str] = []

    parts["valid"] = 1.0

    # grounded: every declared span must appear in its own block text
    spans = ground_spans(pred)
    if spans:
        ok = sum(1 for span, text in spans if span in text)
        parts["grounded"] = ok / len(spans)
        missing = [s for s, t in spans if s not in t][:3]
        if missing:
            notes.append(
                f"{len(missing)} declared span(s) do not appear in their block's "
                f"text, e.g. {missing}. Only quote spans that exist verbatim."
            )
    else:
        parts["grounded"] = 1.0

    parts["roles"] = difflib.SequenceMatcher(
        None, _role_sequence(gold), _role_sequence(pred)
    ).ratio()
    if parts["roles"] < 0.95:
        notes.append(
            f"block roles differ from expected: got {_role_sequence(pred)}, "
            f"expected {_role_sequence(gold)}."
        )

    parts["text"] = _text_fidelity(gold, pred)
    if parts["text"] < 0.95:
        notes.append(
            "block text is not verbatim; copy the source text exactly rather "
            "than paraphrasing or reflowing it."
        )

    parts["cases"] = _case_f1(gold, pred)
    if parts["cases"] < 1.0:
        notes.append(
            "cited case names do not match; put each cited case in the "
            "paragraph's case_names list, quoted verbatim."
        )

    parts["clean_render"], render_note = _clean_render(pred)
    if render_note:
        notes.append(render_note)

    total = sum(WEIGHTS[k] * v for k, v in parts.items())
    breakdown = " ".join(f"{k}={parts[k]:.2f}" for k in WEIGHTS)
    feedback = f"score={total:.3f} ({breakdown})."
    if notes:
        feedback += " " + " ".join(notes)
    return total, feedback


def metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
    """DSPy / GEPA metric.

    Returns a Prediction carrying score and feedback so GEPA can reflect on
    what specifically went wrong.
    """
    g = gold.gold
    p = getattr(pred, "document", None)
    err = getattr(pred, "error", None)
    s, fb = score(g, p, err)
    return dspy.Prediction(score=s, feedback=fb)
