"""Line tokenizer for the M1 driver (stdlib only)."""

from dataclasses import dataclass


@dataclass
class TokenLine:
    lineno: int
    indent: int
    text: str
    comment: str
    has_tab: bool
    blank: bool
    raw: str


def _split_comment(line: str) -> tuple[str, str]:
    """Split a trailing # comment, ignoring # inside double-quoted text."""
    in_string = False
    escaped = False
    for i, ch in enumerate(line):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "#":
            return line[:i], line[i + 1 :]
    return line, ""


def tokenize(source: str) -> list[TokenLine]:
    out: list[TokenLine] = []
    for num, raw in enumerate(source.splitlines(), start=1):
        body, comment = _split_comment(raw)
        stripped = body.strip()
        if not stripped:
            out.append(TokenLine(num, 0, "", comment.strip(), False, True, raw))
            continue
        leading = body[: len(body) - len(body.lstrip())]
        has_tab = "\t" in leading
        indent = len(leading.replace("\t", ""))
        out.append(TokenLine(num, indent, stripped, comment.strip(), has_tab, False, raw))
    return out


def bracket_delta(text: str) -> int:
    """Net bracket depth change of one line, ignoring double-quoted text."""
    depth = 0
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
    return depth


def split_args(text: str) -> list[str]:
    """Split call arguments on top-level commas, strings and brackets aware."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            current.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
            current.append(ch)
        elif ch in "[{":
            depth += 1
            current.append(ch)
        elif ch in "]}":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts
