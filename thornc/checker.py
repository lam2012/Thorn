"""Check-time rules: regions, moves, visibility, seals, uses, widths, discard (M2).

Single-file scope. Sharing across tasks needs channels and the task tree,
so E-SHARE-01 and E-GC-01 stay with M3. No new codes are introduced here.
"""

import os
import re
from dataclasses import dataclass, field

from . import imports
from .errors import (
    E_DAEMON_01,
    E_DISCARD_01,
    E_MOVE_01,
    E_NONDET_01,
    E_REGION_01,
    E_TYPE_01,
    W_CONTRACT_01,
    Diagnostic,
)
from .lex import TokenLine, bracket_delta, split_args

CATALOG_ROOTS = ("Std", "Oracles", "Lex", "Foreign")
CONTRACT_KINDS = ("behavior", "daemon")

DEF_RE = re.compile(r"^(?:(?:open|local)\s+)?(behavior|spawn|daemon|task)\s+([A-Za-z_][A-Za-z0-9_]*)")
BARE_DECL_RE = re.compile(r"^(shape|behavior|capability)(?=\s|$)")
USES_RE = re.compile(r"uses\s*\[([^\]]*)\]")
FAILS_RE = re.compile(r"fails\s*\{[^}]*\}")
REGION_RE = re.compile(r"^region\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+gc)?\s*:$")
LET_RE = re.compile(
    r"^let\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(\S+)\s+in\s+([A-Za-z_][A-Za-z0-9_]*)\s*="
)
DISCARD_RE = re.compile(r"^discard\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
ARM_RE = re.compile(r"^(Ok|Err)\s+(\S+)\s*->")
PARAMS_RE = re.compile(r"\(([^)]*)\)")
CALL_RE = re.compile(r"(?<![A-Za-z_0-9.])([A-Za-z_][A-Za-z0-9_]*)\[")
IMPORT_CALL_RE = re.compile(r"(?<![A-Za-z_0-9.])([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\[")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
DOTTED_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)")
STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"')
BARE_NUM_RE = re.compile(r"\b(Int|Float)\b")
NONDET_RE = re.compile(r"\bnondet\b")


@dataclass
class _Logical:
    lineno: int
    indent: int
    text: str


@dataclass
class _Def:
    kind: str
    name: str
    indent: int
    lineno: int
    uses: set[str] = field(default_factory=set)
    nondet: bool = False
    params: list[str] | None = None


def _strip_strings(text: str) -> str:
    return STRING_RE.sub('""', text)


def logical_lines(token_lines: list[TokenLine]) -> list[_Logical]:
    """Join bracket-continued physical lines into logical lines."""
    out: list[_Logical] = []
    buf: list[TokenLine] = []
    depth = 0
    for tl in token_lines:
        if tl.blank:
            continue
        delta = bracket_delta(tl.text)
        if not buf and depth == 0 and delta <= 0:
            out.append(_Logical(tl.lineno, tl.indent, tl.text))
            continue
        buf.append(tl)
        depth += delta
        if depth <= 0:
            depth = 0
            first = buf[0]
            out.append(_Logical(first.lineno, first.indent, " ".join(b.text for b in buf)))
            buf = []
    if buf:
        first = buf[0]
        out.append(_Logical(first.lineno, first.indent, " ".join(b.text for b in buf)))
    return out


def _parse_uses(text: str) -> set[str]:
    match = USES_RE.search(text)
    if match is None:
        return set()
    return {part.strip() for part in match.group(1).split(",") if part.strip()}


