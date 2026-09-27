"""M3 acceptance runner (stdlib only). Static regression plus runtime execution.

Expectations differ per stage for the same file, so they are recorded here:

Static (rc 0, "ok" in output): greet, pair, parse, daemon, stamp, cont,
cancel, bad-scan. Diagnostics expected: bad-seal E-SEAL-01, bad-move E-MOVE-01,
bad-type E-TYPE-01, bad-discard E-DISCARD-01, bad-tab/bad-visibility/bad-uses/
bad-nondet parse rejection without E- codes.

Runtime (in-process, fixtures below): pair out ["hello", "hello"] ok (greeter
emits, then logger re-emits the received text); parse with INPUTS ["hi there"]
ok; stamp with INSTANT ok; daemon E-CANCEL-01 rc 1; cancel out ["tick"] ok
(one tick before the owner cancels); bad-scan with INPUTS ["   "] err Lex.Bad
rc 0.

Fixtures: INPUTS per file for Std.In.read, INSTANT for Oracles.Time.now,
SEED for Oracles.Rand.next (unused by current corpus, pinned anyway).
"""

import os
import subprocess
import sys

PIN = "0"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANT = "2026-01-01T00:00:00Z"
SEED = 7

STATIC_OK = [
    "greet.thorn",
    "pair.thorn",
    "parse.thorn",
    "daemon.thorn",
    "stamp.thorn",
    "cont.thorn",
    "cancel.thorn",
    "bad-scan.thorn",
]
STATIC_CODE = {
    "bad-seal.thorn": "E-SEAL-01",
    "bad-move.thorn": "E-MOVE-01",
    "bad-type.thorn": "E-TYPE-01",
    "bad-discard.thorn": "E-DISCARD-01",
}
STATIC_REJECT = ["bad-tab.thorn", "bad-visibility.thorn", "bad-uses.thorn", "bad-nondet.thorn"]

RUNTIME_INPUTS = {
    "pair.thorn": [],
    "parse.thorn": ["hi there"],
    "stamp.thorn": [],
    "daemon.thorn": [],
    "cancel.thorn": [],
    "bad-scan.thorn": ["   "],
}


def run_driver(path: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = PIN
    return subprocess.run(
        [sys.executable, "-m", "thornc", "build", path],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def main() -> int:
    if os.environ.get("PYTHONHASHSEED") != PIN:
        print(f"run with PYTHONHASHSEED={PIN}")
        return 2
    sys.path.insert(0, ROOT)
    from thornc.runtime import run_source

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

    for name in STATIC_OK:
        proc = run_driver(os.path.join(ROOT, "corpus", name))
        note(proc.returncode == 0 and "ok" in proc.stdout, f"static {name}", proc.stdout + proc.stderr)
    for name, code in STATIC_CODE.items():
        proc = run_driver(os.path.join(ROOT, "corpus", name))
        note(proc.returncode != 0 and code in proc.stdout, f"static {name}", proc.stdout + proc.stderr)
    for name in STATIC_REJECT:
        proc = run_driver(os.path.join(ROOT, "corpus", name))
        note(
            proc.returncode != 0 and "parse error" in proc.stdout and "E-" not in proc.stdout,
            f"static {name}",
            proc.stdout + proc.stderr,
        )

    def run_case(name: str) -> tuple:
        with open(os.path.join(ROOT, "corpus", name), encoding="utf-8") as fh:
            return run_source(fh.read(), RUNTIME_INPUTS[name], INSTANT, SEED)

    rc, out, outcome, diags = run_case("pair.thorn")
    note(rc == 0 and out == ["hello", "hello"] and outcome == ("ok", None), "run pair.thorn", f"{rc} {out} {outcome}")

    rc, out, outcome, diags = run_case("parse.thorn")
    note(rc == 0 and out == [] and outcome == ("ok", None), "run parse.thorn", f"{rc} {out} {outcome}")

    rc, out, outcome, diags = run_case("stamp.thorn")
    note(rc == 0 and outcome == ("ok", None), "run stamp.thorn", f"{rc} {out} {outcome}")

    rc, out, outcome, diags = run_case("daemon.thorn")
    rendered = " ".join(d.render() for d in diags)
    note(rc == 1 and "E-CANCEL-01" in rendered, "run daemon.thorn", f"{rc} {rendered}")

    rc, out, outcome, diags = run_case("cancel.thorn")
    note(rc == 0 and out == ["tick"] and outcome == ("ok", None), "run cancel.thorn", f"{rc} {out} {outcome}")

    rc, out, outcome, diags = run_case("bad-scan.thorn")
    note(rc == 0 and outcome == ("err", "Lex.Bad"), "run bad-scan.thorn", f"{rc} {out} {outcome}")

    print(f"{total}/{total} passed" if not failures else f"{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
