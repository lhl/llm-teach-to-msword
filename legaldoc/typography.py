"""Typography passes that belong in code, not in a prompt.

Two things lawyers ask for that models get wrong every time:

1. **Two spaces after every sentence.** Asked to "put two spaces after every
   sentence", a model applies it after every *period*. Legal prose is dense
   with periods that do not end sentences: Inc., v., No., Id., cf., e.g.,
   U.S.C., Cal. App., subd., Hon., initials. The fix is a tokenizer, not a
   better prompt -- and then the output is exactly checkable.

2. **Consistent emphasis.** Whether a case name is italic or underlined is a
   house-style decision, not a per-paragraph judgment call. Fix it in the
   spec so it cannot vary.
"""

from __future__ import annotations

import re

# Tokens whose trailing period does not end a sentence. Lowercased.
# Legal citations are the bulk of this: getting them wrong is what produces
# "Inc.  filed" in the middle of a clause.
ABBREV: frozenset[str] = frozenset(
    """
    inc corp ltd co llc llp lp pllc pc
    v vs
    no nos
    id ib ibid
    cf eg ie etc viz
    mr mrs ms dr prof hon
    st ave blvd rd
    dept dist cir ct app supp fed reg
    sec art ch subd subds para paras p pp
    ed rev al
    civ proc pen bus gov lab elec com corp code
    jan feb mar apr jun jul aug sep sept oct nov dec
    approx est
    u.s u.s.c u.s.s.c cal cal.app cal.app.4th cal.app.5th
    f f.2d f.3d f.supp f.supp.2d f.supp.3d
    """.split()
)

_SENTENCE_END = re.compile(r"\.(\s+)")
_TOKEN_BEFORE = re.compile(r"([A-Za-z0-9.]+)\.$")


def _is_sentence_end(text: str, period_pos: int) -> bool:
    """Does the period at `period_pos` end a sentence?"""
    prefix = text[:period_pos]
    if not prefix:
        return False

    # A lowercase next word means the clause continues: "Inc. filed",
    # "briefs... and then". No sentence starts lowercase in legal prose.
    after = text[period_pos + 1 :].lstrip(" \t\n")
    if after[:1].islower():
        return False

    # Ellipsis.
    if prefix.endswith(".."):
        return True

    m = _TOKEN_BEFORE.search(prefix + ".")
    if m:
        token = m.group(1)
        low = token.lower().strip(".")
        if low in ABBREV:
            return False
        # Acronym: U.S., i.e., e.g., P.C.
        if re.fullmatch(r"(?:[A-Za-z]\.){1,5}", token + "."):
            return False
        # Single initial, as in "J.Q. Attorney" or "R. Example".
        if re.fullmatch(r"[A-Z]", token):
            return False
        return True

    # Period after a closing paren or quote ends a sentence: "(2020)."
    if prefix[-1] in ")]\"'\u201d\u2019":
        return True
    return True


def sentence_boundaries(text: str) -> list[int]:
    """Indices of periods that terminate sentences."""
    return [
        m.start()
        for m in _SENTENCE_END.finditer(text)
        if _is_sentence_end(text, m.start())
    ]


def apply_sentence_spacing(text: str, spaces: int = 2) -> str:
    """Normalize inter-sentence spacing. Idempotent.

    Non-sentence periods keep whatever spacing they had, normalized to one
    space, so "Inc.  filed" collapses back to "Inc. filed".
    """
    out: list[str] = []
    last = 0
    for m in _SENTENCE_END.finditer(text):
        pos = m.start()
        is_end = _is_sentence_end(text, pos)
        want = " " * (spaces if is_end else 1)
        out.append(text[last:pos])
        out.append("." + want)
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def single_spaced_sentence_ends(text: str) -> list[tuple[int, str]]:
    """Sentence ends followed by exactly one space.

    This is the exact check for the reported bug: every hit is a real
    sentence boundary that did not get its second space, with no false
    positives from abbreviations or citations.
    """
    hits = []
    for m in _SENTENCE_END.finditer(text):
        if m.group(1) == " " and _is_sentence_end(text, m.start()):
            snippet = text[max(0, m.start() - 25) : m.end() + 20]
            hits.append((m.start(), snippet))
    return hits


_DOUBLE = re.compile(r"\.(\s{2,})")


def double_spaced_non_sentence_ends(text: str) -> list[tuple[int, str]]:
    """Periods followed by two or more spaces that do NOT end a sentence.

    This is the other half of the same bug: "Inc.  filed", "v.  Jones",
    "Cal.  App."  A model told to double-space after sentences typically
    double-spaces after every period instead.
    """
    hits = []
    for m in _DOUBLE.finditer(text):
        if not _is_sentence_end(text, m.start()):
            snippet = text[max(0, m.start() - 25) : m.end() + 15]
            hits.append((m.start(), snippet))
    return hits
