"""Pinned-fetch manifest handling (M5, stdlib only).

Manifest file name is `fetch.lock`, resolved relative to the working root.
The first line is the version marker `# thorn-fetch: 1`. Each entry line is
`<hex sha256><two spaces><root-relative path>`. Lines starting with `#` are
comments. Verification is offline against the working tree; nothing here
touches the network.
"""

import hashlib
import os
import re

MARKER = "# thorn-fetch: 1"
MANIFEST_NAME = "fetch.lock"
ENTRY_RE = re.compile(r"^([0-9a-fA-F]{64})  (\S+)$")


def read_manifest(path: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Return (entries, problems). Problems are codeless human sentences."""
    try:
        with open(path, encoding="utf-8") as fh:
            raw_lines = fh.read().splitlines()
    except OSError as exc:
        return [], [f"cannot read manifest {path}: {exc.strerror or exc}"]
    except UnicodeDecodeError:
        return [], [f"manifest not decodable: {path}"]
    if not raw_lines or raw_lines[0].strip() != MARKER:
        return [], [f"bad manifest marker in {path}, expected `{MARKER}`"]
    entries: list[tuple[str, str]] = []
    problems: list[str] = []
    for num, raw in enumerate(raw_lines[1:], start=2):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = ENTRY_RE.match(line)
        if match is None:
            problems.append(f"bad manifest line {num} in {path}")
            continue
        entries.append((match.group(1).lower(), match.group(2)))
    return entries, problems


def _fenced(root: str, rel: str) -> str | None:
    """Join rel under root. Return None when rel escapes the root."""
    if os.path.isabs(rel):
        return None
    full = os.path.normpath(os.path.join(root, rel))
    if full != root and not full.startswith(root + os.sep):
        return None
    return full


def verify_tree(root: str, manifest_path: str) -> tuple[bool, list[str]]:
    """Verify every manifest entry against the tree. Returns (ok, failures)."""
    entries, problems = read_manifest(manifest_path)
    if problems:
        return False, problems
    failures: list[str] = []
    for want, rel in entries:
        full = _fenced(root, rel)
        if full is None:
            failures.append(f"path escapes root: {rel}")
            continue
        if not os.path.isfile(full):
            failures.append(f"missing input {rel}")
            continue
        with open(full, "rb") as fh:
            got = hashlib.sha256(fh.read()).hexdigest()
        if got != want:
            failures.append(f"pin mismatch for {rel}")
    return (not failures, failures)
