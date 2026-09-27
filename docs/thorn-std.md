# THORN Standard Catalog (v0.1)

## Overview

The v0.1 closed world contains exactly six language-level names: `Std.Out`, `Std.In`, `Lex.scan`, `Oracles.Time`, `Oracles.Rand`, and `Foreign.C`. Every canonical example refers only to these names. Each entry below documents its operations in declaration-site syntax, its `fails` set, its required seal, and a call in correct form. Channel operations such as `msg.send` and `msg.recv` are per-channel capabilities and are not catalog entries. Network fetch configuration is toolchain-level manifest data described in the `thornc` document, not a seventh language capability.

## Rules

### 1. `Std.Out` — ordered text emission

- Operation: `emit` with signature `emit[msg: Text in r]`, declared as `track Std.Out.emit[msg] ::` returning `Outcome`.
- Callers declare `uses [Std.Out]` and `fails {Io.Denied}`.
- No seal beyond the normal deterministic context. Emission order follows the enclosing `seq:` block.
- Example:
  ```text
  track Std.Out.emit[msg] ::
    Ok _ -> done
    Err e -> fail e
  ```

### 2. `Std.In` — tracked text intake

- Operation: `read` with signature `read[]`, declared as `track Std.In.read[] ::` returning `Outcome` carrying the buffer.
- Callers declare `uses [Std.In]` and a read `fails` set such as `{Io.Denied}`.
- The buffer is adopted into the caller's region on `Ok`. A direct unread binding without `track` is a contract violation.
- Example:
  ```text
  track Std.In.read[] ::
    Ok buf -> track Lex.scan[buf] ::
      Ok tok -> done
      Err e -> fail e
    Err e -> fail e
  ```

### 3. `Lex.scan` — lexical analysis with its own failure set

- Operation: `scan` with signature `scan[buf: Text in r]`, declared as `track Lex.scan[buf] ::` returning `Outcome` carrying the token list.
- `Lex.scan` fails `{Lex.Bad}`. A calling behavior surfaces scan failures under its own declared contract, for example behavior `parse` declares `fails {Parse.Bad}` and converts the scan outcome at its boundary.
- Callers declare the scan capability in `uses` alongside their input capability.
- Example:
  ```text
  track Lex.scan[buf] ::
    Ok tok -> done
    Err e -> fail e
  ```

### 4. `Oracles.Time` — sealed clock with mocked instants

- Operation: `now` with signature `now[]`, declared as `track Oracles.Time.now[] ::` returning `Outcome` carrying the instant.
- Callers declare `uses [Oracles.Time]`, `fails {Time.Unavailable}`, and the trailing `nondet` marker. A caller of a time behavior becomes `nondet`.
- Replay contract: every replayed run reads a declared mock holding a fixed instant. The mock and its instant are logged by `thornc test`. A direct clock read in replay without a declared mock is an error, reported as `E-NONDET-01` inside a deterministic suite.
- Example:
  ```text
  local behavior stamp uses [Oracles.Time] fails {Time.Unavailable} nondet =
    seq:
      region r0:
        track Oracles.Time.now[] ::
          Ok t -> done
          Err e -> fail e
  ```

### 5. `Oracles.Rand` — sealed randomness with seeded mocks

- Operation: `next` with signature `next[]`, declared as `track Oracles.Rand.next[] ::` returning `Outcome` carrying the drawn value.
- Callers declare `uses [Oracles.Rand]`, `fails {Rand.Unavailable}`, and the trailing `nondet` marker. A caller of a random behavior becomes `nondet`.
- Seed contract: each random mock declares an explicit fixed seed, and `thornc test` logs the seed for replay. A mock without a fixed logged seed is error `E-SEED-01`. A direct random read in replay without a declared mock is an error, reported as `E-NONDET-01` inside a deterministic suite. Real entropy is never read during replay.
- Example:
  ```text
  track Oracles.Rand.next[] ::
    Ok v -> done
    Err e -> fail e
  ```

### 6. `Foreign.C` — reserved boundary form, never a plain call

- There is no direct C call syntax. The only form is the reserved boundary wrapper `foreign risk uses [Foreign.C] nondet` with a copy across the boundary. A foreign handle held across more than one `seq` block is an error.
- The `fails` set of a foreign boundary comes from its generated binding contract, for example `{Foreign.Denied}`. Bindings are generated from contracts by tooling, never hand-written as inline `extern` declarations.
- Calling through the boundary without the `foreign risk` wrapper is an error.
- Example shape:
  ```text
  foreign risk uses [Foreign.C] nondet
  ```
  The wrapped call copies its arguments across the boundary and adopts results back into a local region.

## Examples

### Greeting through the catalog

```text
api v0.1

open behavior greet uses [Std.Out] fails {Io.Denied} =
  seq:
    region r0:
      let msg: Text in r0 = "hello from thorn"
      track Std.Out.emit[msg] ::
        Ok _ -> done
        Err e -> fail e
```

### Parse pipeline across three entries

```text
api v0.1

local behavior parse uses [Std.In, Lex.scan] fails {Parse.Bad} =
  seq:
    region rparse gc:
      track Std.In.read[] ::
        Ok buf -> track Lex.scan[buf] ::
          Ok tok -> done
          Err e -> fail e
        Err e -> fail e
```

## Errors

Catalog breaches reuse existing diagnostics and add no new codes. Oracle use from a deterministic replay context reports `E-NONDET-01`. A seedless oracle mock reports `E-SEED-01`. A daemon or channel breach inside catalog examples reports `E-DAEMON-01` or `E-CHAN-01`. A dropped catalog value without `discard` reports `E-DISCARD-01`. The canonical registry stays in the v0.1 core.

## Non-goals

- No language names beyond the six catalog entries in v0.1.
- No fetch capability inside the language. Fetch manifests are toolchain configuration and are governed by the `thornc` document.
- No per-channel operations in the catalog. `send` and `recv` belong to their channel, not to the closed world.
- No additional `Std`, `Lex`, or `Oracles` members in v0.1.
- No hand-written foreign declarations. Boundary bindings are generated from contracts.
- No real clock, entropy, or environment reads during replay. Sealed suites read only declared mocks.
