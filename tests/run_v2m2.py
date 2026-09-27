"""V2-M2 vendor-import runner (stdlib only). Static regression plus import runs.

Decomposition, 43 assertions: static 29 (prior 25: 14 STATIC_OK plus
recurse-noW-TERM plus 4 CODE plus 4 REJECT plus overcost plus bad-call; new
import.thorn rc 0, bad-import-hash.thorn rc 1 hash mismatch, bad-import-seal
rc 1 seal mismatch, bad-transitive.thorn rc 1 transitive ban, all codeless
with no E- codes), runtime 13 (prior 12 plus import.thorn out
["hi from vendor"] ok with corpus path passed for resolution), inline depth
cap 1 (unchanged). Old corpus expectations are identical across stages.
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
    "fold.thorn",
    "contract.thorn",
    "recurse.thorn",
    "bad-ensures.thorn",
    "foldname.thorn",
    "call.thorn",
    "import.thorn",
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
    "fold.thorn": [],
    "contract.thorn": [],
    "bad-ensures.thorn": [],
    "foldname.thorn": [],
    "call.thorn": [],
    "recurse.thorn": [],
    "import.thorn": [],
}

DEPTH_SOURCE = """api v0.1

open behavior loop uses [Std.Out] fails {Io.Denied} requires true ensures true cost {mem <= 4k} =
  seq:
    region r0:
      track loop[] ::
        Ok _ -> done
        Err e -> fail e
"""


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
    proc = run_driver(os.path.join(ROOT, "corpus", "recurse.thorn"))
    if "W-TERM-01" in proc.stdout:
        total += 1
        failures += 1
        print(f"FAIL static recurse.thorn W-TERM\n{proc.stdout}")
    else:
        total += 1
        print("pass static recurse.thorn no-W-TERM")
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
    proc = run_driver(os.path.join(ROOT, "corpus", "overcost.thorn"))
    note(
        proc.returncode != 0 and "fold bound" in proc.stdout and "E-" not in proc.stdout,
        "static overcost.thorn",
        proc.stdout + proc.stderr,
    )
    proc = run_driver(os.path.join(ROOT, "corpus", "bad-call.thorn"))
    note(
        proc.returncode != 0 and "uses" in proc.stdout and "E-" not in proc.stdout,
        "static bad-call.thorn",
        proc.stdout + proc.stderr,
    )
    proc = run_driver(os.path.join(ROOT, "corpus", "bad-import-hash.thorn"))
    note(
        proc.returncode != 0 and "hash mismatch" in proc.stdout and "E-" not in proc.stdout,
        "static bad-import-hash.thorn",
        proc.stdout + proc.stderr,
    )
    proc = run_driver(os.path.join(ROOT, "corpus", "bad-import-seal.thorn"))
    note(
        proc.returncode != 0 and "seal mismatch" in proc.stdout and "E-" not in proc.stdout,
        "static bad-import-seal.thorn",
        proc.stdout + proc.stderr,
    )
    proc = run_driver(os.path.join(ROOT, "corpus", "bad-transitive.thorn"))
    note(
        proc.returncode != 0 and "transitive" in proc.stdout and "E-" not in proc.stdout,
        "static bad-transitive.thorn",
        proc.stdout + proc.stderr,
    )

    def run_case(name: str) -> tuple:
        path = os.path.join(ROOT, "corpus", name)
        with open(path, encoding="utf-8") as fh:
            return run_source(fh.read(), RUNTIME_INPUTS[name], INSTANT, SEED, path)

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

    rc, out, outcome, diags = run_case("fold.thorn")
    note(
        rc == 0 and out == ["tick", "tick", "tick"] and outcome == ("ok", None),
        "run fold.thorn",
        f"{rc} {out} {outcome}",
    )

    rc, out, outcome, diags = run_case("contract.thorn")
    note(rc == 0 and out == ["hi"] and outcome == ("ok", None), "run contract.thorn", f"{rc} {out} {outcome}")

    rc, out, outcome, diags = run_case("bad-ensures.thorn")
    rendered = " ".join(d.render() for d in diags)
    note(rc == 1 and "ensures violated" in rendered, "run bad-ensures.thorn", f"{rc} {rendered}")

    rc, out, outcome, diags = run_case("foldname.thorn")
    note(
        rc == 0 and out == ["tick", "tick", "tick"] and outcome == ("ok", None),
        "run foldname.thorn",
        f"{rc} {out} {outcome}",
    )

    rc, out, outcome, diags = run_case("call.thorn")
    note(rc == 0 and out == ["hi"] and outcome == ("ok", None), "run call.thorn", f"{rc} {out} {outcome}")

    rc, out, outcome, diags = run_case("recurse.thorn")
    rendered = " ".join(d.render() for d in diags)
    note(rc == 1 and "unbound name" in rendered, "run recurse.thorn", f"{rc} {rendered}")

    rc, out, outcome, diags = run_case("import.thorn")
    note(rc == 0 and out == ["hi from vendor"] and outcome == ("ok", None), "run import.thorn", f"{rc} {out} {outcome}")

    rc, out, outcome, diags = run_source(DEPTH_SOURCE, [], INSTANT, SEED)
    rendered = " ".join(d.render() for d in diags)
    note(rc == 1 and "call depth exceeded" in rendered, "run inline depth cap", f"{rc} {rendered}")

    print(f"{total}/{total} passed" if not failures else f"{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
