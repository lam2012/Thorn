"""thornc command surface (stdlib only). Exactly four verbs: build, test, fetch, version."""

import os
import subprocess
import sys

from . import checker, contracts, fetch, layout, lex, seal
from .errors import E_FETCH_01, W_CONTRACT_01, W_TERM_01, Diagnostic

VERSION = "0.1.0"
KNOWN_SEALS = ("api v0.1", "api v0.2")
PROMOTED_IN_V02 = (W_CONTRACT_01, W_TERM_01)
RUNNERS = ["tests/run_m1.py", "tests/run_m2.py", "tests/run_m3.py", "tests/run_m4.py"]
USAGE = "usage: python -m thornc {build <file>|test|fetch [manifest]|version}"


def _failed(diags: list, seal: str | None) -> bool:
    """Decide failure from diagnostics and the file seal. Codes never change."""
    for d in diags:
        if d.code is None or d.code.startswith("E-"):
            return True
        if seal == "api v0.2" and d.code in PROMOTED_IN_V02:
            return True
    return False


def _analyze(path: str) -> tuple[str | None, list]:
    try:
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
    except OSError as exc:
        return None, [Diagnostic(None, 0, f"cannot read {path}: {exc.strerror or exc}")]
    except UnicodeDecodeError:
        return None, [Diagnostic(None, 0, f"file not decodable: {path}")]
    token_lines = lex.tokenize(source)
    found, diags = seal.find_seal(token_lines)
    diags.extend(layout.check(token_lines))
    diags.extend(checker.check(token_lines, path))
    diags.extend(contracts.check_file(token_lines))
    return found, diags


def _manifest_gate() -> list:
    """Verify ./fetch.lock when present. Missing inputs are E-FETCH-01."""
    manifest = os.path.join(os.getcwd(), fetch.MANIFEST_NAME)
    if not os.path.exists(manifest):
        return []
    entries, problems = fetch.read_manifest(manifest)
    if problems:
        return [Diagnostic(None, 0, problem) for problem in problems]
    diags: list = []
    for want, rel in entries:
        full = fetch._fenced(os.getcwd(), rel)
        if full is None or not os.path.isfile(full):
            diags.append(Diagnostic(E_FETCH_01, 0, f"declared input not fetched: {rel}"))
            continue
        with open(full, "rb") as fh:
            import hashlib

            got = hashlib.sha256(fh.read()).hexdigest()
        if got != want:
            diags.append(Diagnostic(None, 0, f"pin mismatch for {rel}"))
    return diags


def cmd_build(path: str) -> int:
    found, diags = _analyze(path)
    if found is not None and found not in KNOWN_SEALS:
        diags.append(Diagnostic(None, 0, f"unsupported seal {found}"))
    diags.extend(_manifest_gate())
    for diag in diags:
        print(diag.render())
    if _failed(diags, found):
        return 1
    print(f"seal: {found} ok")
    print("layout: ok")
    print("check: ok")
    if os.path.exists(os.path.join(os.getcwd(), fetch.MANIFEST_NAME)):
        print("fetch gate: ok")
    return 0


def cmd_test() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    ok = True
    for runner in RUNNERS:
        proc = subprocess.run(
            [sys.executable, runner],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
        )
        tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "(no output)"
        print(f"{runner}: {'ok' if proc.returncode == 0 else 'FAILED'} ({tail})")
        ok = ok and proc.returncode == 0
    return 0 if ok else 1


def cmd_fetch(manifest: str) -> int:
    ok, failures = fetch.verify_tree(os.getcwd(), manifest)
    if ok:
        print(f"fetch: {manifest} verified")
        return 0
    for failure in failures:
        print(f"fetch: {failure}")
    return 1


def cmd_version() -> int:
    print("thornc 0.1.0")
    print("seals: api v0.1")
    print("api v0.2: W-CONTRACT-01, W-TERM-01 -> error")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "build":
        return cmd_build(argv[1])
    if len(argv) == 1 and argv[0] == "test":
        return cmd_test()
    if len(argv) in (1, 2) and argv[0] == "fetch":
        manifest = argv[1] if len(argv) == 2 else os.path.join(os.getcwd(), fetch.MANIFEST_NAME)
        return cmd_fetch(manifest)
    if len(argv) == 1 and argv[0] == "version":
        return cmd_version()
    print(USAGE)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
