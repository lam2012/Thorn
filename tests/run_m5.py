"""M5 CLI-surface runner (stdlib only). build/test/fetch/version plus retirement proof.

Static and runtime corpora stay owned by run_m1..run_m4 (totals 7/14/22/33
unchanged); this runner only covers the M5 command surface:

build: greet.thorn rc 0, bad-seal.thorn E-SEAL-01.
version: prints thornc 0.1.0, api v0.1 seals, promotion table.
fetch: ok/ verified, tampered pin mismatch codeless, missing input codeless.
build with manifest: missing declared input is E-FETCH-01.
rand.thorn: static rc 0; runtime seed 7 ok; runtime seed None E-SEED-01 rc 1.
test: aggregator over run_m1..run_m4 rc 0.
usage: unknown verb rc 2, retired check verb rc 2 with usage text.
"""

import os
import subprocess
import sys

PIN = "0"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANT = "2026-01-01T00:00:00Z"
SEED = 7


def invoke(args: list[str], cwd: str = ROOT) -> subprocess.CompletedProcess[str]:
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

    proc = invoke(["build", "corpus/greet.thorn"])
    note(proc.returncode == 0 and "ok" in proc.stdout, "build greet.thorn", proc.stdout + proc.stderr)

    proc = invoke(["build", "corpus/bad-seal.thorn"])
    note(proc.returncode != 0 and "E-SEAL-01" in proc.stdout, "build bad-seal.thorn", proc.stdout + proc.stderr)

    proc = invoke(["version"])
    note(
        proc.returncode == 0
        and "thornc 0.1.0" in proc.stdout
        and "api v0.1" in proc.stdout
        and "W-CONTRACT-01" in proc.stdout,
        "version",
        proc.stdout + proc.stderr,
    )

    proc = invoke(["fetch", "fetch.lock"], cwd=os.path.join(ROOT, "tests/fetch/ok"))
    note(proc.returncode == 0 and "verified" in proc.stdout, "fetch ok", proc.stdout + proc.stderr)

    proc = invoke(["fetch"], cwd=os.path.join(ROOT, "tests/fetch/tampered"))
    note(
        proc.returncode != 0 and "pin mismatch" in proc.stdout and "E-" not in proc.stdout,
        "fetch tampered",
        proc.stdout + proc.stderr,
    )

    proc = invoke(["fetch"], cwd=os.path.join(ROOT, "tests/fetch/missing"))
    note(
        proc.returncode != 0 and "missing input" in proc.stdout and "E-" not in proc.stdout,
        "fetch missing",
        proc.stdout + proc.stderr,
    )

    proc = invoke(
        ["build", os.path.join(ROOT, "corpus/greet.thorn")],
        cwd=os.path.join(ROOT, "tests/fetch/missing"),
    )
    note(proc.returncode != 0 and "E-FETCH-01" in proc.stdout, "build missing input", proc.stdout + proc.stderr)

    proc = invoke(["build", "corpus/rand.thorn"])
    note(proc.returncode == 0 and "ok" in proc.stdout, "static rand.thorn", proc.stdout + proc.stderr)

    with open(os.path.join(ROOT, "corpus/rand.thorn"), encoding="utf-8") as fh:
        rand_src = fh.read()
    rc, out, outcome, diags = run_source(rand_src, [], INSTANT, SEED)
    note(rc == 0 and outcome == ("ok", None), "run rand.thorn seeded", f"{rc} {out} {outcome}")
    rc, out, outcome, diags = run_source(rand_src, [], INSTANT, None)
    rendered = " ".join(d.render() for d in diags)
    note(rc == 1 and "E-SEED-01" in rendered, "run rand.thorn seedless", f"{rc} {rendered}")

    proc = invoke(["test"])
    note(proc.returncode == 0 and "ok" in proc.stdout, "test aggregator", proc.stdout + proc.stderr)

    proc = invoke(["frobnicate"])
    note(proc.returncode == 2 and "usage" in proc.stdout, "usage unknown verb", proc.stdout + proc.stderr)

    proc = invoke(["check", "corpus/greet.thorn"])
    note(proc.returncode == 2 and "usage" in proc.stdout, "usage retired check", proc.stdout + proc.stderr)

    print(f"{total}/{total} passed" if not failures else f"{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
