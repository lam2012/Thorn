"""M6 v0.2 promotion conformance (stdlib only). The driver enforces severity.

Method: copy the 15 statically clean corpus files to a temp dir with ONLY
the first seal line flipped from api v0.1 to api v0.2, layout byte-identical
otherwise. No fetch.lock is carried over, so the manifest gate sleeps. The
driver itself promotes W-CONTRACT-01 and W-TERM-01 to errors under the v0.2
seal with codes unchanged, so this runner asserts build results directly:

Fail under v0.2 (W-CONTRACT-01): greet, parse, daemon, stamp, cont, cancel,
bad-scan.
Stay green: pair (no behavior or daemon definitions, hence no warnings),
fold, contract, bad-ensures, foldname, rand, and recurse. Recurse is the
TERM branch coverage: as the only TERM-implicated file it must show neither
W-CONTRACT-01 nor W-TERM-01. No corpus file emits W-TERM-01 today; a future
unproven-decreases case flips under the same driver rule.
overcost.thorn keeps rc 1 through its cost rejection, unchanged.
bad-seal-unknown.thorn (native api v9.9 seal, not flipped) is rejected
codeless with no E- code. Old negative files are not rehearsed: promotion
changes nothing about them.

Out of scope on purpose: this runner never enters the `test` aggregator,
which stays exactly run_m1..run_m4. No toolchain, docs, or codes change
beyond the M7 severity rule already reviewed.
"""

import os
import re
import subprocess
import sys
import tempfile

PIN = "0"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEAL_RE = re.compile(r"^api v\d+\.\d+\s*$")

FLIP_TO_FAIL = [
    "greet.thorn",
    "parse.thorn",
    "daemon.thorn",
    "stamp.thorn",
    "cont.thorn",
    "cancel.thorn",
    "bad-scan.thorn",
]
STAY_GREEN = [
    "pair.thorn",
    "fold.thorn",
    "contract.thorn",
    "recurse.thorn",
    "bad-ensures.thorn",
    "foldname.thorn",
    "rand.thorn",
]


def invoke(args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = PIN
    env["PYTHONPATH"] = ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "thornc"] + args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


def main() -> int:
    if os.environ.get("PYTHONHASHSEED") != PIN:
        print(f"run with PYTHONHASHSEED={PIN}")
        return 2
    total = 0
    failures = 0

    def note(ok: bool, label: str, detail: str = "") -> None:
        nonlocal total, failures
        total += 1
        if ok:
            print(f"pass {label}")
        else:
            failures += 1
            print(f"FAIL {label}\n{detail}")

    with tempfile.TemporaryDirectory() as tmp:
        flipped: dict[str, str] = {}
        for name in FLIP_TO_FAIL + STAY_GREEN + ["overcost.thorn"]:
            with open(os.path.join(ROOT, "corpus", name), encoding="utf-8") as fh:
                lines = fh.read().splitlines(keepends=True)
            if not lines or SEAL_RE.match(lines[0].strip()) is None:
                note(False, f"flip {name}", "first line is not a seal")
                continue
            lines[0] = "api v0.2\n"
            dest = os.path.join(tmp, name)
            with open(dest, "w", encoding="utf-8") as fh:
                fh.writelines(lines)
            flipped[name] = dest
        for name in FLIP_TO_FAIL:
            if name not in flipped:
                continue
            proc = invoke(["build", flipped[name]], cwd=tmp)
            note(
                proc.returncode != 0 and "W-CONTRACT-01" in proc.stdout,
                f"v0.2 fail {name}",
                proc.stdout + proc.stderr,
            )
        for name in STAY_GREEN:
            if name not in flipped:
                continue
            proc = invoke(["build", flipped[name]], cwd=tmp)
            note(
                proc.returncode == 0
                and "ok" in proc.stdout
                and "W-CONTRACT-01" not in proc.stdout
                and "W-TERM-01" not in proc.stdout,
                f"v0.2 green {name}",
                proc.stdout + proc.stderr,
            )
        if "overcost.thorn" in flipped:
            proc = invoke(["build", flipped["overcost.thorn"]], cwd=tmp)
            note(proc.returncode != 0, "v0.2 overcost.thorn", proc.stdout + proc.stderr)
    proc = invoke(["build", os.path.join(ROOT, "corpus/bad-seal-unknown.thorn")], cwd=ROOT)
    note(
        proc.returncode != 0 and "unsupported seal" in proc.stdout and "E-" not in proc.stdout,
        "unknown seal bad-seal-unknown.thorn",
        proc.stdout + proc.stderr,
    )

    print(f"{total}/{total} passed" if not failures else f"{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
