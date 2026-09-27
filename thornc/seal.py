"""Seal-line parsing (M1, stdlib only)."""

import re

from .errors import E_SEAL_01, Diagnostic
from .lex import TokenLine

SEAL_RE = re.compile(r"^api v(\d+)\.(\d+)$")


def find_seal(lines: list[TokenLine]) -> tuple[str | None, list[Diagnostic]]:
    """Return the seal and any seal diagnostics for one file."""
    diags: list[Diagnostic] = []
    first: TokenLine | None = None
    for tl in lines:
        if tl.blank:
            continue
        first = tl
        break
    if first is None:
        return None, [Diagnostic(None, 1, "empty source")]
    if SEAL_RE.match(first.text) is None:
        return None, [Diagnostic(None, first.lineno, "first line must be a seal such as `api v0.1`")]
    seal = first.text
    for tl in lines:
        if tl.blank or tl.lineno == first.lineno:
            continue
        if tl.text.startswith("api v"):
            diags.append(
                Diagnostic(E_SEAL_01, tl.lineno, "mixed seals in one file without explicit declaration")
            )
    return seal, diags
