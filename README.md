# legaldoc

Reliable MS Word output for legal documents. The model does not touch layout.

## The problem

A model driving LibreOffice produced Word documents with inconsistent spacing,
margins, and emphasis. Two specific symptoms were reported:

- told to put two spaces after every sentence, it put two spaces after every
  *period* (`Inc.  filed`, `Smith v.  Jones`, `Cal.  App.  4th`)
- it bolded and underlined the same span inconsistently within one document

Neither is a language problem. Both are deterministic transformations that a
prompt cannot reliably control.

## The design

    messy input
        |
        v
    [ LLM: text -> semantic IR ]      <- the only model call
        |
        v
    [ deterministic renderer ]        <- spec.py + template.docx
        |
        v
    [ deterministic linter ]          <- exact checks, no judge
        |
        v
    .docx

The IR (`legaldoc/ir.py`) carries roles, not formatting: `heading`, `paragraph`,
`block_quote`, `caption`, `signature`, `certificate`. It has no field for
margins, spacing, fonts, or blank paragraphs. Layout is therefore not something
the model can get wrong.

Layout lives in `legaldoc/spec.py` as data. One document format is defined there
today (`LITIGATION`): US Letter, 1" margins, Times New Roman 12pt, double-spaced
body, `PAGE` field in the footer, two spaces after sentences, case names
italicized.

## What the linter checks

`legaldoc/lint.py` reports findings without any model in the loop.

Direct formatting, which is the root cause of drift:

| code | meaning |
| --- | --- |
| `direct-spacing` | paragraph carries its own `<w:spacing/>` instead of using a style |
| `direct-indent` | paragraph carries its own `<w:ind/>` |
| `direct-align` | paragraph carries its own `<w:jc/>` |
| `direct-run-format` | a run carries its own font or size |
| `spacer-paragraph` | empty paragraph used as vertical space |
| `unknown-style` | paragraph style is not in the spec |

Effective formatting, after resolving the style chain down to `docDefaults`:

| code | meaning |
| --- | --- |
| `margins`, `page-size` | section geometry differs from the spec |
| `effective-spacing` | line spacing resolves to the wrong multiple |
| `effective-font`, `effective-size`, `effective-color` | style resolves wrong |
| `theme-font` | a style sets a theme font, which overrides its explicit font name |
| `footer-page-number` | no `PAGE` field in any footer |
| `line-numbering` | pleading paper required, none present |
| `heading-order` | heading levels skip |

Text and emphasis:

| code | meaning |
| --- | --- |
| `sentence-spacing` | a real sentence end has one space, spec wants two |
| `sentence-spacing-false` | two spaces after a period that does not end a sentence |
| `emphasis-inconsistent` | the same named span is formatted two ways in one style |

`sentence-spacing-false` and `sentence-spacing` are complementary. Together they
catch the reported bug in both directions.

## Two OOXML traps worth knowing

Both were live bugs in this repository's own renderer, found by rendering and
looking at the output.

1. **A theme attribute beats an explicit font.** python-docx's stock Heading
   styles set both `w:ascii="Times New Roman"` and `w:asciiTheme="majorHAnsi"`.
   Word uses the theme font, so the explicit name is silently ignored. Same for
   `w:color` with `w:themeColor`. `template.py` strips the theme attributes;
   `lint.py` reports `theme-font`.

2. **`<w:br/>` is not `<w:t>`.** A paragraph containing a line break
   concatenates the two lines into one word if you only collect `w:t` nodes,
   which
   invents a sentence boundary. `_para_text` flattens breaks and tabs to spaces.

Schema validation does not catch either. The `docx` skill published by Anthropic
validates OOXML against XSD; it has no style or spacing checks, so it passes a
document with 1.25" margins and direct spacing overrides.

## Running it

```bash
mamba activate dspy          # dspy 3.4.1, python-docx, lxml, pydantic
python demo.py               # renders a clean motion, reproduces the bugs, lints both
python -m pytest tests/ -q   # 49 tests, all deterministic
```

`demo.py` renders a motion from the IR, then mutates the `.docx` the way a model
editing in LibreOffice does: nudges a margin, adds a direct spacing override,
inserts blank spacer paragraphs, substitutes a font on one run, applies the
naive two-space rule, italicizes one case-name occurrence but not the other,
and drops the footer field. The clean document lints to zero findings; the
mangled one reports every mutation.

