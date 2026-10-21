"""Typography evals. Exact assertions, no model, no tolerance."""

from __future__ import annotations

import pytest

from legaldoc.typography import (
    apply_sentence_spacing,
    double_spaced_non_sentence_ends,
    single_spaced_sentence_ends,
)

# (input, expected) after two-space normalization. The first column is real
# legal prose, chosen for the periods that do not end sentences.
CASES = [
    (
        "Acme Widgets, Inc. filed suit. Defendant responded.",
        "Acme Widgets, Inc. filed suit.  Defendant responded.",
    ),
    (
        "See Smith v. Jones, 123 Cal. App. 4th 456, 460 (2020). The court held otherwise.",
        "See Smith v. Jones, 123 Cal. App. 4th 456, 460 (2020).  The court held otherwise.",
    ),
    (
        "Code Civ. Proc., § 2031.320, subd. (a). Plaintiff argues the motion is timely.",
        "Code Civ. Proc., § 2031.320, subd. (a).  Plaintiff argues the motion is timely.",
    ),
    (
        "Id. at 461. See also U.S.C. § 1983.",
        "Id. at 461.  See also U.S.C. § 1983.",
    ),
    (
        "On March 4, 2025, at 9:00 a.m., the matter was heard. Hon. R. Example presided.",
        "On March 4, 2025, at 9:00 a.m., the matter was heard.  Hon. R. Example presided.",
    ),
    (
        "J.Q. Attorney, SBN 000000, appeared. The clerk called the matter.",
        "J.Q. Attorney, SBN 000000, appeared.  The clerk called the matter.",
    ),
    (
        "Plaintiff cites e.g. Jones, supra. Defendant disagrees.",
        "Plaintiff cites e.g. Jones, supra.  Defendant disagrees.",
    ),
    (
        "The parties filed briefs... and then settled. The end.",
        "The parties filed briefs... and then settled.  The end.",
    ),
    (
        "Acme Corp. v. Doe, 55 F. Supp. 3d 12 (N.D. Cal. 2021). That is the rule.",
        "Acme Corp. v. Doe, 55 F. Supp. 3d 12 (N.D. Cal. 2021).  That is the rule.",
    ),
]


@pytest.mark.parametrize("raw,expected", CASES)
def test_sentence_spacing(raw, expected):
    assert apply_sentence_spacing(raw) == expected


@pytest.mark.parametrize("raw,_expected", CASES)
def test_idempotent(raw, _expected):
    once = apply_sentence_spacing(raw)
    assert apply_sentence_spacing(once) == once


@pytest.mark.parametrize("raw,_expected", CASES)
def test_correct_output_has_no_findings(raw, _expected):
    out = apply_sentence_spacing(raw)
    assert single_spaced_sentence_ends(out) == []
    assert double_spaced_non_sentence_ends(out) == []


@pytest.mark.parametrize("raw,_expected", CASES)
def test_naive_regex_is_detected(raw, _expected):
    """The reported bug: double space after every period."""
    naive = raw.replace(". ", ".  ")
    assert double_spaced_non_sentence_ends(naive), (
        f"naive doubling of {raw!r} should be detected"
    )


def test_single_space_after_sentence_detected():
    hits = single_spaced_sentence_ends("The motion is granted. Costs to follow.")
    assert len(hits) == 1


def test_abbreviation_not_flagged_as_missing_space():
    assert single_spaced_sentence_ends("Acme Widgets, Inc. filed suit.") == []
