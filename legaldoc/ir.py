"""The document IR.

This is the ONLY thing a language model is allowed to produce. Note what is
absent: no margins, no font sizes, no spacing, no indents, no page breaks
expressed as "add three blank lines". Those live in spec.py and are applied by
the renderer. An LLM cannot corrupt layout it never touches.

The IR carries *semantics*: what role each block plays in the document.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class Block(BaseModel):
    """Base for all blocks. `role` is what the renderer keys on."""


class Heading(Block):
    role: Literal["heading"] = "heading"
    level: Literal[1, 2] = 1
    text: str


class Paragraph(Block):
    role: Literal["paragraph"] = "paragraph"
    text: str
    # Semantic flags, not formatting instructions. The renderer decides how
    # each is expressed, from the spec.
    emphasis: list[str] = Field(default_factory=list)  # bold spans
    italic: list[str] = Field(default_factory=list)  # italic spans
    case_names: list[str] = Field(default_factory=list)  # cited cases
    defined_terms: list[str] = Field(default_factory=list)  # bold on first use


class BlockQuote(Block):
    role: Literal["block_quote"] = "block_quote"
    text: str
    attribution: str | None = None


class Caption(Block):
    """The court/party/title box at the top of a pleading."""

    role: Literal["caption"] = "caption"
    court: str
    parties: list[str]
    title: str
    document_title: str
    case_number: str


class SignatureBlock(Block):
    role: Literal["signature"] = "signature"
    name: str
    bar_number: str | None = None
    firm: str | None = None
    address: list[str] = Field(default_factory=list)
    phone: str | None = None
    email: str | None = None
    represented_party: str | None = None


class CertificateOfService(Block):
    role: Literal["certificate"] = "certificate"
    text: str


BlockT = Annotated[
    Union[Heading, Paragraph, BlockQuote, Caption, SignatureBlock, CertificateOfService],
    Field(discriminator="role"),
]


class Document(BaseModel):
    """A complete legal document, semantically."""

    doc_type: str
    blocks: list[BlockT]