To inspect the output:

```bash
soffice --headless --convert-to pdf --outdir build build/motion.docx
pdftoppm -png -r 80 build/motion.pdf build/page
```

## Evals and GEPA

`evals/fixtures.py` holds four labeled examples: a motion, a letter, a memo with
a block quote, and one PDF-extracted motion with pleading line numbers and page
headers interleaved.

`evals/metric.py` scores six components, none of which is an LLM judge:

| component | weight | check |
| --- | --- | --- |
| `valid` | 0.15 | JSON parses and satisfies the IR schema (exact) |
| `grounded` | 0.15 | every declared span appears in its own block's text (exact) |
| `roles` | 0.15 | block-role sequence vs gold |
| `text` | 0.15 | verbatim text fidelity vs gold |
| `cases` | 0.15 | F1 of cited case names |
| `clean_render` | 0.25 | renders, and the `.docx` lints with zero findings (exact) |

`clean_render` is what ties the prompt to the lawyer's complaint. A model that
invents a span, emits double spaces, or adds a blank paragraph cannot score on
it. Gold scores 1.000 against itself, so the ceiling is reachable.

```bash
python -m evals.run          # baseline
python -m evals.gepa         # optimize the extraction prompt
```

GEPA optimizes exactly one thing: the instruction text of `ExtractIR`. It cannot
affect margins, spacing, fonts, or emphasis, because those are not in the prompt.
That is deliberate. Pointing an optimizer at a deterministic problem wastes the
optimizer and leaves the bug in place.

Observed on the four fixtures with `qwen38-flash-next-nvfp4`:

    baseline   mean=0.974   [1.0, 0.979, 1.0, 0.918]
    optimized  mean=0.996   [1.0, 1.0,   1.0, 0.983]

**These numbers are in-sample.** `evals/gepa.py` uses the same four examples for
training and validation, so 0.996 is not a generalization estimate. The run
demonstrates that the loop closes and that the feedback is specific enough to
drive useful edits. The optimized prompt picked up rules that were not in the
original, each traceable to a fixture failure:

- "Ignore page headers, footers, page labels, page numbers, pleading-style line
  numbers, and page breaks" (from the PDF-extracted motion)
- "Do not treat PLEASE TAKE NOTICE or similar opening phrases as headings; they
  are paragraphs" (from the letter fixture's role error)
- "Do not use a caption role and do not output caption metadata" (from the
  model inventing a caption block)

A real optimization needs 20-50 labeled documents and a held-out set. The labels
are the expensive part; the metric is cheap once they exist.

## What is not built yet

- **`.dotx` import.** If the firm already has Word templates, `spec.py` should
  be generated from them rather than written by hand. The lawyer almost
  certainly has these.
- **Tables and exhibits.** The IR has no table block. Legal documents need them.
- **Numbering.** Auto-numbered paragraphs use `numPr` referencing the template's
  list definitions; not implemented.
- **Court-specific rules.** One format is defined. Local rules vary by
  jurisdiction and judge, and some require line numbering on pleading paper.
- **Tracked changes and redlining.** Out of scope here; see below.
- **PDF round-trip check.** Converting to PDF and comparing page count and text
  bounding boxes against a golden PDF catches layout drift that XML inspection
  misses. Not implemented.

## On the Anthropic docx skill

The skill is proprietary. Its `LICENSE.txt` forbids retaining copies outside
Anthropic's services, creating derivative works, and redistribution, so it is not
vendored here. Nothing in this repository is derived from it. It was read for
reference only and the copy was deleted.

Two observations from reading it, offered as design notes rather than as copied
material:

- It is built around `docx-js` (Node) for creation and LibreOffice for
  conversion. Its gotcha list — A4 default page size, dual table widths,
  `ShadingType.SOLID` rendering black — is a list of layout primitives a model
  has to get right by hand. This repository's approach removes that list.
- Its validator checks OOXML against XSD schemas. That is file validity, not
  house style. It will not catch a wrong margin.

If you want the redlining and comment machinery, use the skill through Anthropic's
own distribution rather than copying the files.
