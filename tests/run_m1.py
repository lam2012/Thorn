"""M1 acceptance runner (stdlib only). Spawns the driver with a pinned hash seed."""

import os
import subprocess
import sys

PIN = "0"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OK_CASES = ["greet.thorn", "pair.thorn", "parse.thorn", "daemon.thorn", "stamp.thorn"]


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
    failures = 0
    for name in OK_CASES:
        proc = run_driver(os.path.join(ROOT, "corpus", name))
        if proc.returncode == 0 and "ok" in proc.stdout:
            print(f"pass {name}")
        else:
            failures += 1
            print(f"FAIL {name}\n{proc.stdout}{proc.stderr}")
    proc = run_driver(os.path.join(ROOT, "corpus", "bad-seal.thorn"))
    if proc.returncode != 0 and "E-SEAL-01" in proc.stdout:
        print("pass bad-seal.thorn")
    else:
        failures += 1
        print(f"FAIL bad-seal.thorn\n{proc.stdout}{proc.stderr}")
    proc = run_driver(os.path.join(ROOT, "corpus", "bad-tab.thorn"))
    if proc.returncode != 0 and "parse error" in proc.stdout:
        print("pass bad-tab.thorn")
    else:
        failures += 1
        print(f"FAIL bad-tab.thorn\n{proc.stdout}{proc.stderr}")
    print("7/7 passed" if not failures else f"{7 - failures}/7 passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
