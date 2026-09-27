# THORN Syntax (v0.1)

## Overview

THORN v0.1 source is expression-only. Every block ends with a single-exit `Outcome`. Layout is indentation-delimited with two distinct symbols: `=` binds a name to its body, and `:` opens an indented block. Brackets carry contracts: `[]` holds effect sets, `{}` holds error sets. There are no C-style statements, no semicolons, and no brace blocks.

Each file opens with a version seal line such as `api v0.1`.

## Rules

### 1. File seal and layout

- The first line of every file is a seal such as `api v0.1`. A build with mixed seals must declare the mix explicitly. An undeclared mix is error `E-SEAL-01`.
- Indentation is 2 spaces per level. Tabs are forbidden so that `thornc` parses layout deterministically.
- A newline ends a simple line. `[]` and `{}` lists may span lines when continuation lines are indented deeper than the opening line.
- `#` starts a line comment that runs to end of line. There are no block comments in v0.1.

### 2. `=` binds a name, `:` opens a block

- `=` follows `behavior`, `task`, `daemon`, `shape`, `capability`, `channel`, `spawn`, and `let`. It binds the declared name to its body. A multi-line body is the indented block that follows the `=` line.
- `:` follows `seq`, `region`, `match`, and `fold`, where it opens the indented block that belongs to the construct. Its only other jobs are shape ascription inside the one-line `channel NAME: SHAPE =` and `let NAME: SHAPE in REGION = EXPR` forms, and field ascription inside shape declaration lines of the form `field: SHAPE`.
- `::` after a `track` expression opens the indented arm list that handles the `Outcome`.
- No other use of `=` or `:` is valid. `=>` is not a THORN operator.

### 3. Lexical forms: identifiers, literals, comments

- Value, behavior, task, channel, and region names use `snake_case`: they start with a lowercase letter followed by lowercase letters, digits, or underscores.
- Shape and capability names use `PascalCase`: they start with an uppercase letter. Dotted paths name capabilities and errors, for example `Std.Out`, `Io.Denied`, `Oracles.Time`.
- Integer and float literals are written plain with optional `_` digit separators, for example `42`, `4_000`, `3.5`. A literal takes its type from the ascribed declaration at its position, for example `let n: U64 in r0 = 4_000`. A literal in a position without an ascribed width is error `E-TYPE-01`. Only decimal literals exist in v0.1.
- Text literals use double quotes with `\"` and `\\` as the only escapes in v0.1.
- `#` comments run to end of line and never nest.

### 4. Visibility is explicit

- Every `shape`, `behavior`, and `capability` declaration starts with a visibility marker: `open` means usable outside the seal unit, `local` means unit-only. The marker comes before the declaration keyword, for example `open behavior greet` or `local shape Point`.
- A missing visibility marker is an error. There is no default visibility.
- `daemon` work is always local to its owning task tree and takes no visibility marker. `task`, `spawn`, `channel`, and `let` follow their enclosing scope.

### 5. Declaration signatures and canonical order

- Behavior form with canonical clause order:
  `[open|local] behavior NAME[(name: SHAPE, ...)] uses [Effects] fails {Errors} requires ... ensures ... cost {...} decreases ... nondet =`
  Parameters in parentheses are adopted into the callee scope. Only `uses` and `fails` are mandatory in v0.1. A missing `uses` or `fails` is an error. A missing `requires`, `ensures`, or `cost` is warning `W-CONTRACT-01` in v0.1.
- Daemon form: `daemon NAME cancel TOKEN uses [Effects] fails {Errors} ... =`. The `cancel` token sits directly after the name. A daemon without a token is error `E-DAEMON-01`.
- Task form: `task NAME isolates [regions] =`.
- Channel form: `channel NAME: SHAPE =`.
- Let form: `let NAME: SHAPE in REGION = EXPR`.
- `nondet` is a trailing signature marker for behaviors that use oracle capabilities. Calling one from a deterministic context is error `E-NONDET-01`.
- `NAME[args]` calls a behavior: arguments evaluate left to right and move, bind to parameters in order, and the callee Outcome returns to the call site. Unknown callees, non-behavior heads, and arity mismatches against declared parameters are codeless build rejections.
- Behavior calls nest to 64 levels; deeper nesting fails the run without a code.
- A callee sees only its parameters and catalog operations; caller locals stay invisible across the call boundary.

### 6. Control: match, fold, recurse, track

- Decision form: `match EXPR:` followed by arms of the form `PATTERN -> EXPR`. Every `match` is exhaustive and all arms return the same `shape`.
- Bounded repetition form: `fold bound N:` where `N` is a pure `U64` expression computed once on entry, immutable in the body, and checked against the declared `cost`. Example fragment:
  ```text
  fold bound n:
    match step:
      Ok _ -> done
      Err e -> fail e
  ```
