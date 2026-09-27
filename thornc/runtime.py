"""Tree-walking runtime: tasks, channels, daemons, cancel (M3, stdlib only).

Single logical thread. Tasks interleave at observation points: track/match
completion, channel operations, and spawn/daemon declaration. A block exits
only after tasks declared inside it complete, so channels outlive their users.
Assumes statically checked input. Daemons yield after each body pass and
retire on cancel. M3: tokens live in run-global scope, so binding means the
daemon was declared and started before the cancel runs.
"""

import os
import re
from collections import deque
from dataclasses import dataclass, field

from . import contracts
from . import imports
from .errors import E_CANCEL_01, E_CHAN_01, E_SEED_01, Diagnostic
from .lex import TokenLine, split_args, tokenize
from .ops import World

BUDGET = 1000
CALL_DEPTH_CAP = 64  # Nested behavior calls. Each level costs several Python
# frames, so 64 stays far below the interpreter limit while exceeding any
# validation-pipeline need. Revisited when base-case recursion lands.

ARM_RE = re.compile(r"^(Ok|Err)\s+(\S+)\s*->\s*(.+)$")
DEF_RE = re.compile(r"^(?:(?:open|local)\s+)?(behavior|spawn|daemon|task)\s+([A-Za-z_][A-Za-z0-9_]*)")
DAEMON_RE = re.compile(r"^daemon\s+([A-Za-z_][A-Za-z0-9_]*)\s+cancel\s+([A-Za-z_][A-Za-z0-9_]*)")
REGION_RE = re.compile(r"^region\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+gc)?\s*:$")
CHANNEL_RE = re.compile(r"^channel\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(\S+)\s*=$")
LET_RE = re.compile(
    r"^let\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(\S+)\s+in\s+([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$"
)
DISCARD_RE = re.compile(r"^discard\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
TRACK_RE = re.compile(r"^track\s+(.+?)\s*::$")
MATCH_RE = re.compile(r"^match\s+(.+?)\s*:$")
FOLD_RE = re.compile(r"^fold\s+bound\s+(.+?)\s*:$")
CALL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*)\[(.*)\]$")
ARITH_RE = re.compile(r"^[A-Za-z0-9_+\-* ]+$")
ARITH_TOK_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9][0-9_]*|[+\-*]")
U64_MAX = 2**64 - 1
PARAMS_RE = re.compile(r"\(([^)]*)\)")
INT_RE = re.compile(r"^[+-]?[0-9][0-9_]*$")
FLOAT_RE = re.compile(r"^[+-]?[0-9][0-9_]*\.[0-9_]+$")
STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"')
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

OK = "ok"
ERR = "err"


class _Diag(Exception):
    def __init__(self, code: str, lineno: int, message: str) -> None:
        super().__init__(message)
        self.diagnostic = Diagnostic(code, lineno, message)


class _Failure(Exception):
    def __init__(self, lineno: int, message: str) -> None:
        super().__init__(message)
        self.lineno = lineno
        self.message = message


@dataclass
class _Node:
    lineno: int
    indent: int
    text: str
    kids: list["_Node"] = field(default_factory=list)


@dataclass
class _Channel:
    queue: deque = field(default_factory=deque)
    closed: bool = False


@dataclass
class _DaemonRec:
    cancelled: bool = False


@dataclass
class _Task:
    name: str
    daemon: bool
    gen: object = None
    outcome: tuple = (OK, None)
    done: bool = False
    scope: int = -1


def _unquote(text: str) -> str:
    body = text[1:-1]
    out: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body) and body[i + 1] in ('"', "\\"):
            out.append(body[i + 1])
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _tree(token_lines: list[TokenLine]) -> list[_Node]:
    roots: list[_Node] = []
    stack: list[tuple[int, _Node]] = []
    for tl in token_lines:
        if tl.blank or tl.text.startswith("api v"):
            continue
        node = _Node(tl.lineno, tl.indent, tl.text)
        while stack and stack[-1][0] >= tl.indent:
            stack.pop()
        if stack:
            stack[-1][1].kids.append(node)
        else:
            roots.append(node)
        stack.append((tl.indent, node))
    return roots


