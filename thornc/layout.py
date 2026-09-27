"""Indentation, bracket continuation, and block-nesting validation (stdlib only)."""

from .errors import Diagnostic
from .lex import TokenLine, bracket_delta

NEST_DEPTH_CAP = 64  # Block nesting levels. Symmetric with the call cap:
# deeper nesting would outgrow interpreter headroom instead of diagnosing.


def _is_opener(text: str) -> bool:
    return text.endswith((":", "::", "="))


def check(lines: list[TokenLine]) -> list[Diagnostic]:
    """Validate 2-space indentation, continuation depth, and nesting."""
    diags: list[Diagnostic] = []
    stack: list[int] = [0]
    prev_opener = True
    depth = 0
    base = 0
    last_lineno = 0

    def place(indent: int, opener: bool, lineno: int) -> None:
        nonlocal prev_opener
        if indent > stack[-1]:
            if not prev_opener or indent != stack[-1] + 2:
                diags.append(Diagnostic(None, lineno, "unexpected indent jump"))
                prev_opener = opener
                return
            stack.append(indent)
        elif indent < stack[-1]:
            while stack and stack[-1] > indent:
                stack.pop()
            if not stack or stack[-1] != indent:
                diags.append(Diagnostic(None, lineno, "dedent to unopened level"))
                stack.clear()
                stack.append(0)
                prev_opener = opener
                return
        prev_opener = opener

    for tl in lines:
        if tl.blank:
            continue
        last_lineno = tl.lineno
        if tl.has_tab:
            diags.append(Diagnostic(None, tl.lineno, "tab indentation is forbidden"))
            continue
        if tl.indent % 2 != 0:
            diags.append(
                Diagnostic(None, tl.lineno, "indentation must be a multiple of 2 spaces")
            )
            continue
        if tl.indent // 2 > NEST_DEPTH_CAP:
            diags.append(Diagnostic(None, tl.lineno, "nesting too deep"))
            continue
        delta = bracket_delta(tl.text)
        if depth > 0:
            if tl.indent <= base:
                diags.append(
                    Diagnostic(
                        None, tl.lineno, "continuation must indent deeper than opening line"
                    )
                )
                depth = 0
                place(tl.indent, _is_opener(tl.text), tl.lineno)
                if delta > 0:
                    depth = delta
                    base = tl.indent
                continue
            depth += delta
            if depth < 0:
                diags.append(Diagnostic(None, tl.lineno, "unbalanced bracket"))
                depth = 0
                place(tl.indent, _is_opener(tl.text), tl.lineno)
                continue
            if depth == 0:
                place(base, _is_opener(tl.text), tl.lineno)
            continue
        if delta < 0:
            diags.append(Diagnostic(None, tl.lineno, "unbalanced bracket"))
            continue
        place(tl.indent, _is_opener(tl.text), tl.lineno)
        if delta > 0:
            depth = delta
            base = tl.indent
    if depth > 0:
        diags.append(Diagnostic(None, last_lineno, "unclosed bracket"))
    return diags
