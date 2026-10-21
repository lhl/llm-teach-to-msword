"""Build the reference template (.docx) from a DocSpec.

The template is where all layout lives. Every paragraph style is fully
specified here, including docDefaults, so that nothing downstream inherits a
surprise from python-docx's stock template (Calibri 11, 1.08 line spacing).
"""

from __future__ import annotations

from pathlib import Path

from docx import Document as new_docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Emu
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from .spec import DocSpec, StyleSpec

_ALIGN = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}


def _set_doc_defaults(doc, spec: DocSpec) -> None:
    """Pin the document defaults so no style silently inherits a stray font."""
    styles_el = doc.styles.element
    rpr_default = styles_el.find(qn("w:docDefaults")).find(qn("w:rPrDefault"))
    rpr = rpr_default.find(qn("w:rPr"))
    for tag in ("w:rFonts", "w:sz", "w:szCs"):
        for old in rpr.findall(qn(tag)):
            rpr.remove(old)
    fonts = OxmlElement("w:rFonts")
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attr), "Times New Roman")
    rpr.append(fonts)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), "24")
    rpr.append(sz)
    szcs = OxmlElement("w:szCs")
    szcs.set(qn("w:val"), "24")
    rpr.append(szcs)


def _apply_style(style, ss: StyleSpec) -> None:
    pf = style.paragraph_format
    pf.space_before = Emu(ss.space_before * 635)  # DXA -> EMU
    pf.space_after = Emu(ss.space_after * 635)
    pf.left_indent = Emu(ss.left_indent * 635)
    pf.first_line_indent = Emu(ss.first_line_indent * 635)
    pf.alignment = _ALIGN[ss.alignment]
    if ss.spacing_line is not None:
        # line_spacing_rule must be set or Word interprets the value as points
        from docx.enum.text import WD_LINE_SPACING

        pf.line_spacing = ss.spacing_line / 240
        pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE

    font = style.font
    font.name = ss.font
    font.size = Emu(ss.size_half_points * 6350)  # half-points -> EMU
    font.bold = ss.bold
    font.all_caps = ss.caps
    # East Asian / complex script font must match or Word substitutes.
    rpr = style.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    # A theme attribute wins over the explicit font in OOXML. python-docx's
    # stock Heading styles set both, so the explicit font is silently ignored
    # and Word renders the theme font. Strip the theme attributes.
    for attr in list(fonts.attrib):
        if "theme" in attr.lower():
            del fonts.attrib[attr]
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attr), ss.font)

    # Same trap for color: a themeColor reference overrides w:val.
    from docx.shared import RGBColor

    font.color.rgb = RGBColor.from_string(ss.color)
    color_el = rpr.find(qn("w:color"))
    if color_el is not None:
        for attr in list(color_el.attrib):
            if "theme" in attr.lower():
                del color_el.attrib[attr]


def _add_page_number_footer(doc, spec: DocSpec) -> None:
    section = doc.sections[0]
    footer = section.footer
    para = footer.paragraphs[0]
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = para.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_end)


def _set_line_numbering(doc) -> None:
    """Continuous line numbering in the left margin (pleading paper)."""
    section = doc.sections[0]
    sect_pr = section._sectPr
    ln = OxmlElement("w:lnNumType")
    ln.set(qn("w:countBy"), "1")
    ln.set(qn("w:restart"), "continuous")
    ln.set(qn("w:distance"), "360")
    sect_pr.append(ln)


def build_template(spec: DocSpec, out: Path) -> Path:
    doc = new_docx()
    _set_doc_defaults(doc, spec)

    section = doc.sections[0]
    section.page_width = Emu(spec.page_width * 635)
    section.page_height = Emu(spec.page_height * 635)
    section.top_margin = Emu(spec.margin_top * 635)
    section.bottom_margin = Emu(spec.margin_bottom * 635)
    section.left_margin = Emu(spec.margin_left * 635)
    section.right_margin = Emu(spec.margin_right * 635)
    section.header_distance = Emu(spec.header_distance * 635)
    section.footer_distance = Emu(spec.footer_distance * 635)

    # Stock template ships Normal as Calibri; make it match the body style.
    _apply_style(doc.styles["Normal"], spec.styles["Body Text"])

    for name, ss in spec.styles.items():
        if name == "Normal":
            continue
        try:
            style = doc.styles[name]
        except KeyError:
            style = doc.styles.add_style(name, 1)  # WD_STYLE_TYPE.PARAGRAPH
        _apply_style(style, ss)

    if spec.require_footer_page_number:
        _add_page_number_footer(doc, spec)
    if spec.require_line_numbering:
        _set_line_numbering(doc)

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    return out
