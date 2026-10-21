"""Demo: render a clean motion, then reproduce the reported bugs and catch them."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document as open_docx
from docx.shared import Inches, Pt

from legaldoc.ir import (
    BlockQuote,
    Caption,
    CertificateOfService,
    Document,
    Heading,
    Paragraph,
    SignatureBlock,
)
from legaldoc.lint import lint_docx
from legaldoc.render import render
from legaldoc.spec import LITIGATION
from legaldoc.template import build_template
from legaldoc.typography import apply_sentence_spacing

OUT = Path(__file__).parent / "build"

CITATION = (
    "Plaintiff relies on Smith v. Jones, 123 Cal. App. 4th 456, 460 (2020), "
    "which held that boilerplate objections waive the privilege. See also "
    "Acme Corp. v. Doe, 55 F. Supp. 3d 12 (N.D. Cal. 2021)."
)

CITATION2 = (
    "The same rule controls here. Smith v. Jones, 123 Cal. App. 4th at 461, "
    "requires production where the objection is unsupported by any facts."
)

DOC = Document(
    doc_type="motion",
    blocks=[
        Caption(
            court="SUPERIOR COURT OF THE STATE OF CALIFORNIA\nCOUNTY OF ALAMEDA",
            parties=[
                "ACME WIDGETS, INC., a Delaware corporation,",
                "Plaintiff,",
                "v.",
                "JOHN DOE, an individual,",
                "Defendant.",
            ],
            title="Case No. 00-CV-000000",
            document_title="PLAINTIFF'S NOTICE OF MOTION AND MOTION TO COMPEL",
            case_number="Dept. 12",
        ),
        Heading(level=1, text="NOTICE OF MOTION"),
        Paragraph(
            text=(
                "TO ALL PARTIES AND THEIR COUNSEL OF RECORD: PLEASE TAKE NOTICE that "
                "on March 4, 2025, at 9:00 a.m., or as soon thereafter as the matter "
                "may be heard, in Department 12 of the above-entitled Court, Plaintiff "
                "Acme Widgets, Inc. will and hereby does move this Court for an order "
                "compelling Defendant John Doe to produce documents responsive to "
                "Requests Nos. 4 through 19."
            ),
            emphasis=["PLEASE TAKE NOTICE"],
        ),
        Heading(level=2, text="I. FACTUAL BACKGROUND"),
        Paragraph(
            text=(
                "On June 1, 2024, Acme served its First Set of Requests for Production. "
                "Defendant's responses, served thirty-one days later, consisted almost "
                "entirely of boilerplate objections."
            )
        ),
        Heading(level=2, text="II. LEGAL STANDARD"),
        Paragraph(text=CITATION, case_names=["Smith v. Jones", "Acme Corp. v. Doe"]),
        Paragraph(text=CITATION2, case_names=["Smith v. Jones"]),
        Paragraph(
            text=(
                "A party may move for an order compelling production where a responding "
                "party fails to produce documents. (Code Civ. Proc., § 2031.320, subd. (a).)"
            )
        ),
        BlockQuote(
            text=(
                "Responding Party objects to this Request on the grounds that it seeks "
                "documents protected by the attorney-client privilege and the work "
                "product doctrine."
            ),
            attribution="— Defendant's Response to Request No. 7",
        ),
        SignatureBlock(
            name="JANE Q. ATTORNEY",
            bar_number="SBN 000000",
            firm="Example Law Group LLP",
            address=["100 Example Plaza, Suite 100", "Anytown, CA 00000"],
            phone="(555) 555-0100",
            email="jane@example.com",
            represented_party="Acme Widgets, Inc.",
        ),
        CertificateOfService(
            text=(
                "I am employed in the County of Alameda, State of California. I am over "
                "the age of eighteen and not a party to the within action. On March 1, "
                "2025, I served the foregoing document by electronic mail on all counsel "
                "of record."
            )
        ),
    ],
)


def naive_two_spaces(text: str) -> str:
    """What a model does when told 'two spaces after every sentence'."""
    return re.sub(r"\. ", ".  ", text)


def mangle(path: Path) -> Path:
    """Reproduce the reported failures. Each is an observed mode, not a strawman."""
    doc = open_docx(path)
    sec = doc.sections[0]

    # 1. Margin drift.
    sec.left_margin = Inches(1.25)

    body = [p for p in doc.paragraphs if p.style.name == "Body Text"]

    # 2. Direct spacing override on one paragraph.
    body[1].paragraph_format.line_spacing = 1.5

    # 3. Blank paragraphs as vertical space.
    for _ in range(2):
        body[1].insert_paragraph_before("").style = doc.styles["Normal"]

    # 4. Font substitution on one run.
    run = body[0].runs[0]
    run.font.name = "Calibri"
    run.font.size = Pt(11)

    # 6. Emphasis applied to a case name in one paragraph but not the other.
    #    Briefs cite the same case repeatedly; this is where inconsistency
    #    becomes visible.
    seen = 0
    for p in body:
        for r in p.runs:
            if r.text.strip() == "Smith v. Jones":
                seen += 1
                if seen == 2:
                    r.italic = False

    # 5. Sentence spacing applied to every period, including abbreviations.
    for p in body:
        for r in p.runs:
            if r.text:
                r.text = naive_two_spaces(r.text)


    # 7. Footer field lost.
    for p in sec.footer.paragraphs:
        for r in list(p.runs):
            r._r.getparent().remove(r._r)

    out = path.with_name(path.stem + "-mangled.docx")
    doc.save(out)
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    template = build_template(LITIGATION, OUT / "template.docx")
    good = render(DOC, LITIGATION, template, OUT / "motion.docx")
    bad = mangle(good)

    print("SENTENCE SPACING")
    print("-" * 70)
    print("naive (every period):", naive_two_spaces(CITATION)[:110], "...")
    print("correct (tokenizer) :", apply_sentence_spacing(CITATION)[:110], "...")

    failed = False
    for label, path in (("CLEAN (rendered from IR)", good), ("MANGLED (LLM edited)", bad)):
        findings = lint_docx(path, LITIGATION)
        print(f"\n{label}: {path.name}")
        print("-" * 70)
        if not findings:
            print("  no findings")
        for f in findings:
            print(f"  {f}")
        if label.startswith("CLEAN") and findings:
            failed = True

    print()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