- Recursive behavior declares `decreases <expr>` naming the shrinking measure. Structural recursion is accepted automatically. An unproven decrease is warning `W-TERM-01` in v0.1.
- Error handling form: `track EXPR ::` followed by arms `Ok x -> ...` and `Err e -> ...`. Arms use `->` only. `_` may explicitly discard an `Ok` payload, as in `Ok _ -> done`. Errors are never swallowed silently.
- `cancel[ct]` is an expression returning `Outcome` that names a token bound by an enclosing `daemon NAME cancel TOKEN` declaration. It must appear under `track ::`. Naming a token with no enclosing binding fails the run without a code; authority comes from token ownership, not from `uses`.
- There is no `if`, `for`, `while`, `try`, or primitive loop. Unbounded work is a `daemon` with a cancel token, never a bare infinite loop.

### 7. Effects, regions, tasks, and channels at the use site

- Order inside one task is requested with `seq:` followed by the ordered steps. `seq:` creates no task.
- Allocation sites name their region: `region NAME:` or `region NAME gc:`. A `gc` region is collected locally and cannot be shared, adopted, or sent on a channel.
- Sending isolates a value in the sender, moves it through the channel, and the receiver adopts it: `isolate -> move -> adopt`. Use after channel close is error `E-CHAN-01`.
- Foreign access uses the reserved form `foreign risk uses [Foreign.C] nondet` with a copy across the boundary. A foreign handle held across more than one `seq` block is an error. Full interop detail stays in the complete specification.
- `import ALIAS = vendor "rel/path.thorn" hash "<64hex>"` binds a module namespace; modules are not values.
- ALIAS is any identifier except `Std`, `Oracles`, `Lex`, or `Foreign`; shadowing those roots is a codeless rejection.
- Imported files join the importing unit: equal seal required, hash must match; mismatch and seal difference are codeless build rejections.
- Imported files are definitions-only: task declarations and nested imports inside are codeless rejections. Resolution root is the entry file's directory, fenced to the unit.
- Calls use `ALIAS.behavior[args]` (exactly two levels); imported callees must be open.
- Callee capabilities must be covered by caller uses; arity follows the declared-parameters rule.
- Resolution order is alias, then catalog, then local channel, otherwise codeless rejection.
- Integer `+ - *` evaluate with standard precedence and left associativity; there are no parentheses, so name every intermediate result with an explicit `let`.
- Arithmetic is U64-only: operands and results must satisfy 0 <= v < 2^64, checked dynamically with no conversion from other widths.
- Overflow, underflow, and bool operands fail without a code.
- Reads in expressions move like plain names (`a + a` fails on the second read); the `copy` form is undefined, deferred with debt.
- Fold iterations are independent with no accumulator; counting only, no combining of results.

### 8. Banned forms and their replacements

- Banned: early `return`, `break`, `continue`, `goto`, `;`, `++`, `&&`, `||`, `if`, `for`, `while`, `try`, `catch`, `null`, `.unwrap()`, `!`, `=>`, brace blocks, and `while(true)`.
- Logic without hidden branches uses exhaustive `and` / `or` and collection-wide `all` / `any` returning `Outcome`.
- A dropped value requires explicit `discard`. An unused expression without `discard` is error `E-DISCARD-01`.
- Bodies terminate with `done` for success or `fail e` for a declared error. Copies are explicit `copy` calls, never implicit.

## Examples

### Ordered greeting with explicit visibility

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

`=` binds `greet` and `msg`. `:` opens `seq`, `region`, and the `track` arm list. Arms use `->`.

### Isolated task pair

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

Spawned tasks run concurrently in logical terms. The `Text` value is isolated, moved through `msg`, and adopted. No aliasing occurs.

### Tracked parse inside a local collection region

```text
api v0.1

local behavior parse uses [Std.In] fails {Parse.Bad} =
  seq:
    region rparse gc:
      track Std.In.read[] ::
        Ok buf -> track Lex.scan[buf] ::
          Ok tok -> done
          Err e -> fail e
        Err e -> fail e
```

`rparse` is collected locally and never crosses a channel. Input handling nests `track` arm lists.

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

```text
api v0.1

local behavior stamp uses [Oracles.Time] fails {Time.Unavailable} nondet =
  seq:
    region r0:
      track Oracles.Time.now[] ::
        Ok t -> done
        Err e -> fail e
```

`ct` is retained by the owner and cancelled before `r0` exits. `stamp` is `nondet` and cannot run inside a deterministic replay test.

## Errors

Syntax breaches surface through existing diagnostics where they overlap. Missing or mixed seals report `E-SEAL-01`. A daemon without its token reports `E-DAEMON-01`. Oracle use from a deterministic context reports `E-NONDET-01`. Channel misuse reports `E-CHAN-01`. Untyped numeric positions report `E-TYPE-01`. Dropped values without `discard` report `E-DISCARD-01`. All other malformed sources are parse rejections. This draft adds no new codes; the canonical registry stays in the v0.1 core.

## Non-goals

- No `=>`, no semicolons, no brace blocks, no tabs, and no block comments.
- No non-decimal literals and no implicit numeric width in v0.1.
- No operator overloading and no macros in v0.1.
- No shared mutable state and no hidden control flow.
- No C-compatible statement syntax.