class _Run:
    def __init__(self, world: World) -> None:
        self.world = world
        self.tokens: dict[str, _DaemonRec] = {}
        self._scope_seq = 0

    def _new_scope(self) -> int:
        self._scope_seq += 1
        return self._scope_seq

    def _eval(self, task: _Task, env: list[dict], text: str, lineno: int):
        """Evaluate an expression to an Outcome. Generator: yields scheduler events."""
        text = text.strip()
        if text.startswith('"'):
            if STRING_RE.fullmatch(text) is None:
                raise _Failure(lineno, f"bad text literal: {text}")
            return (OK, _unquote(text))
        if INT_RE.fullmatch(text):
            try:
                return (OK, int(text.replace("_", "")))
            except ValueError:
                raise _Failure(lineno, f"bad integer literal: {text}")
        if FLOAT_RE.fullmatch(text):
            try:
                return (OK, float(text.replace("_", "")))
            except ValueError:
                raise _Failure(lineno, f"bad float literal: {text}")
        if text in ("true", "false"):
            return (OK, text == "true")
        if text == "done":
            return (OK, None)
        call = CALL_RE.match(text)
        if call is None:
            if ARITH_RE.fullmatch(text) and re.search(r"[+\-*]", text):
                return self._arith_eval(task, env, text, lineno)
            if NAME_RE.fullmatch(text) is None:
                root = text.split(".", 1)[0]
                if NAME_RE.fullmatch(root) is not None:
                    raise _Failure(lineno, f"unbound name: {root}")
                raise _Failure(lineno, f"not executable: {text}")
            for frame in reversed(env):
                if text in frame:
                    val, movable = frame[text]
                    if movable:
                        del frame[text]
                    return (OK, val)
            raise _Failure(lineno, f"unbound name: {text}")
        head, arg = call.group(1), call.group(2).strip()
        if head == "cancel":
            if not NAME_RE.match(arg):
                raise _Failure(lineno, f"bad cancel token: {arg}")
            rec = self.tokens.get(arg)
            if rec is None:
                raise _Failure(lineno, f"unknown cancel token: {arg}")
            rec.cancelled = True
            return (OK, None)
        if head in self.behaviors:
            params, kids, defline = self.behaviors[head]
            return (yield from self._call_behavior(task, env, head, params, kids, defline, arg, lineno))
        parts = head.split(".")
        if len(parts) == 2 and parts[0] in self.imports:
            alias, name = parts
            module = self.imports[alias]
            if name not in module["behaviors"]:
                raise _Failure(lineno, f"unknown import target: {alias}.{name}")
            info = module["behaviors"][name]
            kids = self.import_nodes[alias][name]
            return (yield from self._call_behavior(task, env, f"{alias}.{name}", info["params"], kids, info["line"], arg, lineno))
        if len(parts) == 3 and parts[0] == "Std" and parts[1] == "Out" and parts[2] == "emit":
            val = yield from self._eval(task, env, arg, lineno)
            if val[0] == ERR:
                return val
            self.world.out.append(str(val[1]))
            yield ("observe",)
            return (OK, None)
        if len(parts) == 3 and parts[0] == "Std" and parts[1] == "In" and parts[2] == "read":
            if not self.world.inputs:
                return (ERR, "Io.Denied")
            yield ("observe",)
            return (OK, self.world.inputs.pop(0))
        if len(parts) == 2 and parts[0] == "Lex" and parts[1] == "scan":
            val = yield from self._eval(task, env, arg, lineno)
            if val[0] == ERR:
                return val
            toks = str(val[1]).split()
            yield ("observe",)
            if not toks:
                return (ERR, "Lex.Bad")
            return (OK, toks)
        if head == "Oracles.Time.now":
            yield ("observe",)
            return (OK, self.world.instant)
        if head == "Oracles.Rand.next":
            if self.world.rng is None:
                raise _Diag(E_SEED_01, lineno, "oracle mock without a fixed logged seed")
            yield ("observe",)
            return (OK, self.world.rng.random())
        if len(parts) == 2:
            target, op = parts
            for frame in reversed(env):
                if target in frame:
                    ch, _ = frame[target]
                    if not isinstance(ch, _Channel):
                        raise _Failure(lineno, f"not a channel: {target}")
                    if op == "send":
                        val = yield from self._eval(task, env, arg, lineno)
                        if val[0] == ERR:
                            return val
                        if ch.closed:
                            raise _Diag(E_CHAN_01, lineno, "send on closed channel")
                        ch.queue.append(val[1])
                        yield ("observe",)
                        return (OK, None)
                    if op == "recv":
                        while True:
                            if ch.queue:
                                yield ("observe",)
                                return (OK, ch.queue.popleft())
                            if ch.closed:
                                raise _Diag(E_CHAN_01, lineno, "recv on closed channel")
                            yield ("wait",)
            raise _Failure(lineno, f"unbound name: {target}")
        raise _Failure(lineno, f"not executable: {text}")

    def _u64(self, value, lineno: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise _Failure(lineno, "arithmetic on non-integer")
        if value < 0 or value > U64_MAX:
            raise _Failure(lineno, "integer overflow")
        return value

    def _arith_eval(self, task: _Task, env: list[dict], text: str, lineno: int):
        """Evaluate U64 + - * with standard precedence. Pure: no scheduler yield."""
        tokens = ARITH_TOK_RE.findall(text)
        if "".join(tokens).replace(" ", "") != text.replace(" ", ""):
            raise _Failure(lineno, f"bad arithmetic: {text}")
        pos = 0

        def peek():
            return tokens[pos] if pos < len(tokens) else None

        def next_tok():
            nonlocal pos
            if pos >= len(tokens):
                raise _Failure(lineno, f"bad arithmetic: {text}")
            token = tokens[pos]
            pos += 1
            return token

        def atom():
            token = next_tok()
            if re.fullmatch(r"[0-9][0-9_]*", token):
                return self._u64(int(token.replace("_", "")), lineno)
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
                for frame in reversed(env):
                    if token in frame:
                        val, movable = frame[token]
                        if movable:
                            del frame[token]
                        return self._u64(val, lineno)
                raise _Failure(lineno, f"unbound name: {token}")
            raise _Failure(lineno, f"bad arithmetic: {text}")

        def term():
            value = atom()
            while peek() == "*":
                next_tok()
                value = self._u64(value * atom(), lineno)
            return value

        def expr():
            value = term()
            while peek() in ("+", "-"):
                op = next_tok()
                rhs = term()
                value = self._u64(value + rhs if op == "+" else value - rhs, lineno)
            return value

        value = expr()
        if peek() is not None:
            raise _Failure(lineno, f"bad arithmetic: {text}")
        return (OK, value)

    def _call_behavior(self, task: _Task, env: list[dict], label: str, params, kids, defline: str, arg: str, lineno: int):
        args = [] if arg == "" else split_args(arg)
        if params is not None and len(args) != len(params):
            raise _Failure(lineno, f"arity mismatch calling {label}")
        values = []
        for a in args:
            val = yield from self._eval(task, env, a.strip(), lineno)
            if val[0] == ERR:
                return val
            values.append(val[1])
        actuals = {}
        if params is not None:
            for pname, v in zip(params, values):
                actuals[pname] = v
        req = contracts.parse_requires(defline)
        if req is not None:
            try:
                held = contracts.eval_ensures(req, dict(actuals))
            except ValueError as exc:
                raise _Failure(lineno, f"bad requires: {exc}")
            if not held:
                raise _Failure(lineno, "requires violated")
        if self.depth >= CALL_DEPTH_CAP:
            raise _Failure(lineno, "call depth exceeded")
        frame = {pname: (v, True) for pname, v in actuals.items()}
        call_env = [frame]
        self.depth += 1
        result = yield from self._exec_block(task, call_env, kids)
        self.depth -= 1
        if result[0] == OK:
            ens = contracts.parse_ensures(defline)
            if ens is not None:
                try:
                    held = contracts.eval_ensures(ens, {"result": result[1], **actuals})
                except ValueError as exc:
                    raise _Failure(lineno, f"bad ensures: {exc}")
                if not held:
                    raise _Failure(lineno, "ensures violated")
        return result

    def _arm_body(self, task: _Task, env: list[dict], arm: _Node):
        match = ARM_RE.match(arm.text)
        assert match is not None
        body = match.group(3).strip()
        if body == "done":
            return (OK, None)
        if body.startswith("fail "):
            name = body[5:].strip()
            for frame in reversed(env):
                if name in frame:
                    val, _ = frame[name]
                    return (ERR, val)
            raise _Failure(arm.lineno, f"unbound error name: {name}")
        track = TRACK_RE.match(body)
        if track is not None:
            return (yield from self._track(task, env, track.group(1), arm.kids, arm.lineno))
        nested = MATCH_RE.match(body)
        if nested is not None:
            return (yield from self._track(task, env, nested.group(1), arm.kids, arm.lineno))
        return (yield from self._eval(task, env, body, arm.lineno))

    def _track(self, task: _Task, env: list[dict], expr: str, arms: list[_Node], lineno: int):
        outcome = yield from self._eval(task, env, expr, lineno)
        for arm in arms:
            match = ARM_RE.match(arm.text)
            if match is None:
                raise _Failure(arm.lineno, f"bad arm: {arm.text}")
            if match.group(1) != ("Ok" if outcome[0] == OK else "Err"):
                continue
            pat = match.group(2)
            if pat != "_":
                env[-1][pat] = (outcome[1], True)
            result = yield from self._arm_body(task, env, arm)
            yield ("observe",)
            return result
        raise _Failure(lineno, "non-exhaustive arms")

    def _exec_block(self, task: _Task, env: list[dict], kids: list[_Node]):
        """Execute block children in order. Exits join tasks declared in this block."""
        here = self._new_scope()
        outcome: tuple = (OK, None)
        for node in kids:
            text = node.text
            if node.text.startswith("api v"):
                continue
            dm = DEF_RE.match(text)
            if dm and dm.group(1) in ("behavior", "shape", "capability"):
                continue
            if dm and dm.group(1) == "task":
                continue
            rm = REGION_RE.match(text)
            if rm:
                env.append({})
                outcome = yield from self._exec_block(task, env, node.kids)
                env.pop()
                continue
            if text == "seq:":
                outcome = yield from self._exec_block(task, env, node.kids)
                continue
            cm = CHANNEL_RE.match(text)
            if cm:
                ch = _Channel()
                env[-1][cm.group(1)] = (ch, False)
                outcome = yield from self._exec_block(task, env, node.kids)
                yield from self._join(task, here)
                ch.closed = True
                continue
            if dm and dm.group(1) == "spawn":
                child = _Task(dm.group(2), False, scope=here)
                child.gen = self._exec_block(child, [{}] + env, node.kids)
                self._tasks.append(child)
                yield ("spawn",)
                continue
            dam = DAEMON_RE.match(text)
            if dam:
                rec = _DaemonRec()
                self.tokens[dam.group(2)] = rec
                child = _Task(dam.group(1), True, scope=here)
                child.gen = self._daemon(child, [{}] + env, node.kids, rec, node.lineno)
                self._tasks.append(child)
                yield ("spawn",)
                continue
            lm = LET_RE.match(text)
            if lm:
                rhs = lm.group(4).strip()
                if not rhs:
                    raise _Failure(node.lineno, f"empty binding: {text}")
                val = yield from self._eval(task, env, rhs, node.lineno)
                if val[0] == ERR:
                    return val
                env[-1][lm.group(1)] = (val[1], True)
                outcome = (OK, None)
                continue
            dis = DISCARD_RE.match(text)
            if dis:
                for frame in reversed(env):
                    frame.pop(dis.group(1), None)
                outcome = (OK, None)
                continue
            tm = TRACK_RE.match(text)
            if tm:
                outcome = yield from self._track(task, env, tm.group(1), node.kids, node.lineno)
                continue
            mm = MATCH_RE.match(text)
            if mm:
                outcome = yield from self._track(task, env, mm.group(1), node.kids, node.lineno)
                continue
            fm = FOLD_RE.match(text)
            if fm:
                outcome = yield from self._fold(task, env, fm.group(1), node.kids, node.lineno)
                continue
            if text.startswith("fold "):
                raise _Failure(node.lineno, "fold execution out of scope in M3")
            outcome = yield from self._eval(task, env, text, node.lineno)
        yield from self._join(task, here)
        return outcome

    def _fold(self, task: _Task, env: list[dict], bound: str, kids: list[_Node], lineno: int):
        bound = bound.strip()
        if re.fullmatch(r"[+-]?[0-9][0-9_]*", bound):
            count = int(bound.replace("_", ""))
        elif NAME_RE.fullmatch(bound):
            hit = None
            for frame in reversed(env):
                if bound in frame:
                    hit = frame[bound]
                    break
            if hit is None:
                raise _Failure(lineno, f"unbound fold bound: {bound}")
            count, _ = hit
            if isinstance(count, bool) or not isinstance(count, int):
                raise _Failure(lineno, f"non-integer fold bound: {bound}")
        else:
            raise _Failure(lineno, f"bad fold bound: {bound}")
        if count < 0:
            raise _Failure(lineno, "negative fold bound")
        if self.cost is not None and count > self.cost:
            raise _Failure(lineno, f"fold bound {bound} exceeds cost {self.cost}")
        result: tuple = (OK, None)
        for _ in range(count):
            env.append({})
            result = yield from self._exec_block(task, env, kids)
            env.pop()
        return result

    def _join(self, task: _Task, scope: int):
        """Wait until tasks declared in this scope complete."""
        while True:
            live = [t for t in self._tasks if not t.done and t.scope == scope and t is not task]
            if not live:
                return
            yield ("join",)

    def _daemon(self, task: _Task, env: list[dict], kids: list[_Node], rec: _DaemonRec, lineno: int):
        while True:
            if rec.cancelled:
                return (OK, None)
            yield from self._exec_block(task, env, kids)
            if rec.cancelled:
                return (OK, None)

    def run_file(self, entry: "_Entry", behaviors: dict, importmap: dict, import_nodes: dict,
                 inputs, instant, seed):
        world = World.make(inputs, instant, seed)
        self.world = world
        self.tokens = {}
        self._tasks = []
        self.depth = 0
        self.behaviors = behaviors
        self.imports = importmap
        self.import_nodes = import_nodes
        self.cost = contracts.parse_cost_membytes(entry.line)
        if entry.params:
            return 1, world.out, None, [
                Diagnostic(None, entry.lineno, "entry behavior takes parameters")
            ]
        task = _Task(entry.name, entry.kind == "daemon", scope=self._new_scope())
        task.gen = self._exec_block(task, [{}], entry.kids)
        self._tasks.append(task)
        queue = deque([task])
        queued = {id(task)}
        steps = 0
        diags: list[Diagnostic] = []
        outcome: tuple | None = None
        while queue:
            current = queue.popleft()
            queued.discard(id(current))
            if current.done:
                continue
            try:
                current.gen.send(None)
            except StopIteration as stop:
                current.done = True
                current.outcome = stop.value
                if current is task:
                    outcome = stop.value
                continue
            except _Diag as err:
                return 1, world.out, None, [err.diagnostic]
            except _Failure as fail:
                return 1, world.out, None, [Diagnostic(None, fail.lineno, fail.message)]
            steps += 1
            if steps > BUDGET:
                live_daemon = next((t for t in self._tasks if not t.done and t.daemon), None)
                if live_daemon is not None:
                    return 1, world.out, None, [
                        Diagnostic(E_CANCEL_01, 0, "live daemon at step budget")
                    ]
                return 1, world.out, None, [Diagnostic(None, 0, "step budget exhausted")]
            for t in self._tasks:
                if t is not current and not t.done and id(t) not in queued:
                    queued.add(id(t))
                    queue.append(t)
            queue.append(current)
            queued.add(id(current))
        if outcome is not None and outcome[0] == OK and entry.kind == "behavior":
            ens = contracts.parse_ensures(entry.line)
            if ens is not None:
                try:
                    held = contracts.eval_ensures(ens, {"result": outcome[1]})
                except ValueError as exc:
                    return 1, world.out, outcome, [
                        Diagnostic(None, entry.lineno, f"bad ensures: {exc}")
                    ]
                if not held:
                    return 1, world.out, outcome, [
                        Diagnostic(None, entry.lineno, "ensures violated")
                    ]
        return 0, world.out, outcome, diags


@dataclass
class _Entry:
    kind: str
    name: str
    kids: list = field(default_factory=list)
    line: str = ""
    lineno: int = 0
    params: list[str] | None = None


def _parse_params(defline: str) -> list[str] | None:
    match = PARAMS_RE.search(defline)
    if match is None:
        return None
    inner = match.group(1).strip()
    if not inner:
        return []
    return [p.split(":")[0].strip() for p in inner.split(",")]


def find_entry(roots: list[_Node]) -> _Entry | None:
    for node in roots:
        dm = DEF_RE.match(node.text)
        if dm and dm.group(1) == "task":
            return _Entry("task", dm.group(2), node.kids, node.text, node.lineno)
    for node in roots:
        dm = DEF_RE.match(node.text)
        if dm and dm.group(1) in ("behavior", "daemon"):
            return _Entry(
                dm.group(1), dm.group(2), node.kids, node.text, node.lineno,
                _parse_params(node.text) if dm.group(1) == "behavior" else None,
            )
    return None


def _collect_behaviors(roots: list[_Node]) -> dict:
    table: dict = {}

    def visit(nodes: list[_Node]) -> None:
        for node in nodes:
            dm = DEF_RE.match(node.text)
            if dm and dm.group(1) == "behavior":
                table[dm.group(2)] = (_parse_params(node.text), node.kids, node.text)
            visit(node.kids)

    visit(roots)
    return table


def _load_imports(root: str, token_lines) -> tuple[dict, dict, list]:
    """Load entry-file imports. Returns (modules, node-kids, problems)."""
    importmap: dict = {}
    import_nodes: dict = {}
    problems: list = []
    seal = imports.read_seal(token_lines)
    for tl in token_lines:
        if tl.blank:
            continue
        match = imports.IMPORT_RE.match(tl.text)
        if match is None:
            if re.match(r"^import\b", tl.text):
                problems.append(Diagnostic(None, tl.lineno, "bad import declaration"))
            continue
        alias = match.group(1)
        if alias in ("Std", "Oracles", "Lex", "Foreign"):
            problems.append(Diagnostic(None, tl.lineno, f"import alias shadows catalog: {alias}"))
            continue
        if alias in importmap:
            problems.append(Diagnostic(None, tl.lineno, f"duplicate import alias: {alias}"))
            continue
        module, problem = imports.resolve(root, match.group(2), match.group(3), seal)
        if problem is not None:
            problems.append(Diagnostic(None, tl.lineno, problem))
            continue
        importmap[alias] = module
        kids_by_name: dict = {}
        for node in _tree(tokenize(module["source"])):
            dm = DEF_RE.match(node.text)
            if dm and dm.group(1) == "behavior":
                kids_by_name[dm.group(2)] = node.kids
        import_nodes[alias] = kids_by_name
    return importmap, import_nodes, problems


def run_source(source: str, inputs: list[str], instant: str, seed: int, src_path: str | None = None):
    """Parse and execute one source file. Returns (rc, output, outcome, diagnostics)."""
    from .layout import NEST_DEPTH_CAP

    run = _Run(World.make(inputs, instant, seed))
    tls = tokenize(source)
    if any(not tl.blank and tl.indent // 2 > NEST_DEPTH_CAP for tl in tls):
        return 1, [], None, [Diagnostic(None, 0, "nesting too deep")]
    nodes = _tree(tls)
    entry = find_entry(nodes)
    if entry is None:
        return 1, [], None, [Diagnostic(None, 0, "no runnable entry")]
    root = os.path.dirname(os.path.abspath(src_path)) if src_path else os.getcwd()
    importmap, import_nodes, problems = _load_imports(root, tls)
    if problems:
        return 1, [], None, problems
    return run.run_file(entry, _collect_behaviors(nodes), importmap, import_nodes, inputs, instant, seed)
