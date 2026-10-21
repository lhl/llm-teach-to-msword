"""Command line interface.

    legaldoc lint motion.docx            check a document against the spec
    legaldoc render ir.json -o out.docx  build a document from an IR file
    legaldoc template -o template.docx   write the reference template
    legaldoc spec                        print the active formatting spec

Exit code is 0 on success and 1 when lint reports findings or a command fails,
so it composes in a shell or CI step.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ir import Document
from .lint import lint_docx
from .render import UnmatchedMark, render
from .spec import LITIGATION, DocSpec
from .template import build_template

SPECS: dict[str, DocSpec] = {LITIGATION.name: LITIGATION}


def _spec(name: str) -> DocSpec:
    try:
        return SPECS[name]
    except KeyError:
        raise SystemExit(
            f"unknown spec {name!r}; available: {', '.join(sorted(SPECS))}"
        ) from None


def cmd_lint(args) -> int:
    spec = _spec(args.spec)
    failed = False
    for path_str in args.files:
        path = Path(path_str)
        if not path.exists():
            print(f"{path}: no such file", file=sys.stderr)
            failed = True
            continue
        findings = lint_docx(path, spec)
        if findings:
            failed = True
            print(f"{path}: {len(findings)} finding(s)")
            for f in findings:
                print(f"  {f}")
        else:
            print(f"{path}: clean")
    return 1 if failed else 0


def cmd_render(args) -> int:
    spec = _spec(args.spec)
    try:
        doc_ir = Document.model_validate_json(Path(args.ir).read_text())
    except FileNotFoundError:
        print(f"{args.ir}: no such file", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"{args.ir}: invalid IR: {e}", file=sys.stderr)
        return 1

    template_path = (
        Path(args.template)
        if args.template
        else build_template(spec, Path(args.out).with_suffix(".template.docx"))
    )
    try:
        out = render(doc_ir, spec, template_path, Path(args.out))
    except UnmatchedMark as e:
        print(f"render failed: {e}", file=sys.stderr)
        return 1

    findings = lint_docx(out, spec)
    print(f"wrote {out}")
    if findings:
        print(f"{len(findings)} finding(s):")
        for f in findings:
            print(f"  {f}")
        return 1
    return 0


def cmd_template(args) -> int:
    spec = _spec(args.spec)
    out = build_template(spec, Path(args.out))
    print(f"wrote {out}")
    return 0


def cmd_spec(args) -> int:
    spec = _spec(args.spec)
    print(f"spec: {spec.name}")
    print(
        f"page: {spec.page_width/1440:.2f} x {spec.page_height/1440:.2f} in, "
        f"margins T{spec.margin_top/1440:.2f} B{spec.margin_bottom/1440:.2f} "
        f"L{spec.margin_left/1440:.2f} R{spec.margin_right/1440:.2f} in"
    )
    print(f"sentence spacing: {spec.sentence_spaces} space(s)")
    print(f"case name style: {spec.case_name_style}")
    print(f"footer page number: {spec.require_footer_page_number}")
    print(f"line numbering: {spec.require_line_numbering}")
    print("styles:")
    for name, ss in spec.styles.items():
        spacing = (
            f"{ss.spacing_line/240:.2f}x" if ss.spacing_line is not None else "unset"
        )
        print(
            f"  {name:<14} {ss.font} {ss.size_half_points/2:g}pt "
            f"{ss.color} line={spacing} align={ss.alignment}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="legaldoc",
        description="Render and lint legal documents as .docx with layout held in data.",
    )
    p.add_argument(
        "--spec",
        default=LITIGATION.name,
        help=f"format spec to use (default: {LITIGATION.name})",
    )
    sub = p.add_subparsers(dest="command", required=True)

    lint = sub.add_parser("lint", help="check .docx files against the spec")
    lint.add_argument("files", nargs="+")
    lint.set_defaults(func=cmd_lint)

    r = sub.add_parser("render", help="render an IR JSON file to .docx")
    r.add_argument("ir", help="path to an IR JSON file")
    r.add_argument("-o", "--out", required=True, help="output .docx path")
    r.add_argument(
        "--template", help="reference .docx template (default: build one from the spec)"
    )
    r.set_defaults(func=cmd_render)

    t = sub.add_parser("template", help="write the reference template")
    t.add_argument("-o", "--out", required=True, help="output .docx path")
    t.set_defaults(func=cmd_template)

    s = sub.add_parser("spec", help="print the active formatting spec")
    s.set_defaults(func=cmd_spec)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
