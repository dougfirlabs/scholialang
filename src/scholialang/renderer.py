"""Scholia renderer — AST → Markdown-embedded XML-ish for humans.

Produces the same shape used throughout the Scholia notation reference:
each Step becomes a level-2 heading, each atom becomes a fenced
``xml`` block, and internal references become anchor links when the
target atom carries an id.

Output is deliberately readable in a vanilla Markdown viewer — no
custom extensions, no shortcodes. The renderer is string-building
only; no templating engine pulled in.
"""
from __future__ import annotations

from scholialang.atoms import (
    KIND_SPECIFIC_FIELDS,
    Atom,
    Step,
    wire_name,
)


def _escape_xml_content(value: str) -> str:
    """Escape &/</> so the rendered block is valid XML-ish content."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _render_attrs(atom: Atom) -> str:
    """Render kind-specific attributes as ``key="value"`` tokens."""
    parts: list[str] = []
    if atom.id:
        parts.append(f'id="{_escape_attr(atom.id)}"')
    for field_name in KIND_SPECIFIC_FIELDS.get(atom.kind, ()):
        value = getattr(atom, field_name, None)
        if value is None:
            continue
        if isinstance(value, list):
            # Lists render as separate inline notation below — skip.
            continue
        parts.append(f'{wire_name(field_name)}="{_escape_attr(str(value))}"')
    return (" " + " ".join(parts)) if parts else ""


def _escape_attr(value: str) -> str:
    return value.replace('"', '\\"')


def render_atom(atom: Atom, indent: int = 0) -> str:
    """Render one atom (+ any nested children) as XML-ish text."""
    pad = "  " * indent
    if atom.kind == "Meta:research-mode":
        return f"{pad}<Meta:research-mode/>"
    open_tag = f"<{atom.kind}{_render_attrs(atom)}>"
    close_tag = f"</{atom.kind}>"
    lines: list[str] = [f"{pad}{open_tag}"]

    # List-valued fields (options / constraints) render as indented
    # dash lines so the parser's ``_extract_list_options`` picks them
    # back up on roundtrip.
    for field_name in KIND_SPECIFIC_FIELDS.get(atom.kind, ()):
        value = getattr(atom, field_name, None)
        if isinstance(value, list) and value:
            lines.append(f"{pad}  {wire_name(field_name)} = LIST:")
            for item in value:
                lines.append(f'{pad}    - "{item}"')

    has_list_fields = False
    for field_name in KIND_SPECIFIC_FIELDS.get(atom.kind, ()):
        value = getattr(atom, field_name, None)
        if isinstance(value, list) and value:
            has_list_fields = True
            break

    if not atom.content and not atom.children and not has_list_fields:
        return f"{pad}<{atom.kind}{_render_attrs(atom)}/>"

    if atom.content:
        content_lines = _escape_xml_content(atom.content).splitlines()
        for line in content_lines:
            lines.append(f"{pad}  {line}")

    # Operators already appear inside ``content`` for round-trip
    # fidelity — do not re-emit them here, or the next parse pass
    # would double-count.

    for child in atom.children:
        lines.append(render_atom(child, indent=indent + 1))

    lines.append(f"{pad}{close_tag}")
    return "\n".join(lines)


def render_step(step: Step, *, level: int = 2) -> str:
    """Render a Step as an ``<Step>`` XML block under a Markdown heading."""
    heading_hashes = "#" * level
    title = step.name or step.id or "(unnamed step)"
    lines: list[str] = [f"{heading_hashes} {title}"]
    if step.id:
        lines.append("")
        lines.append(f'_id: `{step.id}`_')
    lines.append("")
    lines.append("```xml")
    lines.append(
        f'<Step id="{_escape_attr(step.id or "")}"'
        f' name="{_escape_attr(step.name or "")}">'
    )
    for atom in step.atoms:
        lines.append(render_atom(atom, indent=1))
    lines.append("</Step>")
    lines.append("```")
    return "\n".join(lines)


def render_markdown(trace: list[Step], *, title: str | None = None) -> str:
    """Render a whole trace as Markdown with fenced XML-ish blocks."""
    parts: list[str] = []
    if title:
        parts.append(f"# {title}")
        parts.append("")
    for step in trace:
        parts.append(render_step(step))
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def render_xml(trace: list[Step]) -> str:
    """Render a whole trace as pure XML-ish (no Markdown chrome)."""
    lines: list[str] = []
    for step in trace:
        lines.append(
            f'<Step id="{_escape_attr(step.id or "")}"'
            f' name="{_escape_attr(step.name or "")}">'
        )
        for atom in step.atoms:
            lines.append(render_atom(atom, indent=1))
        lines.append("</Step>")
    return "\n".join(lines) + "\n"
