"""Labeled examples. Small on purpose: the point is the harness, not the corpus.

Replace these with 20-50 real documents from the practice. The labels are the
expensive part; the metric is cheap once the labels exist.
"""

from __future__ import annotations

from legaldoc.ir import (
    BlockQuote,
    Document,
    Heading,
    Paragraph,
    SignatureBlock,
)

MOTION_SOURCE = """\
PLAINTIFF'S NOTICE OF MOTION AND MOTION TO COMPEL

PLEASE TAKE NOTICE that on March 4, 2025, at 9:00 a.m., Plaintiff Acme Widgets,
Inc. will move this Court for an order compelling Defendant to produce documents
responsive to Requests Nos. 4 through 19.

Plaintiff relies on Smith v. Jones, 123 Cal. App. 4th 456, 460 (2020), which held
that boilerplate objections waive the privilege. See also Acme Corp. v. Doe, 55 F.
Supp. 3d 12 (N.D. Cal. 2021).
"""

MOTION_GOLD = Document(
    doc_type="motion",
    blocks=[
        Heading(level=1, text="PLAINTIFF'S NOTICE OF MOTION AND MOTION TO COMPEL"),
        Paragraph(
            text=(
                "PLEASE TAKE NOTICE that on March 4, 2025, at 9:00 a.m., Plaintiff Acme "
                "Widgets, Inc. will move this Court for an order compelling Defendant to "
                "produce documents responsive to Requests Nos. 4 through 19."
            ),
            emphasis=["PLEASE TAKE NOTICE"],
        ),
        Paragraph(
            text=(
                "Plaintiff relies on Smith v. Jones, 123 Cal. App. 4th 456, 460 (2020), "
                "which held that boilerplate objections waive the privilege. See also "
                "Acme Corp. v. Doe, 55 F. Supp. 3d 12 (N.D. Cal. 2021)."
            ),
            case_names=["Smith v. Jones", "Acme Corp. v. Doe"],
        ),
    ],
)

LETTER_SOURCE = """\
March 1, 2025

Re: Acme Widgets, Inc. v. Doe - Discovery Dispute

Dear Ms. Attorney:

I write regarding Defendant's responses to Plaintiff's First Set of Requests for
Production. The responses consist entirely of boilerplate objections. Under Code
Civ. Proc., section 2031.240, a responding party must state the specific ground
for each objection. Defendant has not done so.

Please provide supplemental responses by March 15, 2025. If I do not receive them
by that date, Plaintiff will move to compel.

Very truly yours,

JANE Q. ATTORNEY
"""

LETTER_GOLD = Document(
    doc_type="letter",
    blocks=[
        Paragraph(text="March 1, 2025"),
        Paragraph(text="Re: Acme Widgets, Inc. v. Doe - Discovery Dispute"),
        Paragraph(text="Dear Ms. Attorney:"),
        Paragraph(
            text=(
                "I write regarding Defendant's responses to Plaintiff's First Set of "
                "Requests for Production. The responses consist entirely of boilerplate "
                "objections. Under Code Civ. Proc., section 2031.240, a responding party "
                "must state the specific ground for each objection. Defendant has not "
                "done so."
            )
        ),
        Paragraph(
            text=(
                "Please provide supplemental responses by March 15, 2025. If I do not "
                "receive them by that date, Plaintiff will move to compel."
            )
        ),
        Paragraph(text="Very truly yours,"),
        SignatureBlock(name="JANE Q. ATTORNEY"),
    ],
)

MEMO_SOURCE = """\
MEMORANDUM

I. QUESTION PRESENTED

Whether a responding party waives privilege by asserting boilerplate objections
without a privilege log.

II. SHORT ANSWER

Yes. A party that objects on privilege grounds must provide a privilege log
contemporaneously with its response.

III. ANALYSIS

The court in Smith v. Jones addressed this exact issue. It held:

A responding party that asserts privilege must produce a privilege log at the
time it serves its response. A later log does not cure the waiver.

Smith v. Jones, 123 Cal. App. 4th 456, 462 (2020). The reasoning applies with
equal force here.
"""

MEMO_GOLD = Document(
    doc_type="memo",
    blocks=[
        Heading(level=1, text="MEMORANDUM"),
        Heading(level=2, text="I. QUESTION PRESENTED"),
        Paragraph(
            text=(
                "Whether a responding party waives privilege by asserting boilerplate "
                "objections without a privilege log."
            )
        ),
        Heading(level=2, text="II. SHORT ANSWER"),
        Paragraph(
            text=(
                "Yes. A party that objects on privilege grounds must provide a privilege "
                "log contemporaneously with its response."
            )
        ),
        Heading(level=2, text="III. ANALYSIS"),
        Paragraph(
            text="The court in Smith v. Jones addressed this exact issue. It held:",
            case_names=["Smith v. Jones"],
        ),
        BlockQuote(
            text=(
                "A responding party that asserts privilege must produce a privilege log "
                "at the time it serves its response. A later log does not cure the waiver."
            )
        ),
        Paragraph(
            text=(
                "Smith v. Jones, 123 Cal. App. 4th 456, 462 (2020). The reasoning applies "
                "with equal force here."
            ),
            case_names=["Smith v. Jones"],
        ),
    ],
)

FIXTURES = [
    {"source_text": MOTION_SOURCE, "gold": MOTION_GOLD},
    {"source_text": LETTER_SOURCE, "gold": LETTER_GOLD},
    {"source_text": MEMO_SOURCE, "gold": MEMO_GOLD},
]

# A realistic input: text extracted from a filed PDF. Line numbers, page
# headers, and page-break artifacts are interleaved with the content. This is
# what a lawyer's actual source material looks like, and stripping it is a
# genuine language task rather than a formatting one.
MESSY_SOURCE = """\
PLAINTIFF'S MOTION TO COMPEL - 1

1  SUPERIOR COURT OF THE STATE OF CALIFORNIA
2  COUNTY OF ALAMEDA
3
4  ACME WIDGETS, INC., a Delaware corporation,
5            Plaintiff,
6
7  v.
8
9  JOHN DOE, an individual,
10           Defendant.
11
12  Case No. 00-CV-000000
13
14  PLAINTIFF'S MOTION TO COMPEL
15
16  PLEASE TAKE NOTICE that Plaintiff will move this Court for an
17  order compelling Defendant to produce documents.
18
19  Plaintiff relies on Smith v. Jones, 123 Cal. App. 4th 456
20  (2020), which held that boilerplate objections waive the
21  privilege.
22

PLAINTIFF'S MOTION TO COMPEL - 2

23  Respectfully submitted,
24
25  JANE Q. ATTORNEY
"""

MESSY_GOLD = Document(
    doc_type="motion",
    blocks=[
        Heading(level=1, text="PLAINTIFF'S MOTION TO COMPEL"),
        Paragraph(
            text=(
                "PLEASE TAKE NOTICE that Plaintiff will move this Court for an order "
                "compelling Defendant to produce documents."
            ),
            emphasis=["PLEASE TAKE NOTICE"],
        ),
        Paragraph(
            text=(
                "Plaintiff relies on Smith v. Jones, 123 Cal. App. 4th 456 (2020), "
                "which held that boilerplate objections waive the privilege."
            ),
            case_names=["Smith v. Jones"],
        ),
        SignatureBlock(name="JANE Q. ATTORNEY"),
    ],
)

FIXTURES.append({"source_text": MESSY_SOURCE, "gold": MESSY_GOLD})
