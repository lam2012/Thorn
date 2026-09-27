"""Vendor-pin import resolution (V2-M2, stdlib only). Offline only.

An import binds a module namespace from a vendored file: the path resolves
relative to the importing file's directory fenced to the unit root, the
content hash must match the pin, and the seal must equal the importer's
seal. Imported files are definitions-only: task declarations and nested
imports inside are rejections, so cycles cannot form. Returns definitions
plus source text; the caller builds its own trees, so this module stays
decoupled from checker and runtime internals.
"""

import hashlib
import os
import re

from . import fetch
from .lex import TokenLine, tokenize

IMPORT_RE = re.compile(r'^import\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*vendor\s*"([^"]+)"\s+hash\s*"([^"]+)"\s*$')
IMPORT_HEAD_RE = re.compile(r"^import\b")
TASK_HEAD_RE = re.compile(r"^task\b")
DEF_RE = re.compile(r"^(?:(?:open|local)\s+)?(behavior|spawn|daemon|task)\s+([A-Za-z_][A-Za-z0-9_]*)")
USES_RE = re.compile(r"uses\s*\[([^\]]*)\]")
SEAL_RE = re.compile(r"^api v(\d+)\.(\d+)$")


def _content_lines(token_lines: list[TokenLine]) -> list[TokenLine]:
    return [tl for tl in token_lines if not tl.blank]


def read_seal(token_lines: list[TokenLine]) -> str | None:
    content = _content_lines(token_lines)
    if not content:
        return None
    match = SEAL_RE.match(content[0].text)
    return match.group(0) if match else None


def resolve(entry_dir: str, rel: str, want_hash: str, importer_seal: str) -> tuple[dict | None, str | None]:
    """Resolve one import. Returns (module, None) or (None, problem).

    Module shape: {"seal": str, "behaviors": {name: info}}. Info shape:
    {"uses": set, "params": list|None, "nondet": bool, "open": bool,
    "source": str}. Problems are codeless human sentences.
    """
    full = fetch._fenced(entry_dir, rel)
    if full is None or not os.path.isfile(full):
        return None, f"unresolved import {rel}"
    with open(full, "rb") as fh:
        raw = fh.read()
    if hashlib.sha256(raw).hexdigest() != want_hash.lower():
        return None, f"import hash mismatch for {rel}"
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, f"import not decodable: {rel}"
    token_lines = tokenize(source)
    seal = read_seal(token_lines)
    if seal != importer_seal:
        return None, f"import seal mismatch for {rel}"
    behaviors: dict = {}
    for tl in _content_lines(token_lines):
        if IMPORT_HEAD_RE.match(tl.text):
            return None, f"transitive imports rejected: {rel}"
        if TASK_HEAD_RE.match(tl.text):
            return None, f"library file is definitions-only: {rel}"
        dm = DEF_RE.match(tl.text)
        if dm and dm.group(1) == "behavior":
            um = USES_RE.search(tl.text)
            uses = {p.strip() for p in um.group(1).split(",") if p.strip()} if um else set()
            pm = re.search(r"\(([^)]*)\)", tl.text)
            params = None
            if pm:
                inner = pm.group(1).strip()
                params = [] if not inner else [p.split(":")[0].strip() for p in inner.split(",")]
            behaviors[dm.group(2)] = {
                "uses": uses,
                "params": params,
                "nondet": re.search(r"\bnondet\b", tl.text) is not None,
                "open": tl.text.startswith("open "),
                "line": tl.text,
                "source": source,
            }
    return {"seal": seal, "behaviors": behaviors, "source": source}, None