def check(token_lines: list[TokenLine], src_path: str | None = None) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    lines = logical_lines(token_lines)

    regions: list[tuple[str, int, int]] = []
    defs: list[_Def] = []
    lets: dict[str, dict] = {}
    discards: set[str] = set()
    aliases: dict[str, dict] = {}
    pending_imports: list[tuple[str, str, str, int]] = []

    for ln in lines:
        bare = BARE_DECL_RE.match(ln.text)
        if bare:
            diags.append(
                Diagnostic(None, ln.lineno, f"missing visibility marker on {bare.group(1)}")
            )
        dm = DEF_RE.match(ln.text)
        if dm:
            kind, name = dm.group(1), dm.group(2)
            if kind == "daemon" and re.search(r"\bcancel\s+[A-Za-z_]", ln.text) is None:
                diags.append(Diagnostic(E_DAEMON_01, ln.lineno, "daemon without cancel token"))
            if kind == "behavior" and any(d.name == name and d.kind == "behavior" for d in defs):
                diags.append(Diagnostic(None, ln.lineno, f"duplicate behavior definition: {name}"))
            nondet = NONDET_RE.search(ln.text) is not None
            pm = PARAMS_RE.search(ln.text)
            params = None
            if pm:
                inner = pm.group(1).strip()
                params = [] if not inner else [p.split(":")[0].strip() for p in inner.split(",")]
            defs.append(_Def(kind, name, ln.indent, ln.lineno, _parse_uses(ln.text), nondet, params))
            if kind in CONTRACT_KINDS:
                missing = [
                    clause
                    for clause in ("requires", "ensures", "cost")
                    if re.search(rf"\b{clause}\b", ln.text) is None
                ]
                if missing:
                    diags.append(
                        Diagnostic(
                            W_CONTRACT_01,
                            ln.lineno,
                            f"missing contract clause: {', '.join(missing)} (warning in v0.1)",
                        )
                    )
        rm = REGION_RE.match(ln.text)
        if rm:
            regions.append((rm.group(1), ln.indent, ln.lineno))
        lm = LET_RE.match(ln.text)
        if lm:
            name, region = lm.group(1), lm.group(3)
            decl = next(
                (r for r in regions if r[0] == region and r[1] < ln.indent and r[2] < ln.lineno),
                None,
            )
            if decl is None:
                diags.append(Diagnostic(E_REGION_01, ln.lineno, f"unknown region {region}"))
                lets[name] = {"rindent": -1, "lineno": ln.lineno}
            else:
                lets[name] = {"rindent": decl[1], "lineno": ln.lineno}
        dis = DISCARD_RE.match(ln.text)
        if dis:
            discards.add(dis.group(1))
        if BARE_NUM_RE.search(_strip_strings(ln.text)):
            diags.append(
                Diagnostic(E_TYPE_01, ln.lineno, "bare Int or Float without width")
            )
        im = imports.IMPORT_RE.match(ln.text)
        if im:
            alias = im.group(1)
            if alias in CATALOG_ROOTS:
                diags.append(Diagnostic(None, ln.lineno, f"import alias shadows catalog: {alias}"))
            elif alias in aliases or any(p[0] == alias for p in pending_imports):
                diags.append(Diagnostic(None, ln.lineno, f"duplicate import alias: {alias}"))
            else:
                pending_imports.append((alias, im.group(2), im.group(3), ln.lineno))
        elif re.match(r"^import\b", ln.text):
            diags.append(Diagnostic(None, ln.lineno, "bad import declaration"))

    entry_dir = os.path.dirname(os.path.abspath(src_path)) if src_path else os.getcwd()
    importer_seal = imports.read_seal(token_lines)
    for alias, rel, sha, lineno in pending_imports:
        if importer_seal is None:
            continue
        module, problem = imports.resolve(entry_dir, rel, sha, importer_seal)
        if problem is not None:
            diags.append(Diagnostic(None, lineno, problem))
        else:
            aliases[alias] = module

    for ln in lines:
        am = ARM_RE.match(ln.text)
        if am is None or am.group(2) == "_":
            continue
        name = am.group(2)
        body = ln.text.split("->", 1)[1]
        cand = [r for r in regions if r[2] < ln.lineno and r[1] < ln.indent]
        rindent = max((r[1] for r in cand), default=-1)
        if ln.indent <= rindent:
            diags.append(
                Diagnostic(E_REGION_01, ln.lineno, f"{name} used outside its defining region")
            )
        hits = re.findall(rf"\b{re.escape(name)}\b", _strip_strings(body))
        if len(hits) > 1:
            diags.append(Diagnostic(E_MOVE_01, ln.lineno, f"{name} used after move"))

    for name, info in lets.items():
        pattern = re.compile(rf"\b{re.escape(name)}\b")
        occurrences = [
            ln
            for ln in lines
            if ln.lineno != info["lineno"]
            and pattern.search(_strip_strings(ln.text)) is not None
            and DISCARD_RE.match(ln.text) is None
        ]
        if not occurrences:
            if name not in discards:
                diags.append(
                    Diagnostic(E_DISCARD_01, info["lineno"], f"unused value {name} without discard")
                )
            continue
        first = occurrences[0]
        if first.indent <= info["rindent"]:
            diags.append(
                Diagnostic(E_REGION_01, first.lineno, f"{name} used outside its defining region")
            )
        for extra in occurrences[1:]:
            diags.append(Diagnostic(E_MOVE_01, extra.lineno, f"{name} used after move"))

    for ln in lines:
        code = FAILS_RE.sub("fails ", USES_RE.sub("uses ", _strip_strings(ln.text)))
        hits = DOTTED_RE.findall(code)
        if not hits:
            continue
        dm = DEF_RE.match(ln.text)
        if dm:
            encloser = next(d for d in defs if d.lineno == ln.lineno)
        else:
            prior = [d for d in defs if d.lineno < ln.lineno and d.indent < ln.indent]
            if not prior:
                continue
            encloser = max(prior, key=lambda d: d.lineno)
        for root, member in hits:
            if root in CATALOG_ROOTS and f"{root}.{member}" not in encloser.uses:
                diags.append(
                    Diagnostic(
                        None,
                        ln.lineno,
                        f"capability {root}.{member} used but missing from uses",
                    )
                )

    behavior_defs = {d.name: d for d in defs if d.kind == "behavior"}
    for ln in lines:
        if DEF_RE.match(ln.text):
            continue
        code = FAILS_RE.sub("fails ", USES_RE.sub("uses ", _strip_strings(ln.text)))
        for cm in CALL_RE.finditer(code):
            head = cm.group(1)
            if head == "cancel":
                continue
            callee = behavior_defs.get(head)
            if callee is None:
                diags.append(Diagnostic(None, ln.lineno, f"not a callable behavior: {head}"))
                continue
            prior = [d for d in defs if d.lineno < ln.lineno and d.indent < ln.indent]
            if prior:
                encloser = max(prior, key=lambda d: d.lineno)
                for cap in callee.uses:
                    if cap not in encloser.uses:
                        diags.append(
                            Diagnostic(None, ln.lineno, f"callee uses {cap} not in caller uses")
                        )
            if callee.params is not None:
                depth = 1
                chars: list[str] = []
                for ch in code[cm.end():]:
                    if ch == "[":
                        depth += 1
                    elif ch == "]":
                        depth -= 1
                        if depth == 0:
                            break
                    chars.append(ch)
                inner = "".join(chars).strip()
                args = [] if inner == "" else split_args(inner)
                if len(args) != len(callee.params):
                    diags.append(Diagnostic(None, ln.lineno, f"arity mismatch calling {head}"))

    for ln in lines:
        code = FAILS_RE.sub("fails ", USES_RE.sub("uses ", _strip_strings(ln.text)))
        for cm in IMPORT_CALL_RE.finditer(code):
            alias, name = cm.group(1), cm.group(2)
            module = aliases.get(alias)
            if module is None:
                continue
            info = module["behaviors"].get(name)
            if info is None:
                diags.append(Diagnostic(None, ln.lineno, f"unknown import target: {alias}.{name}"))
                continue
            if not info["open"]:
                diags.append(Diagnostic(None, ln.lineno, f"imported behavior not open: {alias}.{name}"))
            prior = [d for d in defs if d.lineno < ln.lineno and d.indent < ln.indent]
            if prior:
                encloser = max(prior, key=lambda d: d.lineno)
                for cap in info["uses"]:
                    if cap not in encloser.uses:
                        diags.append(Diagnostic(None, ln.lineno, f"callee uses {cap} not in caller uses"))
            if info["params"] is not None:
                depth = 1
                chars: list[str] = []
                for ch in code[cm.end():]:
                    if ch == "[":
                        depth += 1
                    elif ch == "]":
                        depth -= 1
                        if depth == 0:
                            break
                    chars.append(ch)
                inner = "".join(chars).strip()
                args = [] if inner == "" else split_args(inner)
                if len(args) != len(info["params"]):
                    diags.append(Diagnostic(None, ln.lineno, f"arity mismatch calling {alias}.{name}"))

    nondet_names = {d.name for d in defs if d.nondet}
    if nondet_names:
        for d in defs:
            if d.nondet:
                continue
            for ln in lines:
                if ln.lineno <= d.lineno:
                    continue
                if ln.indent <= d.indent:
                    break
                for nn in sorted(nondet_names):
                    if re.search(rf"\b{re.escape(nn)}\b", _strip_strings(ln.text)):
                        diags.append(
                            Diagnostic(
                                None,
                                ln.lineno,
                                f"nondet call to {nn} without nondet marker",
                            )
                        )
                        break

    for d in defs:
        if d.kind not in ("behavior", "daemon") or d.nondet:
            continue
        for ln in lines:
            if ln.lineno <= d.lineno:
                continue
            if ln.indent <= d.indent:
                break
            if re.search(r"\bOracles\.[A-Za-z_]", _strip_strings(ln.text)):
                diags.append(
                    Diagnostic(E_NONDET_01, ln.lineno, "oracle capability without nondet seal")
                )
                break

    diags.sort(key=lambda d: (d.lineno, d.code or "", d.message))
    return diags
