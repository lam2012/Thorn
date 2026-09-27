# THORN Memory Model (v0.1)

## Overview

THORN uses a region-locked linear memory model. Every value lives in an explicit region. Ownership is move-only by default. Sharing across tasks requires explicit isolation, move, and adoption. There is no global garbage collector. Garbage collection is permitted only inside a region explicitly marked `gc`, and such a region cannot be shared.

This model provides deterministic memory use for embedded targets and explicit cost control for server targets.

## Rules

### 1. Regions are explicit

- Every allocation belongs to a named region declared by `region <name>:`.
- A value type always includes its region: `let msg: Text in r0 = "..."`.
- A region is freed as a whole when its enclosing block exits. No individual `free`.
- Region names are lexical and cannot be aliased.

### 2. Move-only by default

- Assignment and argument passing move ownership. The source binding is no longer usable after a move.
- There is no implicit copy or clone. Copy requires an explicit `copy` behavior call that is visible in the source.
- `I32`, `U64`, `F32`, `Text`, and user-defined `shape` types all follow move semantics. Small scalar size does not grant copy semantics.

### 3. No default numeric or visibility types

- A bare `Int` or `Float` is a compile error. Width and signedness are required: `I32`, `U64`, `F32`.
- No default visibility. Every `shape`, `behavior`, and `capability` declares its visibility explicitly.
- No default `else`. Every `match` is exhaustive.

### 4. Isolate, move, adopt for sharing

- Values are isolated to their owning task by default.
- To transfer a value to another task, the owner isolates it, moves it through a `channel`, and the receiver adopts it into a local region.
- Pattern: `isolate -> move -> adopt`. No shared mutable reference.
- A `shared` seal propagates upward: any caller that touches a `shared` value becomes `shared` and must be wrapped in `share`.

### 5. No implicit discard

- Every expression produces a value of a declared `shape`.
- Ignoring a value is a compile error. Explicit `discard` is required to drop a value.
- All `match` arms return the same `shape`.

### 6. Local GC only

- Global GC is not available.
- A region may be marked `gc`, for example `region rparse gc:`. Inside such a region, short-lived values may be collected locally.
- A `gc` region cannot be shared across tasks and cannot be adopted. It must be fully consumed or discarded inside its defining task.
- Typical use is bounded parsing or formatting inside one `seq` block.

### 7. Interaction with cost and bounds

- A `fold bound n:` computes `n` once on entry. The bound expression must be pure and of type `U64`.
- The bound value is immutable inside the fold body and is checked against the declared `cost {mem <= ...}` of the enclosing behavior.
- If the bound derives from input, the caller proves `n <= cost.mem` or wraps the call in `risk`.

## Examples

### Minimal region

```text
api v0.1

behavior greet uses [Std.Out] fails {Io.Denied} =
  seq:
    region r0:
      let msg: Text in r0 = "hello from thorn"
      track Std.Out.emit[msg] ::
        Ok _ -> done
        Err e -> fail e
```

`msg` lives in `r0`. `emit` moves the value per its contract, or copies only through an explicit `copy` call. `r0` is released when the `seq` block exits.

### Transfer across tasks

```text
api v0.1

task root isolates [r0] =
  region r0:
    channel msg: Text =
      spawn greeter uses [msg.send, Std.Out] fails {Io.Denied} =
        track Std.Out.emit["hello"] ::
          Ok _ -> msg.send["hello"]
          Err e -> fail e
      spawn logger uses [msg.recv, Std.Out] fails {Io.Denied} =
        track msg.recv[] ::
          Ok t -> Std.Out.emit[t]
          Err e -> fail e
```

The `Text` value is isolated in the sender, moved through `msg`, and adopted by the receiver. No aliasing occurs.

### Local GC region

```text
api v0.1

behavior parse uses [Std.In] fails {Parse.Bad} =
  seq:
    region rparse gc:
      track Std.In.read[] ::
        Ok buf -> track Lex.scan[buf] ::
          Ok tok -> done
          Err e -> fail e
        Err e -> fail e
```

`rparse` is collected locally. It cannot be sent on a channel.

## Errors

| Code | Condition | Severity in v0.1 |
|------|-----------|------------------|
| `E-REGION-01` | Use of a value outside its defining region | Error |
| `E-MOVE-01` | Use after move | Error |
| `E-SHARE-01` | Sharing without `isolate -> move -> adopt` | Error |
| `E-GC-01` | Sharing or adopting a `gc` region | Error |
| `E-TYPE-01` | Bare `Int` or `Float` without width | Error |
| `E-DISCARD-01` | Unused expression without `discard` | Error |
| `W-CONTRACT-01` | Missing `requires`, `ensures`, or `cost` | Warning in v0.1, error in v0.2 |
| `W-TERM-01` | Recursive behavior without proven `decreases` | Warning in v0.1, error in v0.2 |
| `E-DAEMON-01` | `daemon` without `cancel` token | Error |

## Non-goals

- No global heap with implicit collection.
- No reference counting as an invisible fallback.
- No C-style pointer arithmetic or unchecked casts.
- No inheritance-based object layout.
- No cross-task shared mutable state.
