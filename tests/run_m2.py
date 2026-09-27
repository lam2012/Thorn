"""M2 acceptance runner (stdlib only). Reruns the M1 corpus, then the M2 cases."""

import os
import subprocess
import sys

PIN = "0"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OK_CASES = ["greet.thorn", "pair.thorn", "parse.thorn", "daemon.thorn", "stamp.thorn", "cont.thorn"]
CODE_CASES = {
    "bad-seal.thorn": "E-SEAL-01",
    "bad-move.thorn": "E-MOVE-01",
    "bad-type.thorn": "E-TYPE-01",
    "bad-discard.thorn": "E-DISCARD-01",
}
REJECT_CASES = ["bad-tab.thorn", "bad-visibility.thorn", "bad-uses.thorn", "bad-nondet.thorn"]


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
    total = 0
    failures = 0
    for name in OK_CASES:
        total += 1
        proc = run_driver(os.path.join(ROOT, "corpus", name))
        if proc.returncode == 0 and "ok" in proc.stdout:
            print(f"pass {name}")
        else:
            failures += 1
            print(f"FAIL {name}\n{proc.stdout}{proc.stderr}")
    for name, code in CODE_CASES.items():
        total += 1
        proc = run_driver(os.path.join(ROOT, "corpus", name))
        if proc.returncode != 0 and code in proc.stdout:
            print(f"pass {name}")
        else:
            failures += 1
            print(f"FAIL {name}\n{proc.stdout}{proc.stderr}")
    for name in REJECT_CASES:
        total += 1
        proc = run_driver(os.path.join(ROOT, "corpus", name))
        if proc.returncode != 0 and "parse error" in proc.stdout and "E-" not in proc.stdout:
            print(f"pass {name}")
        else:
            failures += 1
            print(f"FAIL {name}\n{proc.stdout}{proc.stderr}")
    print(f"{total}/{total} passed" if not failures else f"{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
