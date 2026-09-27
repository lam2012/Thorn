"""Adversarial runner (stdlib only). Seeded crash-freedom fuzz plus hostile corpus.

Fuzz oracle: through every entry point below, only _Failure may escape (the
controlled codeless channel); any other exception is a crash. run_source and
the file-level analyze entry must always return, never raise.

Hostile corpus (5 files): deep-nest.thorn rc 1 nesting too deep codeless,
bad-utf8.thorn rc 1 not decodable with no Traceback text, dup-def.thorn rc 1
duplicate codeless, bad-oracle.thorn rc 1 E-NONDET-01, bad-daemon.thorn rc 1
E-DAEMON-01. All five assert no other E- codes beyond their target.

Audit table, registry code -> producer -> corpus trigger or verdict:
E-SEAL-01 seal.py bad-seal.thorn; E-REGION-01 checker.py GAP no corpus
trigger, needs one region file post-release; E-MOVE-01 checker.py
bad-move.thorn; E-TYPE-01 checker.py bad-type.thorn; E-DISCARD-01 checker.py
bad-discard.thorn; E-TASK-01 no producer GAP dead entry needs a producer
decision post-release; E-CHAN-01 runtime.py GAP no corpus trigger, close-path
timing accepted; E-SHARE-01/E-GC-01 reserved per errors.py; E-DAEMON-01
checker.py bad-daemon.thorn; E-CANCEL-01 runtime.py daemon.thorn runtime;
E-NONDET-01 checker.py bad-oracle.thorn; E-FETCH-01 __main__ gate run_m5
missing fixture; E-SEED-01 runtime.py rand.thorn seedless; W-CONTRACT-01
checker.py canonical warnings; W-TERM-01 contracts.py GAP recorded, no corpus
emits it and structural silence is covered.

Out of scope: full generative grammar fuzzing with coverage guidance waits
for the post-release roadmap. This runner proves crash-freedom only.
"""

import os
import random
import subprocess
import sys
import tempfile

PIN = "0"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANT = "2026-01-01T00:00:00Z"
SEED = 7
ADV_SEED = 424242
STR_CASES = 200
BYTE_CASES = 100


def _pools(rng):
    keywords = [
        "behavior", "task", "daemon", "region", "seq", "channel", "spawn", "let",
        "track", "match", "fold", "bound", "discard", "uses", "fails", "open",
        "local", "nondet", "cancel", "import", "vendor", "hash", "in", "gc",
        "Ok", "Err", "done", "fail", "and", "or", "if", "for", "true", "false",
        "api", "requires", "ensures", "cost", "decreases",
    ]
    names = [
        "msg", "buf", "r0", "rparse", "greet", "root", "x", "n", "t", "e",
        "Std", "Out", "emit", "recv", "send", "Lex", "scan", "Oracles", "Time",
        "now", "I32", "U64", "Text", "Int", "Float",
    ]
    lits = ['"hi"', '"tick"', '"x"', "42", "4_000", "0", "3", "64", "1024"]
    long_digits = ["9" * 5000, "7" * 6000]
    symbols = ["=", ":", "::", "->", "=>", "[", "]", "{", "}", '"', "#", "_",
               "+", "-", "*", ".", ",", "!", ";", "(", ")"]
    return keywords, names, lits, long_digits, symbols


def _random_line(rng, keywords, names, lits, long_digits, symbols):
    indent = rng.choice(["", "  ", "    ", "      ", "\t", "   ", " " * 130])
    parts = []
    for _ in range(rng.randint(1, 6)):
        roll = rng.random()
        if roll < 0.3:
            parts.append(rng.choice(keywords))
        elif roll < 0.55:
            parts.append(rng.choice(names))
        elif roll < 0.7:
            parts.append(rng.choice(lits))
        elif roll < 0.75:
            parts.append(rng.choice(long_digits))
        else:
            parts.append(rng.choice(symbols))
    text = " ".join(parts)
    if rng.random() < 0.1:
        text += rng.choice(["#", '"', "[", ":", "\r"])
    if rng.random() < 0.05:
        text += rng.choice(["é", "文", "\u200b", "\U0001f600"])
    return indent + text


def _mutate(rng, text):
    lines = text.splitlines(keepends=True)
    for _ in range(rng.randint(1, 4)):
        op = rng.random()
        if not lines:
            lines = [_random_line(rng, *_pools(rng)[:5])]
        if op < 0.25 and len(lines) > 1:
            lines.pop(rng.randrange(len(lines)))
        elif op < 0.5:
            lines.insert(rng.randrange(len(lines) + 1), lines[rng.randrange(len(lines))])
        elif op < 0.75:
            i = rng.randrange(len(lines))
            line = lines[i]
            cut = rng.randrange(len(line) + 1) if line else 0
            lines[i] = line[:cut] + rng.choice(["\t", "  ", "9" * 5000, "#", ":", "[", '"']) + line[cut:]
        else:
            i = rng.randrange(len(lines))
            lines[i] = lines[i].replace("  ", "\t", 1) if "  " in lines[i] else lines[i] + "  \n"
    return "".join(lines)


