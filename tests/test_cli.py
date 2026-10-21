"""CLI contract tests: exit codes matter because this runs in CI."""

from __future__ import annotations

from pathlib import Path

import pytest

from legaldoc.cli import main
from legaldoc.ir import Document, Heading, Paragraph
from legaldoc.render import render
from legaldoc.spec import LITIGATION
from legaldoc.template import build_template


@pytest.fixture(scope="module")
def clean_docx(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("cli")
    tpl = build_template(LITIGATION, d / "tpl.docx")
    doc = Document(
        doc_type="memo",
        blocks=[Heading(level=1, text="MEMORANDUM"), Paragraph(text="Body text.")],
    )
    return render(doc, LITIGATION, tpl, d / "clean.docx")


def test_spec_command(capsys):
    assert main(["spec"]) == 0
    out = capsys.readouterr().out
    assert "litigation-us-letter" in out
    assert "Times New Roman" in out


def test_lint_clean_exits_zero(clean_docx, capsys):
    assert main(["lint", str(clean_docx)]) == 0
    assert "clean" in capsys.readouterr().out


def test_lint_defect_exits_one(clean_docx, tmp_path, capsys):
    from docx import Document as open_docx
    from docx.shared import Inches

    doc = open_docx(clean_docx)
    doc.sections[0].top_margin = Inches(2.0)
    bad = tmp_path / "bad.docx"
    doc.save(bad)

    assert main(["lint", str(bad)]) == 1
    assert "margins" in capsys.readouterr().out


def test_lint_missing_file_exits_one(capsys):
    assert main(["lint", "does-not-exist.docx"]) == 1


def test_render_roundtrip(clean_docx, tmp_path, capsys):
    ir = tmp_path / "ir.json"
    ir.write_text(
        Document(
            doc_type="memo",
            blocks=[Heading(level=1, text="MEMORANDUM"), Paragraph(text="Hello.")],
        ).model_dump_json()
    )
    out = tmp_path / "out.docx"
    assert main(["render", str(ir), "-o", str(out)]) == 0
    assert out.exists()
    assert "wrote" in capsys.readouterr().out


def test_render_invalid_ir_exits_one(tmp_path, capsys):
    ir = tmp_path / "bad.json"
    ir.write_text('{"doc_type": "memo", "blocks": [{"role": "nope"}]}')
    assert main(["render", str(ir), "-o", str(tmp_path / "x.docx")]) == 1
