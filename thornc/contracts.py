"""Contract obligations: cost-vs-bound, decreases, ensures plumbing (M4, stdlib only).

- `result` names the Ok payload at exit inside `ensures`.
- A fold bound that exceeds its cost is a codeless build rejection (the
  registry carries no cost code; run_m4.py records the same sentence).
  A bare-name bound passes static and is verified against cost at run time;
  anything more complex is a codeless build rejection in M4.
- Structural recursion is accepted when every self-call site passes at least
  one argument rooted at the decreases parameter through field (`.`) or
  subscript (`[`) projection. Anything else with a self-reference records
  W-TERM-01. Parameter-declaration checking and stronger measures wait for
  M5 or a future prover.
"""

import re

from .checker import DEF_RE, logical_lines
from .errors import W_TERM_01, Diagnostic
from .lex import TokenLine, split_args

COST_RE = re.compile(r"cost\s*\{\s*mem\s*<=\s*([0-9][0-9_]*)\s*(k|K)?\s*\}")
FOLD_RE = re.compile(r"^fold\s+bound\s+(.+?)\s*:$")
DECREASES_RE = re.compile(r"decreases\s+([A-Za-z_][A-Za-z0-9_]*)")
LIT_RE = re.compile(r"^[+-]?[0-9][0-9_]*$")
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ENSURES_RE = re.compile(r"ensures\s+(.+?)(?=\s+(?:cost|decreases|nondet)\b|\s*=\s*$)")
PRED_TOK_RE = re.compile(r'"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z0-9_]*|[0-9][0-9_]*|==|<=|and|or')


def parse_cost_membytes(defline: str) -> int | None:
    match = COST_RE.search(defline)
    if match is None:
        return None
    value = int(match.group(1).replace("_", ""))
    if match.group(2) is not None:
        value *= 1024
    return value


def parse_ensures(defline: str) -> str | None:
    match = ENSURES_RE.search(defline)
    if match is None:
        return None
    return match.group(1).strip()


REQUIRES_RE = re.compile(r"requires\s+(.+?)(?=\s+(?:ensures|cost|decreases|nondet)\b|\s*=\s*$)")


def parse_requires(defline: str) -> str | None:
    match = REQUIRES_RE.search(defline)
    if match is None:
        return None
    return match.group(1).strip()


class _Predicates:
    """Tiny ensures-predicate evaluator: true/false, names, quoted text,
    integers, ==, <=, and, or. Anything else raises ValueError."""

    def __init__(self, text: str, bindings: dict) -> None:
        stripped = text.strip()
        if not stripped:
            raise ValueError("empty ensures predicate")
        tokens = PRED_TOK_RE.findall(stripped)
        if "".join(tokens).replace(" ", "") != stripped.replace(" ", ""):
            raise ValueError(f"bad ensures predicate: {text}")
        self.tokens = tokens
        self.pos = 0
        self.bindings = bindings

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def next(self) -> str:
        token = self.peek()
        if token is None:
            raise ValueError("truncated ensures predicate")
        self.pos += 1
        return token

    def parse(self) -> bool:
        value = self.parse_or()
        if self.peek() is not None:
            raise ValueError("trailing tokens in ensures predicate")
        return value

    def parse_or(self) -> bool:
        value = self.parse_and()
        while self.peek() == "or":
            self.next()
            value = value or self.parse_and()
        return value

    def parse_and(self) -> bool:
        value = self.parse_cmp()
        while self.peek() == "and":
            self.next()
            value = value and self.parse_cmp()
        return value

    def parse_cmp(self) -> bool:
        left = self.parse_atom()
        op = self.peek()
        if op not in ("==", "<="):
            if not isinstance(left, bool):
                raise ValueError("ensures positions must be boolean")
            return left
        self.next()
        right = self.parse_atom()
        if op == "==":
            return left == right
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            raise ValueError("<= needs numbers in ensures predicate")
        return left <= right

    def parse_atom(self):
        token = self.next()
        if token == "true":
            return True
        if token == "false":
            return False
        if token.startswith('"'):
            return token[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        if re.fullmatch(r"[+-]?[0-9][0-9_]*", token):
            return int(token.replace("_", ""))
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
            if token in ("and", "or"):
                raise ValueError(f"misplaced keyword in ensures predicate: {token}")
            if token not in self.bindings:
                raise ValueError(f"unbound name in ensures predicate: {token}")
            return self.bindings[token]
        raise ValueError(f"bad ensures atom: {token}")


def eval_ensures(pred: str, bindings: dict) -> bool:
    return _Predicates(pred, bindings).parse()


def _rooted_at(arg: str, param: str) -> bool:
    arg = arg.strip()
    return arg.startswith(param + ".") or arg.startswith(param + "[")


def check_file(token_lines: list[TokenLine]) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    lines = logical_lines(token_lines)
    for ln in lines:
        dm = DEF_RE.match(ln.text)
        if dm is None or dm.group(1) not in ("behavior", "daemon"):
            continue
        name = dm.group(2)
        cost = parse_cost_membytes(ln.text)
        for bl in lines:
            if bl.lineno <= ln.lineno:
                continue
            if bl.indent <= ln.indent:
                break
            fm = FOLD_RE.match(bl.text)
            if fm is None:
                continue
            if cost is None:
                continue
            bound = fm.group(1).strip()
            if LIT_RE.fullmatch(bound) is not None:
                if int(bound.replace("_", "")) > cost:
                    diags.append(
                        Diagnostic(None, bl.lineno, f"fold bound {bound} exceeds cost {cost}")
                    )
                continue
            if NAME_RE.fullmatch(bound) is None:
                diags.append(
                    Diagnostic(None, bl.lineno, "fold bound too complex for M4")
                )
        decrease = DECREASES_RE.search(ln.text)
        call_inners: list[str] = []
        for bl in lines:
            if bl.lineno <= ln.lineno:
                continue
            if bl.indent <= ln.indent:
                break
            for call in re.finditer(rf"\b{re.escape(name)}\s*\[(.*?)\]", bl.text):
                call_inners.append(call.group(1))
        if not call_inners:
            continue
        param = decrease.group(1) if decrease else None
        structural = param is not None and all(
            any(_rooted_at(arg, param) for arg in split_args(inner))
            for inner in call_inners
        )
        if not structural:
            diags.append(
                Diagnostic(
                    W_TERM_01,
                    ln.lineno,
                    "recursive behavior without proven decreases (warning in v0.1)",
                )
            )
    diags.sort(key=lambda d: (d.lineno, d.code or "", d.message))
    return diags