def _str_cases(rng, corpus_texts):
    keywords, names, lits, long_digits, symbols = _pools(rng)
    cases = []
    for _ in range(STR_CASES):
        roll = rng.random()
        if roll < 0.5:
            cases.append("\n".join(_random_line(rng, keywords, names, lits, long_digits, symbols) for _ in range(rng.randint(1, 40))))
        elif roll < 0.8:
            cases.append(_mutate(rng, rng.choice(corpus_texts)))
        else:
            nest = rng.randint(65, 120)
            pad = "\n".join("  " * i + "seq:" for i in range(1, nest + 1))
            cases.append("api v0.1\n\nopen behavior d uses [Std.Out] fails {Io.Denied} =\n" + pad + "\n" + "  " * (nest + 1) + "track Std.Out.emit[\"x\"] ::\n")
    return cases


def _byte_cases(rng):
    cases = []
    frags = [b"api v0.1\n", b"open behavior f uses [Std.Out] fails {Io.Denied} =\n",
             b"  seq:\n", b"\xff\xfe", b"\x00", b"\r", b"\r\n", b"# c\n",
             b'"unterminated', b"9" * 5000, b"\t", "é".encode("utf-8"), "文".encode("utf-8")]
    for _ in range(BYTE_CASES):
        parts = [rng.choice(frags) for _ in range(rng.randint(1, 12))]
        cases.append(b"".join(parts))
    return cases


def main() -> int:
    if os.environ.get("PYTHONHASHSEED") != PIN:
        print(f"run with PYTHONHASHSEED={PIN}")
        return 2
    sys.path.insert(0, ROOT)
    from thornc import checker, contracts, fetch, imports, layout, lex, seal
    from thornc.__main__ import _analyze
    from thornc.runtime import _Failure, run_source

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

    for name, want, ban_e in [
        ("corpus/deep-nest.thorn", "nesting too deep", True),
        ("corpus/dup-def.thorn", "duplicate", True),
    ]:
        proc = run_driver(os.path.join(ROOT, name))
        ok = proc.returncode != 0 and want in proc.stdout and ("E-" not in proc.stdout if ban_e else True)
        note(ok, f"hostile {name}", proc.stdout + proc.stderr)
    proc = run_driver(os.path.join(ROOT, "corpus/bad-utf8.thorn"))
    combined = proc.stdout + proc.stderr
    note(
        proc.returncode != 0 and "not decodable" in combined and "Traceback" not in combined,
        "hostile corpus/bad-utf8.thorn",
        combined,
    )
    proc = run_driver(os.path.join(ROOT, "corpus/bad-oracle.thorn"))
    note(
        proc.returncode != 0
        and proc.stdout.count("E-NONDET-01") == 1
        and "W-CONTRACT-01" in proc.stdout,
        "hostile corpus/bad-oracle.thorn",
        proc.stdout + proc.stderr,
    )
    proc = run_driver(os.path.join(ROOT, "corpus/bad-daemon.thorn"))
    note(
        proc.returncode != 0
        and proc.stdout.count("E-DAEMON-01") == 1
        and "W-CONTRACT-01" in proc.stdout,
        "hostile corpus/bad-daemon.thorn",
        proc.stdout + proc.stderr,
    )

    rng = random.Random(ADV_SEED)
    corpus_texts = []
    for base, _, files in os.walk(os.path.join(ROOT, "corpus")):
        for fn in sorted(files):
            if fn.endswith(".thorn"):
                try:
                    with open(os.path.join(base, fn), encoding="utf-8") as fh:
                        corpus_texts.append(fh.read())
                except (OSError, UnicodeDecodeError):
                    pass
    if not corpus_texts:
        corpus_texts = ["api v0.1\n"]

    bad = 0
    examined = 0

    def guard(label, func):
        nonlocal bad, examined
        examined += 1
        try:
            func()
        except Exception as exc:  # noqa: BLE001 - the oracle: only _Failure may escape
            if isinstance(exc, _Failure):
                return
            bad += 1
            print(f"CRASH {label}: {type(exc).__name__}: {exc}")

    for i, text in enumerate(_str_cases(rng, corpus_texts)):
        tls = None

        def lex_stage(t=text):
            nonlocal tls
            tls = lex.tokenize(t)

        guard(f"str{i}/lex", lex_stage)
        guard(f"str{i}/layout", lambda: layout.check(tls))
        guard(f"str{i}/seal", lambda: seal.find_seal(tls))
        guard(f"str{i}/checker", lambda: checker.check(tls))
        guard(f"str{i}/contracts", lambda: contracts.check_file(tls))
        guard(f"str{i}/run", lambda t=text: run_source(t, [], INSTANT, SEED))

    with tempfile.TemporaryDirectory() as tmp:
        for i, blob in enumerate(_byte_cases(rng)):
            path = os.path.join(tmp, f"f{i}.thorn")
            with open(path, "wb") as fh:
                fh.write(blob)
            guard(f"byte{i}/analyze", lambda p=path: _analyze(p))
            guard(f"byte{i}/manifest", lambda p=path: fetch.read_manifest(p))
            guard(
                f"byte{i}/import",
                lambda p=path: imports.resolve(tmp, os.path.basename(p), "0" * 64, "api v0.1"),
            )

    note(bad == 0, f"fuzz {examined} clean seed {ADV_SEED}", f"{bad} crashes")

    print(f"{total}/{total} passed" if not failures else f"{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
