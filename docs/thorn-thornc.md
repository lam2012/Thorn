# THORN Toolchain v0.1 (thornc)

## Overview

`thornc` enforces the version seal defined in the v0.1 core. The same sources produce the same result. The toolchain is offline by default and never fetches implicitly. Three commands form the v0.1 gate: `build`, `test`, and `fetch`. A fourth helper, `version`, reports seal support without changing any gate.

## Rules

### 1. Seal is checked first

- Every source file opens with a seal line such as `api v0.1`.
- A build with mixed seals must declare the mix explicitly. An undeclared mix is error `E-SEAL-01`.
- Check order is fixed: seal, then `uses` and `fails`, then bound and cost, then cancel token. A seal failure stops the run early.
- Bumping a seal can promote warnings. Moving from `api v0.1` to `api v0.2` turns `W-CONTRACT-01` and `W-TERM-01` from warnings into errors.

### 2. Build replays without implicit fetch

- `thornc build` replays the sealed sources. The same file set and seal produce the same output.
- Network fetch during compilation without a declared fetch capability is error `E-FETCH-01`. A manifest-declared input absent at build time is also error `E-FETCH-01`.
- Any `E-*` diagnostic blocks the build. `W-CONTRACT-01` and `W-TERM-01` pass with their codes in v0.1 and block in v0.2.
- `build` never auto-fetches to fill a missing input. A missing declared input is an error, not a fetch trigger.

### 3. Test separates deterministic and sealed suites

- `thornc test` runs the deterministic suite by default with full replay.
- Calling a `nondet` behavior from a deterministic test context is error `E-NONDET-01`.
- Oracle suites using `Oracles.*` are allowed but physically separated from the deterministic suite. They share no setup with it.
- Each oracle test declares an explicit mock with a fixed seed and logs the seed for replay. A mock without a fixed seed is error `E-SEED-01`.
- Real clock, random, or environment reads inside any replayed test are errors. Sealed suites read only their declared mocks.

### 4. Fetch is declared, pinned, and logged

- `thornc fetch` is the only command that touches the network. The toolchain is offline unless this command runs with a declared manifest.
- The manifest is a file named `fetch.lock`. Its first line is the version marker `# thorn-fetch: 1`. Each entry line is `<hex sha256><two spaces><root-relative path>`. `#` lines are comments.
- A pin mismatch at fetch time is a codeless diagnostic naming the path. A declared input missing at build time is error `E-FETCH-01`.
- Every fetch entry is declared before use, pinned by content hash, and logged with seal, hash, and seed where applicable.
- `build` and `test` consume only fetched and pinned inputs. They never open new network connections.

### 5. Version helper is non-blocking

- `thornc version` prints the toolchain version, the supported seals, and the warning-to-error promotion table per seal.
- The helper changes no gate. It exists so a seal bump is visible before `build` runs.

## Examples

### Build with v0.1 warnings

```text
$ thornc build
seal: api v0.1 ok
W-CONTRACT-01: behavior greet missing cost (warning in v0.1)
build: ok with 1 warning
```

Warnings carry codes. The same command under `api v0.2` blocks on the same codes.

### Build rejected on mixed seals

```text
$ thornc build
E-SEAL-01: mixed api v0.1 and api v0.2 without declared mix
build: blocked
```

### Deterministic test pass

```text
$ thornc test
suite deterministic: 42 passed, replay ok
suite oracle: skipped (requires --suite oracle)
```

### Oracle suite with fixed seed

```text
$ thornc test --suite oracle
suite oracle: mock Oracles.Rand seed 7 logged, 5 passed, replay ok
```

A mock without a seed fails with `E-SEED-01` instead of running.

### Declared fetch

```text
$ thornc fetch
fetch: manifest 3 entries, hashes pinned, log written
$ thornc build
build: ok, no network used
```

## Errors

| Code | Condition | Severity in v0.1 |
|------|-----------|------------------|
| `E-SEAL-01` | Mixed or mismatched seals without explicit declaration | Error |
| `E-FETCH-01` | Network fetch during build or test without declared fetch capability | Error |
| `E-SEED-01` | Oracle mock without a fixed logged seed | Error |
| `E-NONDET-01` | Oracle use or `nondet` call inside a deterministic replay context | Error |
| `E-DAEMON-01` | `daemon` without `cancel` token | Error |
| `E-CANCEL-01` | Leaked daemon token at region exit | Error |
| `W-CONTRACT-01` | Missing `requires`, `ensures`, or `cost` | Warning in v0.1, error in v0.2 |
| `W-TERM-01` | Recursive behavior without proven `decreases` | Warning in v0.1, error in v0.2 |

## Non-goals

- No implicit fetch to repair a missing input.
- No floating latest-version resolution.
- No network access inside `build` or `test`.
- No shared setup between deterministic and oracle suites.
- No silent warning suppression without a code.
- No toolchain behavior that differs from the sealed core rules.
