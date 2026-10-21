"""The formatting specification, as data.

This is the single source of truth. It is not a prompt. Court rules and firm
house style are written down once here, and both the renderer and the linter
read from it. When a judge's standing order changes, you edit this file, not a
system message.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 1440 DXA (twentieths of a point) = 1 inch
INCH = 1440


@dataclass(frozen=True)
class StyleSpec:
    """What a named paragraph style must resolve to."""

    name: str
    # Effective paragraph properties, after style inheritance.
    spacing_line: int | None = None  # in 240ths; 480 == double spaced
    space_before: int = 0  # DXA
    space_after: int = 0  # DXA
    first_line_indent: int = 0  # DXA
    left_indent: int = 0  # DXA
    alignment: str = "left"
    # Effective run properties.
    font: str = "Times New Roman"
    size_half_points: int = 24  # 24 half-points == 12pt
    color: str = "000000"  # RRGGBB; legal filings are black
    bold: bool = False
    caps: bool = False


@dataclass(frozen=True)
class DocSpec:
    """A complete document format."""

    name: str
    page_width: int = 8 * INCH
    page_height: int = 11 * INCH
    margin_top: int = INCH
    margin_bottom: int = INCH
    margin_left: int = INCH
    margin_right: int = INCH
    header_distance: int = int(0.5 * INCH)
    footer_distance: int = int(0.5 * INCH)
    require_footer_page_number: bool = True
    # Pleading paper: continuous line numbers in the left margin.
    require_line_numbering: bool = False
    # House style, applied uniformly by the renderer. The model never chooses.
    sentence_spaces: int = 2
    case_name_style: str = "italic"  # "italic" (Bluebook) or "underline"
    styles: dict[str, StyleSpec] = field(default_factory=dict)

    def style_names(self) -> set[str]:
        return set(self.styles)


# A conventional US litigation format: Letter paper, 1" margins, Times New
# Roman 12pt, double-spaced body. Close enough to most state and federal
# trial-court rules to be a realistic fixture.
LITIGATION = DocSpec(
    name="litigation-us-letter",
    styles={
        "Body Text": StyleSpec(
            name="Body Text", spacing_line=480, first_line_indent=int(0.5 * INCH)
        ),
        "Heading 1": StyleSpec(
            name="Heading 1",
            spacing_line=240,
            space_before=240,
            space_after=120,
            bold=True,
            alignment="center",
        ),
        "Heading 2": StyleSpec(
            name="Heading 2",
            spacing_line=240,
            space_before=200,
            space_after=100,
            bold=True,
        ),
        "Block Quote": StyleSpec(
            name="Block Quote",
            spacing_line=240,
            left_indent=int(0.5 * INCH),
            size_half_points=22,  # 11pt, common for block quotes
        ),
        "Signature": StyleSpec(name="Signature", spacing_line=240, space_before=240),
        "Certificate": StyleSpec(name="Certificate", spacing_line=240, space_before=240),
        "Caption": StyleSpec(name="Caption", spacing_line=240, alignment="center"),
    },
)
