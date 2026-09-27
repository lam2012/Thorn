# THORN Build Roadmap (v0.1)

## Overview

Implementation is interpreter-first on a single host: Python 3 with the standard library only and no third-party dependencies, so every milestone stays offline and reproducible. One thin driver grows across milestones instead of per-milestone harnesses. Each milestone is accepted by running canonical examples with deterministic replay. Static proof, native code generation, and multi-unit builds are out of scope.

## Rules

### M0. Host and driver seed

- Host language is Python 3 using only the standard library. No third-party packages are permitted in the v0.1 toolchain.
- The driver pins `PYTHONHASHSEED` to a fixed value and forbids any logic that depends on traversal order of hash-ordered views such as `set`. Replay acceptance must pass under the pin; otherwise M3 replay results prove nothing.
- M1 ships a thin driver, `thornc check`, that parses layout and verifies the seal. Every later milestone extends this same driver, so acceptance always runs through one vehicle.

### M1. Layout, seal, and lexical acceptance

- The driver parses 2-space indentation, rejects tabs, checks the first-line `api vX` seal, and recognizes the `=` / `:` / `::` shapes, identifiers, literals, and `#` comments.
- Acceptance: every canonical example from the syntax document checks clean, and an undeclared mixed-seal pair reports `E-SEAL-01`.
- `check` is a temporary driver verb that folds into `build` at M5. The final command surface stays exactly `build`, `test`, `fetch`, and `version`.
- Example:
  ```text
  $ thornc check greet.thorn
  seal: api v0.1 ok
  layout: ok
  ```

### M2. Static checks: regions, seals, and contracts presence

- The checker enforces explicit regions with move-only ownership, mandatory visibility markers, upward seal propagation for `shared`, `nondet`, and `daemon`, and mandatory `uses` plus `fails` on every behavior and daemon.
- Bare numerics report `E-TYPE-01`. Unused expressions without `discard` report `E-DISCARD-01`. Missing `requires`, `ensures`, or `cost` records warning `W-CONTRACT-01`.
- Acceptance: a negative corpus where each violation yields its expected code, and every canonical example checks clean.

### M3. Runtime: tasks, channels, daemons on one logical thread

- The runtime grows the task tree through `spawn`, moves values across channels by `isolate -> move -> adopt`, tracks cancel tokens, and retires daemons on cancel.
- Scheduling observes only `track` points and channel operations. Channel rendezvous makes the canonical greeter/logger pair deterministic: the logger blocks on receive until the greeter sends.
- A daemon without a token reports `E-DAEMON-01`. A token leaked at region exit reports `E-CANCEL-01`. There is no `while(true)` and no orphan background task.
- Acceptance: the task pair emits exactly its sent text with replay ok, the ticker daemon emits then cancels before region exit, and the negative corpus yields the expected daemon and channel codes.
- `run` is a temporary driver verb that folds into `build` at M5. The final command surface stays unchanged.
- Example:
  ```text
  $ thornc run pair.thorn
  out: hello
  replay: ok
  ```

### M4. Contracts to tests plus the seeded oracle suite

- Written `requires` clauses are assumed and `ensures` clauses are asserted by generated deterministic checks. `cost` bounds are verified against `fold` bounds at build time, and overruns fail the test run.
- Structural recursion is accepted statically. An unproven `decreases` records warning `W-TERM-01`.
- The oracle suite runs physically separated from the deterministic suite with declared mocks: fixed instants for `Oracles.Time` and fixed seeds for `Oracles.Rand`, each logged for replay. A mock without a fixed logged seed reports `E-SEED-01`. Real clock and entropy reads during replay are errors.
- Acceptance: the full corpus passes, the oracle suite logs its seeds with replay ok, and the negative corpus yields the expected seed and nondeterminism codes.
- Example:
  ```text
  $ thornc test --suite oracle
  suite oracle: mock Oracles.Rand seed 7 logged, 5 passed, replay ok
  ```

### M5. Full command surface on the corpus

- The driver grows into the complete surface from the toolchain document: `build` replays without implicit fetch, `test` separates deterministic and oracle suites, `fetch` runs offline by default with declared manifests pinned by content hash, and `version` reports seals plus the warning-to-error table without changing gates.
- Acceptance: the full corpus builds, tests, and replays with no network used, and a declared fetch round-trips through pinned hashes.

### M6. v0.2 promotion rehearsal, tracked but out of v0.1 scope

- M6 flips the corpus seals from `api v0.1` to `api v0.2` and reruns everything with `W-CONTRACT-01` and `W-TERM-01` as errors.
- M6 is tracked follow-up work, not part of the v0.1 build. It exists so the promotion promise has an owner and a rerun procedure instead of dangling.

## Examples

### Milestone vehicle growth

```text
M1  thornc check   parse + seal on canonical examples
M2  thornc check   static diagnostics on negative corpus
M3  thornc run     task pair + daemon lifecycle
M4  thornc test    generated checks + seeded oracle suite
M5  thornc         full build/test/fetch/version on corpus
M6  thornc         v0.2 seal rerun with warnings as errors
```

## Errors

Milestone acceptance reuses existing diagnostics and adds no new codes. Layout and seal breaches report through the syntax and seal diagnostics. Static breaches report the core registry. Runtime breaches report the daemon, cancel, channel, and nondeterminism codes. Seedless mocks report `E-SEED-01`. The canonical registry stays in the v0.1 core.

## Non-goals

- No LLVM, no native code generation, and no optimizer work in v0.1.
- No static prover in v0.1. Contracts are recorded and test-enforced.
- No multi-unit builds and no import machinery in v0.1.
- No scheduler parallelism. The runtime is a single logical thread.
- No third-party host dependencies and no network inside `build` or `test`.
- No new diagnostics in this roadmap. Breaches reuse the existing registry.
