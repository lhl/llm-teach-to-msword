"""The one place a language model is used: messy text -> semantic IR.

Everything downstream of this is deterministic. That is deliberate: it bounds
what a prompt-optimizer like GEPA can be responsible for. If a document comes
out with wrong margins, no amount of prompt tuning would have fixed it, so the
optimizer should not be pointed at it.
"""

from __future__ import annotations

import json
import re
from typing import Any

import dspy
from pydantic import ValidationError

from .ir import Document

SCHEMA_HINT = """\
Output a single JSON object with exactly two keys: "doc_type" and "blocks".

"doc_type" is a short lowercase string: motion, opposition, reply, declaration,
letter, memo, contract, order, or notice.

"blocks" is a list. Every block has a "role" key. Allowed roles and their fields:

  {"role": "heading", "level": 1 or 2, "text": str}
  {"role": "paragraph", "text": str,
   "emphasis": [str], "italic": [str], "case_names": [str], "defined_terms": [str]}
  {"role": "block_quote", "text": str, "attribution": str or null}
  {"role": "caption", "court": str, "parties": [str], "title": str,
   "document_title": str, "case_number": str}
  {"role": "signature", "name": str, "bar_number": str or null, "firm": str or null,
   "address": [str], "phone": str or null, "email": str or null,
   "represented_party": str or null}
  {"role": "certificate", "text": str}

Rules that matter:

- Copy text verbatim from the source. Do not rewrite, summarize, or fix grammar.
- Use ONE space between sentences in "text". Sentence spacing is applied by the
  renderer. Never emit double spaces.
- Every string in "emphasis", "italic", "case_names", and "defined_terms" must
  appear verbatim inside that block's own "text". Never invent a span.
- "case_names" holds cited case names only, e.g. "Smith v. Jones". Case names
  are italicized by the renderer according to house style; do not decide.
- "emphasis" is for spans the document itself marks as emphasized, such as
  "PLEASE TAKE NOTICE" in a California notice of motion.
- Never emit formatting instructions, margin values, font names, or blank
  paragraphs. Layout is not yours to control.
"""


class ExtractIR(dspy.Signature):
    __doc__ = (
        "Convert a legal document into a semantic block list.\n\n"
        "You are a document analyst, not a typesetter. Your output describes "
        "what each part of the document *is*. How it looks is decided "
        "elsewhere.\n\n" + SCHEMA_HINT
    )

    source_text: str = dspy.InputField(desc="raw text of the document")
    document_json: str = dspy.OutputField(
        desc="a single JSON object with keys doc_type and blocks"
    )


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    if m:
        return m.group(1).strip()
    # Some models prepend prose before the object.
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return raw[start : end + 1]
    return raw


def parse_ir(raw: str) -> tuple[Document | None, str | None]:
    """Parse and validate. Returns (document, error_message)."""
    text = _strip_fences(raw)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: {e}"
    if not isinstance(obj, dict):
        return None, "top-level JSON value is not an object"
    try:
        return Document.model_validate(obj), None
    except ValidationError as e:
        # Compact: first three problems, not the whole dump.
        problems = "; ".join(
            f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
            for err in e.errors()[:3]
        )
        return None, f"schema violation: {problems}"


class Extractor(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.predict = dspy.Predict(ExtractIR)

    def forward(self, source_text: str) -> dspy.Prediction:
        raw = self.predict(source_text=source_text).document_json
        doc, err = parse_ir(raw)
        return dspy.Prediction(document=doc, raw=raw, error=err)


def declared_spans(doc: Document) -> list[str]:
    """Every span the model claims exists in the text."""
    out: list[str] = []
    for b in doc.blocks:
        for attr in ("emphasis", "italic", "case_names", "defined_terms"):
            out.extend(getattr(b, attr, []) or [])
    return out


def ground_spans(doc: Document) -> list[tuple[str, str]]:
    """(span, block_text) pairs, for checking each span against its own block."""
    out: list[tuple[str, str]] = []
    for b in doc.blocks:
        text = getattr(b, "text", "") or ""
        for attr in ("emphasis", "italic", "case_names", "defined_terms"):
            for span in getattr(b, attr, []) or []:
                out.append((span, text))
    return out


def to_dict(doc: Document) -> dict[str, Any]:
    return doc.model_dump(mode="json")
