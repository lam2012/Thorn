# THORN v0.1 Core (Memory + Concurrency)

## Overview

THORN v0.1 combines a region-locked linear memory model with a task-tree concurrency model. Every value lives in an explicit region. Ownership is move-only by default. Every program is a tree of isolated tasks. Sequential order must be requested. Unbounded work must be cancellable. Nondeterministic input must be sealed.

This document merges `thorn-memory-model` and `thorn-concurrency-model` into one core with a single error registry. The version line `api v0.1` is a replay seal: the same sources build the same result without undeclared network fetch during compilation.

## Rules

### 1. Regions are explicit

- Every allocation belongs to a named region declared by `region <name>:`.
- A value type always includes its region: `let msg: Text in r0 = "..."`.
- A region is freed as a whole when its enclosing block exits. No individual `free`.
- Region names are lexical and cannot be aliased.

### 2. Move-only, no defaults, no implicit discard

- Assignment and argument passing move ownership. The source binding is no longer usable after a move.
- There is no implicit copy or clone. Copy requires an explicit `copy` behavior call that is visible in the source.
- `I32`, `U64`, `F32`, `Text`, and user-defined `shape` types all follow move semantics. Small scalar size does not grant copy semantics.
- A bare `Int` or `Float` is a compile error. Width and signedness are required: `I32`, `U64`, `F32`.
- No default visibility. Every `shape`, `behavior`, and `capability` declares its visibility explicitly.
- No default `else`. Every `match` is exhaustive. All `match` arms return the same `shape`.
- Every expression produces a value of a declared `shape`. Ignoring a value is a compile error. Explicit `discard` is required to drop a value.

### 3. Isolate, move, adopt across tasks and channels

- Values are isolated to their owning task by default. A task cannot name values owned by another task.
- A channel is declared with a value shape: `channel msg: Text =`.
- Sending isolates a value in the sender, moves it through the channel, and the receiver adopts it into a local region.
- Pattern: `isolate -> move -> adopt`. No shared mutable reference crosses a task or channel boundary.
- A channel closes when its defining block exits. Use after close is a compile error.

### 4. Task tree is default, sequence is requested

- A program starts at `task root` and grows only through `spawn`.
- There are no threads, no thread ids, and no `async/await` keywords. The only primitives are `task`, `spawn`, `channel`, and `cancel`.
- Tasks spawned in the same block run concurrently in logical terms. Order between them is not defined.
- To force order, the author requests `seq:` and places the ordered steps inside one indented block. `seq:` does not create a new task.
- A task ends with a single-exit `Outcome`. There is no early `return`.
- Holding a C pointer or a foreign handle across more than one `seq` block is an error. Foreign access is covered by the interop rule in the full spec.

### 5. Daemons must be cancellable

- Unbounded work is not a loop. It is a `daemon` task with a named cancel token.
- Form: `daemon worker cancel ct uses [...] fails {...} =`.
- A daemon without a `cancel` token is a compile error `E-DAEMON-01` starting in v0.1.
- The owner tree must retain the token and must cancel before the enclosing region exits. A leaked daemon token is error `E-CANCEL-01`.
- Cancellation is delivered through the token and observed at `track` points and channel operations. `cancel` returns an `Outcome` and must be handled with `track ::`.
- There is no `while(true)` and no orphan background task.

### 6. Nondeterminism is sealed and propagates

- By default a task is deterministic. Clock, random, environment, and network input are unavailable.
- To use them, the behavior declares `nondet` and requests an explicit oracle capability such as `Oracles.Time` or `Oracles.Rand`.
- Seals propagate upward: `shared`, `nondet`, and `daemon` propagate from callee to caller. Wrappers are explicit: `risk` for partial logic, `share` for shared values, `daemon` for unbounded work, `nondet` for oracle use.
- A pure caller cannot hide an effectful callee. A `nondet` behavior cannot be called from a `deterministic` test replay context.
- Fetching from the network during compilation without a declared fetch capability is an error.

### 7. Contracts and bounds

- Every `behavior` and `daemon` declares `uses [Effects]` and `fails {Errors}`. Missing declarations are errors.
- Missing `requires`, `ensures`, or `cost` is warning `W-CONTRACT-01` in v0.1 and becomes an error in v0.2.
- A `fold bound n:` computes `n` once on entry. The bound expression must be pure and of type `U64`. It is immutable inside the body and checked against `cost {mem <= ...}`. If the bound derives from input, the caller proves `n <= cost.mem` or wraps the call in `risk`.
- Recursive behavior declares `decreases <expr>`. Structural recursion is accepted automatically. Unproven decrease is warning `W-TERM-01` in v0.1.
- There is no global garbage collector. A region may be marked `gc`, for example `region rparse gc:`. A `gc` region cannot be shared across tasks, cannot be adopted, and cannot cross a channel.

### 8. Version seal

- Each file opens with a seal line such as `api v0.1`.
- The seal fixes the language version used for parsing, checking, and replay. Mixed seals in one build must be declared explicitly.
- A version bump example: changing `api v0.1` to `api v0.2` re-checks `W-CONTRACT-01` and `W-TERM-01` as errors and may reject sources that compiled with warnings under v0.1.

## Examples

### Minimal region with ordered steps

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

### Local GC region with tracked input

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

### Cancellable daemon and sealed time

```text
api v0.1

task root isolates [r0] =
  region r0:
    daemon ticker cancel ct uses [Std.Out] fails {Io.Denied} =
      track Std.Out.emit["tick"] ::
        Ok _ -> done
        Err e -> fail e
```

`ct` is the cancel token. The owner must cancel `ct` before `r0` exits. A daemon without `cancel ct` fails with `E-DAEMON-01`.

```text
api v0.1

behavior stamp uses [Oracles.Time] fails {Time.Unavailable} nondet =
  seq:
    region r0:
      track Oracles.Time.now[] ::
        Ok t -> done
        Err e -> fail e
```

`stamp` is `nondet`. Any caller of `stamp` becomes `nondet`. It cannot run inside a deterministic replay test.

## Errors

| Code | Condition | Severity in v0.1 |
|------|-----------|------------------|
| `E-REGION-01` | Use of a value outside its defining region | Error |
| `E-MOVE-01` | Use after move | Error |
| `E-SHARE-01` | Sharing without `isolate -> move -> adopt` | Error |
| `E-GC-01` | Sharing or adopting a `gc` region | Error |
| `E-TYPE-01` | Bare `Int` or `Float` without width | Error |
| `E-DISCARD-01` | Unused expression without `discard` | Error |
| `E-TASK-01` | Naming a value owned by another task | Error |
| `E-CHAN-01` | Use after channel close | Error |
| `E-DAEMON-01` | `daemon` without `cancel` token | Error |
| `E-CANCEL-01` | Leaked daemon token at region exit | Error |
| `E-NONDET-01` | Oracle use without `nondet` seal | Error |
| `W-CONTRACT-01` | Missing `requires`, `ensures`, or `cost` | Warning in v0.1, error in v0.2 |
| `W-TERM-01` | Recursive behavior without proven `decreases` | Warning in v0.1, error in v0.2 |

## Non-goals

- No global heap with implicit collection.
- No reference counting as an invisible fallback.
- No C-style pointer arithmetic or unchecked casts.
- No inheritance-based object layout.
- No cross-task shared mutable state.
- No threads exposed to the author.
- No `async/await` annotations scattered through calls.
- No hidden scheduler yield and no hidden timeout.
- No background work without a cancel token.
- No clock, random, or environment access outside `Oracles.*` and `nondet`.
