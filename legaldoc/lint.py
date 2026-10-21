"""Lint a .docx against a DocSpec.

Two distinct kinds of check, and the distinction matters:

  1. **Direct formatting** -- did someone (or some model) write raw spacing,
     indent, or font properties onto a paragraph or run instead of using a
     named style? This is the root cause of "the spacing is inconsistent".
     It is detectable with certainty, no judgment required.

  2. **Effective formatting** -- after resolving the style inheritance chain
     down to docDefaults, does the paragraph actually come out at the spec?
     This catches the case where direct formatting is absent but the style
     itself drifted.

Neither check needs an LLM. Both are exact.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from .spec import DocSpec
from .typography import double_spaced_non_sentence_ends, single_spaced_sentence_ends

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def w(tag: str) -> str:
    return f"{{{W}}}{tag}"


@dataclass
class Finding:
    code: str
    message: str
    location: str = ""

    def __str__(self) -> str:
        loc = f" @ {self.location}" if self.location else ""
        return f"[{self.code}] {self.message}{loc}"


@dataclass
class _StyleDef:
    name: str
    based_on: str | None
    ppr: etree._Element | None
    rpr: etree._Element | None


class _Styles:
    """styles.xml with inheritance resolution."""

    def __init__(self, xml: bytes):
        self.root = etree.fromstring(xml)
        self.by_id: dict[str, _StyleDef] = {}
        for st in self.root.findall(w("style")):
            sid = st.get(w("styleId"))
            name_el = st.find(w("name"))
            based = st.find(w("basedOn"))
            self.by_id[sid] = _StyleDef(
                name=name_el.get(w("val")) if name_el is not None else sid,
                based_on=based.get(w("val")) if based is not None else None,
                ppr=st.find(w("pPr")),
                rpr=st.find(w("rPr")),
            )
        defaults = self.root.find(w("docDefaults"))
        self.default_ppr = None
        self.default_rpr = None
        if defaults is not None:
            ppd = defaults.find(w("pPrDefault"))
            if ppd is not None:
                self.default_ppr = ppd.find(w("pPr"))
            rpd = defaults.find(w("rPrDefault"))
            if rpd is not None:
                self.default_rpr = rpd.find(w("rPr"))

    def name_of(self, style_id: str) -> str:
        s = self.by_id.get(style_id)
        return s.name if s else style_id

    def chain(self, style_id: str) -> list[_StyleDef]:
        out, seen, cur = [], set(), style_id
        while cur and cur not in seen and cur in self.by_id:
            seen.add(cur)
            s = self.by_id[cur]
            out.append(s)
            cur = s.based_on
        return out

    def _resolve(self, style_id: str, tag: str) -> str | None:
        """Walk style chain then docDefaults; return w:val of first hit."""
        for s in self.chain(style_id):
            el = s.ppr if tag in ("spacing", "ind", "jc") else s.rpr
            if el is None:
                continue
            for child in el.findall(w(tag)):
                # w:ind carries multiple attrs; caller handles it separately.
                return child.get(w("val"))
        default = self.default_ppr if tag in ("spacing", "ind", "jc") else self.default_rpr
        if default is not None:
            for child in default.findall(w(tag)):
                return child.get(w("val"))
        return None

    def resolved_line_spacing(self, style_id: str) -> int | None:
        for s in self.chain(style_id):
            if s.ppr is None:
                continue
            sp = s.ppr.find(w("spacing"))
            if sp is not None:
                line = sp.get(w("line"))
                if line is not None:
                    return int(line)
                rule = sp.get(w("lineRule"))
                if rule == "auto" and sp.get(w("line")) is None:
                    return 240
        return None

    def resolved_size(self, style_id: str) -> int | None:
        v = self._resolve(style_id, "sz")
        return int(v) if v else None

    def resolved_font(self, style_id: str) -> str | None:
        for s in self.chain(style_id):
            if s.rpr is None:
                continue
            f = s.rpr.find(w("rFonts"))
            if f is not None and f.get(w("ascii")):
                return f.get(w("ascii"))
        if self.default_rpr is not None:
            f = self.default_rpr.find(w("rFonts"))
            if f is not None and f.get(w("ascii")):
                return f.get(w("ascii"))
        return None

    def resolved_color(self, style_id: str) -> str | None:
        for s in self.chain(style_id):
            if s.rpr is None:
                continue
            c = s.rpr.find(w("color"))
            if c is not None:
                # A themeColor reference beats an explicit val in Word, so
                # report the theme name and let the caller flag it.
                if c.get(w("themeColor")):
                    return f"theme:{c.get(w('themeColor'))}"
                return c.get(w("val"))
        return None

    def resolved_flag(self, style_id: str, tag: str) -> bool:
        """Effective on/off for w:b, w:i, w:u through the style chain."""
        for s in self.chain(style_id):
            if s.rpr is None:
                continue
            el = s.rpr.find(w(tag))
            if el is not None:
                val = el.get(w("val"))
                return val not in ("0", "false", "none")
        return False

    def theme_font_styles(self) -> list[str]:
        """Styles whose rFonts still carry theme attributes.

        When both w:ascii and w:asciiTheme are present Word uses the theme
        font, so the explicit font name is dead weight that looks correct.
        """
        out = []
        for sid, s in self.by_id.items():
            if s.rpr is None:
                continue
            f = s.rpr.find(w("rFonts"))
            if f is not None and any("theme" in a.lower() for a in f.attrib):
                out.append(s.name)
        return out


def _run_format(styles: _Styles, style_id: str, run) -> tuple[bool, bool, bool]:
    """Effective (bold, italic, underline) for a run.

    Direct run properties win over the style chain, which is exactly the
    precedence Word uses.
    """
    flags = [styles.resolved_flag(style_id, t) for t in ("b", "i", "u")]
    rpr = run.find(w("rPr"))
    if rpr is not None:
        for idx, tag in enumerate(("b", "i", "u")):
            el = rpr.find(w(tag))
            if el is not None:
                val = el.get(w("val"))
                flags[idx] = val not in ("0", "false", "none")
    return (flags[0], flags[1], flags[2])


def _is_named_span(text: str) -> bool:
    """Looks like a case name or citation rather than a common word."""
    return len(text) >= 8 and any(c in text for c in " .,")


def _para_text(p) -> str:
    """Paragraph text with breaks and tabs flattened to spaces.

    python-docx stores a newline as <w:br/> and a tab as <w:tab/>, neither of
    which is a <w:t>, so naive concatenation silently glues words together
    (a judge name running into a department number) and creates phantom
    sentence boundaries.
    """
    out = []
    for el in p.iter():
        if el.tag == w("t"):
            out.append(el.text or "")
        elif el.tag in (w("br"), w("tab"), w("cr")):
            out.append(" ")
    return "".join(out)


def _canonical_style(name: str, allowed: set[str]) -> str | None:
    if name in allowed:
        return name
    folded = name.casefold()
    for a in allowed:
        if a.casefold() == folded:
            return a
    return None


def lint_docx(path: Path, spec: DocSpec) -> list[Finding]:
    findings: list[Finding] = []
    with zipfile.ZipFile(path) as z:
        doc_xml = z.read("word/document.xml")
        styles = _Styles(z.read("word/styles.xml"))
        has_footer = any(n.startswith("word/footer") for n in z.namelist())
        footer_xml = b""
        for n in z.namelist():
            if n.startswith("word/footer") and n.endswith(".xml"):
                footer_xml += z.read(n)

    root = etree.fromstring(doc_xml)
    body = root.find(w("body"))

    # ---- Section properties: page size, margins, line numbering ----
    sect = body.find(w("sectPr"))
    if sect is None:
        findings.append(Finding("no-section", "document has no sectPr"))
    else:
        pg_sz = sect.find(w("pgSz"))
        if pg_sz is None:
            findings.append(Finding("page-size", "no page size set"))
        else:
            got = (int(pg_sz.get(w("w"))), int(pg_sz.get(w("h"))))
            want = (spec.page_width, spec.page_height)
            if got != want:
                findings.append(
                    Finding(
                        "page-size",
                        f"page is {got[0]/1440:.2f}x{got[1]/1440:.2f}in, "
                        f"spec is {want[0]/1440:.2f}x{want[1]/1440:.2f}in",
                    )
                )
        pg_mar = sect.find(w("pgMar"))
        if pg_mar is None:
            findings.append(Finding("margins", "no margins set"))
        else:
            for attr, want in (
                ("top", spec.margin_top),
                ("bottom", spec.margin_bottom),
                ("left", spec.margin_left),
                ("right", spec.margin_right),
            ):
                raw = pg_mar.get(w(attr))
                got = int(raw) if raw is not None else None
                if got != want:
                    findings.append(
                        Finding(
                            "margins",
                            f"{attr} margin is "
                            f"{'unset' if got is None else f'{got/1440:.2f}in'}, "
                            f"spec is {want/1440:.2f}in",
                        )
                    )
        if spec.require_line_numbering and sect.find(w("lnNumType")) is None:
            findings.append(
                Finding("line-numbering", "spec requires line numbering; none present")
            )

    # ---- Footer page number ----
    if spec.require_footer_page_number:
        if not has_footer or b" PAGE " not in footer_xml:
            findings.append(
                Finding("footer-page-number", "no PAGE field in any footer")
            )

    # ---- Style-level theme leakage ----
    # Reported once per style, not per paragraph: a theme attribute silently
    # overrides the explicit font/color, and Word renders something different
    # from what the XML appears to say.
    for style_name in styles.theme_font_styles():
        if _canonical_style(style_name, spec.style_names()):
            findings.append(
                Finding(
                    "theme-font",
                    f"style {style_name!r} sets a theme font, which overrides "
                    f"its explicit font name in Word",
                )
            )

    # ---- Per-paragraph checks ----
    allowed = spec.style_names()
    last_heading_level = 0
    # (style, run text) -> set of observed formatting signatures
    emphasis_seen: dict[tuple[str, str], set[tuple[bool, bool, bool]]] = {}
    paras = body.findall(w("p"))
    for i, p in enumerate(paras):
        ppr = p.find(w("pPr"))
        style_id = "Normal"
        if ppr is not None:
            ps = ppr.find(w("pStyle"))
            if ps is not None:
                style_id = ps.get(w("val"))
        style_name = styles.name_of(style_id)
        text = _para_text(p)
        where = f"para {i} ({style_name})"

        # Word stores built-in style names lowercased in some templates
        # ("caption" vs "Caption"), so match case-insensitively and then
        # normalize to the spec's canonical spelling.
        canonical = _canonical_style(style_name, allowed)
        if canonical is None:
            findings.append(
                Finding(
                    "unknown-style",
                    f"style {style_name!r} is not in the spec",
                    where,
                )
            )
        else:
            style_name = canonical

        # -- Direct formatting: the root cause -- No style-based document
        # should ever carry these on a paragraph.
        if ppr is not None:
            for tag, code in (
                ("spacing", "direct-spacing"),
                ("ind", "direct-indent"),
                ("jc", "direct-align"),
            ):
                if ppr.find(w(tag)) is not None:
                    findings.append(
                        Finding(
                            code,
                            f"paragraph carries direct <w:{tag}/> instead of "
                            f"using the style",
                            where,
                        )
                    )

        # -- Blank-line spacing hack: an empty paragraph in a flow that is
        # not a signature block is almost always someone faking vertical
        # space. The spec supplies space_before/space_after.
        if not text.strip() and style_name not in ("Signature", "Caption"):
            findings.append(
                Finding(
                    "spacer-paragraph",
                    "empty paragraph used for vertical spacing; "
                    "use space_before/space_after in the style",
                    where,
                )
            )

        # -- Direct run formatting --
        for r_i, run in enumerate(p.iter(w("r"))):
            rpr = run.find(w("rPr"))
            if rpr is None:
                continue
            for tag in ("sz", "rFonts"):
                if rpr.find(w(tag)) is not None:
                    findings.append(
                        Finding(
                            "direct-run-format",
                            f"run {r_i} carries direct <w:{tag}/>",
                            where,
                        )
                    )

        # -- Effective formatting vs spec --
        if style_name in allowed:
            ss = spec.styles[style_name]
            if ss.spacing_line is not None:
                got = styles.resolved_line_spacing(style_id)
                if got != ss.spacing_line:
                    findings.append(
                        Finding(
                            "effective-spacing",
                            f"line spacing resolves to "
                            f"{'unset' if got is None else f'{got/240:.2f}x'}, "
                            f"spec is {ss.spacing_line/240:.2f}x",
                            where,
                        )
                    )
            got_size = styles.resolved_size(style_id)
            if got_size is not None and got_size != ss.size_half_points:
                findings.append(
                    Finding(
                        "effective-size",
                        f"font size resolves to {got_size/2:g}pt, "
                        f"spec is {ss.size_half_points/2:g}pt",
                        where,
                    )
                )
            got_font = styles.resolved_font(style_id)
            if got_font is not None and got_font != ss.font:
                findings.append(
                    Finding(
                        "effective-font",
                        f"font resolves to {got_font!r}, spec is {ss.font!r}",
                        where,
                    )
                )
            got_color = styles.resolved_color(style_id)
            if got_color is not None and got_color != ss.color:
                findings.append(
                    Finding(
                        "effective-color",
                        f"color resolves to {got_color}, spec is {ss.color}",
                        where,
                    )
                )

        # -- Sentence spacing: the exact check for "two spaces after every
        # sentence" applied wrongly, with no false positives from
        # abbreviations or citations.
        if spec.sentence_spaces == 2:
            for _, snippet in single_spaced_sentence_ends(text):
                findings.append(
                    Finding(
                        "sentence-spacing",
                        f"sentence end has one space, spec is two: ...{snippet}...",
                        where,
                    )
                )
            for _, snippet in double_spaced_non_sentence_ends(text):
                findings.append(
                    Finding(
                        "sentence-spacing-false",
                        f"two spaces after a period that is not a sentence "
                        f"end: ...{snippet}...",
                        where,
                    )
                )

        # -- Emphasis consistency: the same named span must look the same
        # everywhere it appears. Catches "bolded here, plain there" without
        # needing a ground-truth answer key.
        for run in p.iter(w("r")):
            rtext = "".join(t.text or "" for t in run.iter(w("t")))
            if not rtext.strip() or not _is_named_span(rtext):
                continue
            key = (style_name, rtext)
            emphasis_seen.setdefault(key, set()).add(
                _run_format(styles, style_id, run)
            )

        # -- Heading order --
        if style_name.startswith("Heading "):
            try:
                lvl = int(style_name.split()[1])
            except (IndexError, ValueError):
                lvl = 0
            if lvl and last_heading_level and lvl > last_heading_level + 1:
                findings.append(
                    Finding(
                        "heading-order",
                        f"heading jumps from level {last_heading_level} "
                        f"to {lvl}",
                        where,
                    )
                )
            if lvl:
                last_heading_level = lvl

    # ---- Emphasis consistency, reported once per offending span ----
    for (style_name, rtext), sigs in emphasis_seen.items():
        if len(sigs) > 1:
            rendered = sorted(
                "/".join(k for k, on in zip(("bold", "italic", "underline"), s) if on)
                or "plain"
                for s in sigs
            )
            findings.append(
                Finding(
                    "emphasis-inconsistent",
                    f"{rtext!r} appears as {' and '.join(rendered)} "
                    f"within style {style_name!r}",
                )
            )

    return findings
