# THORN Concurrency Model (v0.1)

## Overview

In THORN, concurrency is the default execution shape. Every program is a tree of isolated tasks. Sequential execution is a privilege that must be requested. Tasks never share mutable state. They communicate only through explicit channels with isolate, move, and adopt semantics. Infinite work must be declared as a cancellable daemon. Nondeterministic inputs must be declared through explicit oracles.

This model gives deterministic replay for tested paths and explicit cost for server and embedded targets.

## Rules

### 1. Task tree is the default

- A program starts at `task root` and grows only through `spawn`.
- Every task is isolated by default. It owns its regions. It cannot name values owned by another task.
- There are no threads, no thread ids, and no `async/await` keywords. The only primitives are `task`, `spawn`, `channel`, and `cancel`.
- A task ends with a single-exit `Outcome`. There is no early `return`.

### 2. Channels carry ownership

- A channel is declared with a value shape: `channel msg: Text =`.
- Sending isolates a value in the sender, moves it through the channel, and the receiver adopts it into a local region.
- Pattern: `isolate -> move -> adopt`. No shared reference crosses a channel.
- A channel closes when its defining block exits. Use after close is a compile error.

### 3. Sequential execution must be requested

- Tasks spawned in the same block run concurrently in logical terms. Order between them is not defined.
- To force order, the author requests `seq:` and places the ordered steps inside one indented block.
- `seq:` does not create a new task. It constrains order inside the current task.
- Holding a C pointer or a foreign handle across more than one `seq` block is an error.

### 4. Daemons must be cancellable

- Unbounded work is not a loop. It is a `daemon` task with a named cancel token.
- Form: `daemon worker cancel ct uses [...] fails {...} =`.
- A daemon without a `cancel` token is a compile error `E-DAEMON-01` starting in v0.1.
- The owner tree must retain the token and must cancel before the enclosing region exits. A leaked daemon is an error.
- There is no `while(true)` and no orphan background task.

### 5. Cancellation is explicit and cooperative

- Cancellation is delivered through the cancel token. It is observed at `track` points and channel operations.
- A task that ignores cancellation and blocks forever fails its contract.
- `cancel` always returns an `Outcome` and must be handled with `track ::`, never ignored.

### 6. Nondeterminism is sealed

- By default a task is deterministic. Clock, random, environment, and network input are unavailable.
- To use them, the behavior declares `nondet` and requests an explicit oracle capability such as `Oracles.Time` or `Oracles.Rand`.
- A `nondet` callee infects its caller. The caller becomes `nondet` and must declare it. A `nondet` behavior cannot be called from a `deterministic` test replay context.
- Fetching from the network during compilation without a declared fetch capability is an error.

### 7. Seals propagate upward

- `shared`, `nondet`, and `daemon` propagate from callee to caller.
- Wrappers are explicit: `risk` for partial logic, `share` for shared values, `daemon` for unbounded work, `nondet` for oracle use.
- A pure caller cannot hide an effectful callee. The compiler reports the missing wrapper at the call site.

### 8. Interaction with memory and contracts

- Every `behavior` and `daemon` declares `uses [Effects]` and `fails {Errors}`. Missing declarations are errors.
- Missing `requires`, `ensures`, or `cost` is warning `W-CONTRACT-01` in v0.1 and becomes an error in v0.2.
- A `fold bound n:` computes `n` once on entry. The bound is a pure `U64` expression, immutable in the body, and checked against `cost {mem <= ...}`.
- Recursive behavior declares `decreases <expr>`. Structural recursion is accepted automatically. Unproven decrease is warning `W-TERM-01` in v0.1.
- A `gc` region cannot be shared across tasks and cannot cross a channel.

## Examples

### Minimal task pair

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

`greeter` and `logger` are isolated. The `Text` value is isolated, moved, and adopted. No aliasing occurs.

### Ordered steps inside one task

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

`seq:` constrains order. Without it, independent steps have no defined order.

### Cancellable daemon

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

### Sealed nondeterminism

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
| `E-TASK-01` | Naming a value owned by another task | Error |
| `E-CHAN-01` | Use after channel close | Error |
| `E-DAEMON-01` | `daemon` without `cancel` token | Error |
| `E-CANCEL-01` | Leaked daemon token at region exit | Error |
| `E-NONDET-01` | Oracle use without `nondet` seal | Error |
| `E-SHARE-01` | Sharing without `isolate -> move -> adopt` | Error |
| `E-GC-01` | Sharing or adopting a `gc` region | Error |
| `W-CONTRACT-01` | Missing `requires`, `ensures`, or `cost` | Warning in v0.1, error in v0.2 |
| `W-TERM-01` | Recursive behavior without proven `decreases` | Warning in v0.1, error in v0.2 |

## Non-goals

- No threads exposed to the author.
- No `async/await` annotations scattered through calls.
- No shared mutable state between tasks.
- No hidden scheduler yield and no hidden timeout.
- No background work without a cancel token.
- No clock, random, or environment access outside `Oracles.*` and `nondet`.
