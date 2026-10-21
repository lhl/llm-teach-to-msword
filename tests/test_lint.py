"""Format evals. Deterministic: no LLM, no judge, no threshold. Pass or fail."""

from __future__ import annotations

from pathlib import Path

import pytest

from legaldoc.ir import Document, Heading, Paragraph
from legaldoc.lint import lint_docx
from legaldoc.render import render
from legaldoc.spec import LITIGATION
from legaldoc.template import build_template

CITE = "See Smith v. Jones, 123 Cal. App. 4th 456 (2020). The rule applies."

MINIMAL = Document(
    doc_type="memo",
    blocks=[
        Heading(level=1, text="MEMORANDUM"),
        Paragraph(text="The quick brown fox."),
        Paragraph(text="Second paragraph."),
        Paragraph(text=CITE, case_names=["Smith v. Jones"]),
        Paragraph(text=CITE, case_names=["Smith v. Jones"]),
    ],
)


@pytest.fixture(scope="module")
def template(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("tpl") / "template.docx"
    return build_template(LITIGATION, out)


@pytest.fixture(scope="module")
def clean(template, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("out") / "clean.docx"
    return render(MINIMAL, LITIGATION, template, out)


def codes(path: Path) -> set[str]:
    return {f.code for f in lint_docx(path, LITIGATION)}


def test_clean_render_has_no_findings(clean):
    findings = lint_docx(clean, LITIGATION)
    assert findings == [], "\n".join(str(f) for f in findings)


def test_render_is_deterministic(template, clean, tmp_path):
    again = render(MINIMAL, LITIGATION, template, tmp_path / "again.docx")
    # Paragraph-level XML must be byte-identical across renders.
    import zipfile

    def body(p):
        with zipfile.ZipFile(p) as z:
            return z.read("word/document.xml")

    assert body(clean) == body(again)


def test_margin_drift_detected(template, clean, tmp_path):
    from docx import Document as open_docx
    from docx.shared import Inches

    doc = open_docx(clean)
    doc.sections[0].top_margin = Inches(1.5)
    out = tmp_path / "bad_margin.docx"
    doc.save(out)

    findings = lint_docx(out, LITIGATION)
    assert any(f.code == "margins" and "top" in f.message for f in findings)


def test_direct_spacing_detected(template, clean, tmp_path):
    """The core bug: one paragraph carries its own spacing."""
    from docx import Document as open_docx

    doc = open_docx(clean)
    doc.paragraphs[1].paragraph_format.line_spacing = 1.15
    out = tmp_path / "bad_spacing.docx"
    doc.save(out)

    assert "direct-spacing" in codes(out)


def test_spacer_paragraph_detected(template, clean, tmp_path):
    from docx import Document as open_docx

    doc = open_docx(clean)
    doc.paragraphs[0].insert_paragraph_before("")
    out = tmp_path / "bad_spacer.docx"
    doc.save(out)

    assert "spacer-paragraph" in codes(out)


def test_unknown_style_detected(template, clean, tmp_path):
    from docx import Document as open_docx

    doc = open_docx(clean)
    doc.paragraphs[1].style = doc.styles["Normal"]
    out = tmp_path / "bad_style.docx"
    doc.save(out)

    assert "unknown-style" in codes(out)


def test_run_font_override_detected(template, clean, tmp_path):
    from docx import Document as open_docx
    from docx.shared import Pt

    doc = open_docx(clean)
    doc.paragraphs[1].runs[0].font.name = "Arial"
    doc.paragraphs[1].runs[0].font.size = Pt(10)
    out = tmp_path / "bad_run.docx"
    doc.save(out)

    assert "direct-run-format" in codes(out)


def test_missing_page_number_detected(template, clean, tmp_path):
    from docx import Document as open_docx

    doc = open_docx(clean)
    for p in doc.sections[0].footer.paragraphs:
        for r in list(p.runs):
            r._r.getparent().remove(r._r)
    out = tmp_path / "bad_footer.docx"
    doc.save(out)

    assert "footer-page-number" in codes(out)


def test_sentence_spacing_false_detected(template, clean, tmp_path):
    """Two spaces after an abbreviation, as a model produces it."""
    from docx import Document as open_docx

    doc = open_docx(clean)
    # Double-space after "Cal." -- not a sentence end.
    hit = False
    for r in doc.paragraphs[3].runs:
        if "Cal." in r.text:
            r.text = r.text.replace("Cal.", "Cal.  ")
            hit = True
    assert hit, "fixture no longer contains the abbreviation under test"
    out = tmp_path / "bad_spaces.docx"
    doc.save(out)

    assert "sentence-spacing-false" in codes(out)


def test_emphasis_inconsistent_detected(template, clean, tmp_path):
    """Same case name, italic in one paragraph, plain in another."""
    from docx import Document as open_docx

    doc = open_docx(clean)
    targets = [p for p in doc.paragraphs if "Smith v. Jones" in p.text]
    assert len(targets) >= 2
    for r in targets[0].runs:
        if r.text.strip() == "Smith v. Jones":
            r.italic = True
    for r in targets[1].runs:
        if r.text.strip() == "Smith v. Jones":
            r.italic = False
    out = tmp_path / "bad_emph.docx"
    doc.save(out)

    assert "emphasis-inconsistent" in codes(out)


def test_unmatched_mark_raises(template, tmp_path):
    from legaldoc.render import UnmatchedMark

    bad = Document(
        doc_type="memo",
        blocks=[Paragraph(text="Short text.", case_names=["Nonexistent v. Case"])],
    )
    with pytest.raises(UnmatchedMark):
        render(bad, LITIGATION, template, tmp_path / "x.docx")
