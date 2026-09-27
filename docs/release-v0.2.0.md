# THORN Release v0.2.0

- Version: 0.2.0
- Date: 2026-09-27
- Tag: `v0.2.0`, created on release day after content review. The tag name
  is the release identifier; a file cannot contain the hash of the commit
  containing it, so the hash is resolved with `git rev-parse v0.2.0` and
  reported alongside, never inside, this note.
- First users: deterministic firmware-validation teams (HIL and CI-gated
  test scripting), per signed positioning. Nothing in this release targets
  any other group.

## Verification

Ten runners, all green on Linux x86-64 with `PYTHONHASHSEED=0`:

| Runner | Result |
| ------ | ------ |
| tests/run_m1.py | 7/7 passed |
| tests/run_m2.py | 14/14 passed |
| tests/run_m3.py | 22/22 passed |
| tests/run_m4.py | 33/33 passed |
| tests/run_m5.py | 13/13 passed |
| tests/run_m6.py | 16/16 passed |
| tests/run_v2m1.py | 38/38 passed |
| tests/run_v2m2.py | 43/43 passed |
| tests/run_v2m3.py | 53/53 passed |
| tests/run_adv.py | 6/6 passed, fuzz 1500 examined clean seed 424242 |

Provenance of every number above is Linux x86-64 only. Any claim beyond
that platform is specification, not evidence.

## Deliberately out of scope

No native code generation or LLVM, no C compatibility or C ABI, no network
surface, no registry or server (pins and manifests only), no second
implementation (one interpreter plus one suite), no standard-catalog growth
beyond the six names without signed demand, no floating version ranges,
no division or modulo operators, no transitive imports, no static prover
(contracts are recorded and test-enforced), no multi-unit builds.

## Known gaps with verdicts

- `E-TASK-01`: dead registry entry with no producer. Needs a producer
  decision post-release.
- `E-REGION-01`, `E-CHAN-01`, `W-TERM-01`: producers exist, no corpus
  trigger. Accepted as coverage debt; each needs one targeted file
  post-release.
- `Foreign.C` without a marker is unenforced: no runtime path reaches it,
  so it fails closed rather than silently wrong. Tracked for the new
  roadmap, not a rule at this milestone.
- Entry behaviors with parameters fail; parameters exist only for callees.
- Arithmetic is U64-only with dynamic range checks; cross-width conversion
  does not exist. The `copy` form is undefined. Fold bounds stay
  literal-or-name. Behavior calls nest to 64 levels and block nesting to 64
  levels; deeper nesting fails without a code. Step budget bounds every run.
