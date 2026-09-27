# THORN Types and Contracts (v0.1)

## Overview

Shapes are immutable by default and never inherit. Capabilities compose through `uses`. Behavior contracts state `requires`, `ensures`, and `cost` in canonical order. In v0.1, written contracts are recorded with the seal and enforced through generated deterministic tests; there is no static prover. Builds are single-seal units; cross-unit composition does not exist yet.

## Rules

### 1. Primitive inventory

- The primitive value shapes are the explicit-width numerics `I8`, `I16`, `I32`, `I64`, `U8`, `U16`, `U32`, `U64`, `F32`, `F64`, plus `Text` and `Bool`. A bare `Int` or `Float` is error `E-TYPE-01`.
- `Outcome` is the built-in result shape with `Ok` and `Err` arms. It is not user-definable.
- `done` is the success terminator producing an empty `Ok`. `fail e` produces the `Err` arm.
- Channels and regions are not shapes. A channel declares a shape parameter, and a region scopes lifetimes. Neither may appear as a field type, a parameter type, or a match arm shape.

### 2. Shape declarations

- Shape form: `[open|local] shape NAME =` followed by indented field lines of the form `field: SHAPE`, one per line.
- Fields carry ascribed shapes only. Region binding happens at the value site with `let`, never inside the shape.
- All fields are immutable in v0.1. There is no mutable-field syntax yet; data mutation beyond rebinding through moves is out of scope.
- Shapes are nominal: two shapes with different names are different shapes even with identical fields. There is no inheritance, no subtyping, and no generics in v0.1.
- Example:
  ```text
  local shape Point =
    x: F32
    y: F32
  ```

### 3. Capability composition through `uses`

- Capabilities name reusable operation sets from the standard catalog, for example `Std.Out`, `Std.In`, `Oracles.Time`. A behavior lists each capability it touches in `uses [A, B]`.
- A `capability` declaration groups catalog operations under one name for reuse. Its form is `[open|local] capability NAME =` followed by indented catalog paths, one per line.
- A missing `uses` entry for a touched capability is an error. Capabilities never grant implicit access.
- Example:
  ```text
  local capability Console =
    Std.Out
    Std.In
  ```

### 4. Behavior contracts and v0.1 enforcement

- Contract form with canonical clause order:
  `[open|local] behavior NAME uses [Effects] fails {Errors} requires PRED ensures PRED cost {mem <= N} decreases EXPR nondet =`
  Only `uses` and `fails` are mandatory in v0.1. A missing `requires`, `ensures`, or `cost` is warning `W-CONTRACT-01` in v0.1 and becomes an error in v0.2.
- Parameters are listed after the name as `[(name: SHAPE, ...)]` and are adopted into the callee scope. Predicates are boolean expressions over parameters, the exit name `result`, literals, comparisons `==` and `<=`, and exhaustive `and` / `or`.
- A written contract in v0.1 is enforced as follows: the clauses are recorded with the seal for replay, `thornc test` generates deterministic checks asserting `ensures` on exit under `requires` checked against actuals at call sites (assumed only for entry behaviors without callers), and `cost` is checked against `fold` bounds at build time with overruns failing the test run. There is no static proof obligation beyond the recorded warning codes.
- A recursive behavior declares `decreases <expr>` naming the shrinking measure. Structural recursion over a shape field is accepted statically. An unproven decrease is warning `W-TERM-01` in v0.1.
- Example with a full contract:
  ```text
  open behavior first uses [Std.Out] fails {Io.Denied} requires true ensures true cost {mem <= 1k} =
    seq:
      region r0:
        let msg: Text in r0 = "hi"
        track Std.Out.emit[msg] ::
          Ok _ -> done
          Err e -> fail e
  ```

### 5. Visibility and the single-unit scope

- `open` marks intent for use outside the seal unit. `local` restricts a name to its unit. The marker is mandatory; a missing marker is an error.
- v0.1 builds exactly one seal unit. Cross-file and cross-seal composition, including any import syntax, does not exist and is a Non-goal. `open` names are recorded for forward compatibility but resolve within the single unit.
- `daemon` work is always local to its owning task tree and takes no marker. `task`, `spawn`, `channel`, and `let` follow their enclosing scope.

## Examples

### Shape with a contracted reader

```text
api v0.1

local shape Point =
  x: F32
  y: F32

local behavior show uses [Std.Out] fails {Io.Denied} requires true ensures true cost {mem <= 2k} =
  seq:
    region r0:
      let msg: Text in r0 = "point"
      track Std.Out.emit[msg] ::
        Ok _ -> done
        Err e -> fail e
```

### Capability reuse

```text
api v0.1

local capability Console =
  Std.Out
  Std.In

open behavior greet uses [Console] fails {Io.Denied} requires true ensures true cost {mem <= 4k} =
  seq:
    region r0:
      let msg: Text in r0 = "hello from thorn"
      track Std.Out.emit[msg] ::
        Ok _ -> done
        Err e -> fail e
```

A capability entry in `uses` grants exactly its listed catalog operations, nothing more.

## Errors

Type and contract breaches reuse existing diagnostics and add no new codes. Missing contract clauses report `W-CONTRACT-01`. Unproven decrease reports `W-TERM-01`. Bare numerics report `E-TYPE-01`. A missing visibility marker and a missing `uses` entry are parse-time rejections under the syntax Errors section. The canonical registry stays in the v0.1 core.

## Non-goals

- No classes, no inheritance, no subtyping, and no generics in v0.1.
- No mutable-field syntax in v0.1. Shape data is immutable; rebinding happens only through moves.
- No cross-unit or cross-file composition and no import syntax in v0.1. Builds are single-seal units.
- No static prover in v0.1. Contracts are recorded and test-enforced; a future `thornc prove` is out of scope.
- No predicate quantifiers and no arithmetic inside contracts beyond comparison against bounds.
