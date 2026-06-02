# -*- coding: utf-8 -*-
"""MysticIR Federation v0.8.5 - Error Federation.

A prototype that verifies representative failure cases.

    ScatLang surface  -> same Core AST -> same CEK trace -> same error
    SeaIR surface     -> same Core AST -> same CEK trace -> same error

Programs with the same meaning but different surface symbols are normalized
to the same Core AST, and therefore reach the same CEK trace and error
signature (verified on representative cases).
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Mapping

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


# ─────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────

class ScatError(Exception):
    pass

class ParseError(ScatError):
    pass

class StepLimitError(ScatError):
    pass


# ─────────────────────────────────────────
# Values  (shared runtime representation)
# ─────────────────────────────────────────

class Value:
    def pretty(self) -> str:
        raise NotImplementedError
    def to_int(self) -> int:
        raise NotImplementedError


@dataclass(frozen=True)
class PoopZero(Value):
    def pretty(self) -> str: return "💩₀"
    def to_int(self) -> int: return 0


@dataclass(frozen=True)
class PoopSucc(Value):
    inner: Value
    def pretty(self) -> str: return f"💩×{self.to_int()}"
    def to_int(self) -> int: return 1 + self.inner.to_int()


@dataclass(frozen=True)
class Underflow(Value):
    def pretty(self) -> str: return "💩∅"
    def to_int(self) -> int: return 0


def int_to_poop(n: int) -> Value:
    if n < 0:
        raise ValueError("Nat cannot be negative")
    value: Value = PoopZero()
    for _ in range(n):
        value = PoopSucc(value)
    return value


# ─────────────────────────────────────────
# Core AST  (shared by both frontends)
# ─────────────────────────────────────────

class Expr:
    pass

@dataclass(frozen=True)
class PoopZeroExpr(Expr): pass

@dataclass(frozen=True)
class PoopSuccExpr(Expr):
    expr: Expr

@dataclass(frozen=True)
class Var(Expr):
    name: str

@dataclass(frozen=True)
class ScatAdd(Expr):
    left: Expr; right: Expr

@dataclass(frozen=True)
class ScatNeq(Expr):
    left: Expr; right: Expr

@dataclass(frozen=True)
class ScatPred(Expr):
    expr: Expr

@dataclass(frozen=True)
class ScatSub(Expr):
    left: Expr; right: Expr

@dataclass(frozen=True)
class ScatMod(Expr):
    left: Expr; right: Expr

@dataclass(frozen=True)
class ScatEq(Expr):
    left: Expr; right: Expr


class Stmt:
    pass

@dataclass(frozen=True)
class Assign(Stmt):
    name: str; expr: Expr

@dataclass(frozen=True)
class Flush(Stmt):
    expr: Expr

@dataclass(frozen=True)
class While(Stmt):
    left: Expr; right: Expr
    body: tuple[Stmt, ...]


# ─────────────────────────────────────────
# Observation / Sink
# ─────────────────────────────────────────

@dataclass(frozen=True)
class Artifact:
    value: Value
    born_at_step: int

@dataclass(frozen=True)
class Observation:
    artifact: Artifact
    context: str

@dataclass
class ObservationSink:
    _observations: list[Observation] = field(default_factory=list)
    step_count: int = 0
    frontend: str = "unknown"

    def tick(self) -> None:
        self.step_count += 1

    def observe(self, value: Value, context: str = "flush") -> None:
        self._observations.append(Observation(Artifact(value, self.step_count), context))

    @property
    def observations(self) -> tuple[Observation, ...]:
        return tuple(self._observations)


# ─────────────────────────────────────────
# Continuations (CEK machine)
# ─────────────────────────────────────────

class Kont:
    pass

@dataclass(frozen=True)
class Halt(Kont): pass

@dataclass(frozen=True)
class AssignK(Kont):
    name: str; rest: tuple[Stmt, ...]
    env: Mapping[str, Value]; kont: Kont

@dataclass(frozen=True)
class FlushK(Kont):
    rest: tuple[Stmt, ...]
    env: Mapping[str, Value]; kont: Kont

@dataclass(frozen=True)
class SuccK(Kont):
    kont: Kont

@dataclass(frozen=True)
class AddLeftK(Kont):
    right: Expr; env: Mapping[str, Value]; kont: Kont

@dataclass(frozen=True)
class AddRightK(Kont):
    left_val: Value; kont: Kont

@dataclass(frozen=True)
class NeqLeftK(Kont):
    right: Expr; env: Mapping[str, Value]; kont: Kont

@dataclass(frozen=True)
class NeqRightK(Kont):
    left_val: Value; kont: Kont

@dataclass(frozen=True)
class PredK(Kont):
    kont: Kont

@dataclass(frozen=True)
class SubLeftK(Kont):
    right: Expr; env: Mapping[str, Value]; kont: Kont

@dataclass(frozen=True)
class SubRightK(Kont):
    left_val: Value; kont: Kont

@dataclass(frozen=True)
class ModLeftK(Kont):
    right: Expr; env: Mapping[str, Value]; kont: Kont

@dataclass(frozen=True)
class ModRightK(Kont):
    left_val: Value; kont: Kont

@dataclass(frozen=True)
class EqLeftK(Kont):
    right: Expr; env: Mapping[str, Value]; kont: Kont

@dataclass(frozen=True)
class EqRightK(Kont):
    left_val: Value; kont: Kont

@dataclass(frozen=True)
class WhileK(Kont):
    stmt: While; rest: tuple[Stmt, ...]
    env: Mapping[str, Value]; kont: Kont


# ─────────────────────────────────────────
# Control wrappers
# ─────────────────────────────────────────

@dataclass(frozen=True)
class EvalExpr:
    expr: Expr

@dataclass(frozen=True)
class ReturnValue:
    value: Value


# ─────────────────────────────────────────
# CEK State
# ─────────────────────────────────────────

@dataclass
class State:
    control: object
    env: dict[str, Value]
    kont: Kont
    sink: ObservationSink


TRUE  = PoopSucc(PoopZero())
FALSE = PoopZero()


def is_halted(state: State) -> bool:
    return isinstance(state.control, ReturnValue) and isinstance(state.kont, Halt)


# ─────────────────────────────────────────
# Primitive operations
# ─────────────────────────────────────────

def poop_add(l: Value, r: Value) -> Value:
    return int_to_poop(l.to_int() + r.to_int())

def poop_pred(v: Value) -> Value:
    if isinstance(v, PoopZero): return Underflow()
    if isinstance(v, PoopSucc): return v.inner
    if isinstance(v, Underflow): return Underflow()
    raise ScatError(f"pred on unknown value: {v!r}")

def poop_sub(l: Value, r: Value) -> Value:
    return int_to_poop(max(l.to_int() - r.to_int(), 0))

def poop_mod(l: Value, r: Value) -> Value:
    if r.to_int() == 0:
        raise ScatError("mod by zero")
    return int_to_poop(l.to_int() % r.to_int())

def poop_eq(l: Value, r: Value) -> Value:
    return TRUE if l.to_int() == r.to_int() else FALSE

def poop_neq(l: Value, r: Value) -> Value:
    return TRUE if l.to_int() != r.to_int() else FALSE


# ─────────────────────────────────────────
# CEK step evaluator
# ─────────────────────────────────────────

def step(state: State) -> State:
    state.sink.tick()
    ctrl = state.control

    if isinstance(ctrl, tuple):
        if not ctrl:
            return State(ReturnValue(PoopZero()), state.env, state.kont, state.sink)
        head, *tail = ctrl
        rest = tuple(tail)
        if isinstance(head, Assign):
            return State(EvalExpr(head.expr), state.env,
                         AssignK(head.name, rest, dict(state.env), state.kont), state.sink)
        if isinstance(head, Flush):
            return State(EvalExpr(head.expr), state.env,
                         FlushK(rest, dict(state.env), state.kont), state.sink)
        if isinstance(head, While):
            return State(EvalExpr(ScatNeq(head.left, head.right)), state.env,
                         WhileK(head, rest, dict(state.env), state.kont), state.sink)
        raise ScatError(f"unknown statement: {head!r}")

    if isinstance(ctrl, EvalExpr):
        expr = ctrl.expr
        if isinstance(expr, PoopZeroExpr):
            return State(ReturnValue(PoopZero()), state.env, state.kont, state.sink)
        if isinstance(expr, PoopSuccExpr):
            return State(EvalExpr(expr.expr), state.env, SuccK(state.kont), state.sink)
        if isinstance(expr, Var):
            if expr.name not in state.env:
                raise ScatError(f"unbound variable: {expr.name}")
            return State(ReturnValue(state.env[expr.name]), state.env, state.kont, state.sink)
        if isinstance(expr, ScatAdd):
            return State(EvalExpr(expr.left), state.env,
                         AddLeftK(expr.right, dict(state.env), state.kont), state.sink)
        if isinstance(expr, ScatNeq):
            return State(EvalExpr(expr.left), state.env,
                         NeqLeftK(expr.right, dict(state.env), state.kont), state.sink)
        if isinstance(expr, ScatPred):
            return State(EvalExpr(expr.expr), state.env, PredK(state.kont), state.sink)
        if isinstance(expr, ScatSub):
            return State(EvalExpr(expr.left), state.env,
                         SubLeftK(expr.right, dict(state.env), state.kont), state.sink)
        if isinstance(expr, ScatMod):
            return State(EvalExpr(expr.left), state.env,
                         ModLeftK(expr.right, dict(state.env), state.kont), state.sink)
        if isinstance(expr, ScatEq):
            return State(EvalExpr(expr.left), state.env,
                         EqLeftK(expr.right, dict(state.env), state.kont), state.sink)
        raise ScatError(f"unknown expression: {expr!r}")

    if isinstance(ctrl, ReturnValue):
        value = ctrl.value
        kont  = state.kont
        if isinstance(kont, Halt):     return state
        if isinstance(kont, SuccK):
            return State(ReturnValue(PoopSucc(value)), state.env, kont.kont, state.sink)
        if isinstance(kont, AssignK):
            new_env = dict(kont.env); new_env[kont.name] = value
            return State(kont.rest, new_env, kont.kont, state.sink)
        if isinstance(kont, FlushK):
            state.sink.observe(value)
            return State(kont.rest, dict(kont.env), kont.kont, state.sink)
        if isinstance(kont, AddLeftK):
            return State(EvalExpr(kont.right), dict(kont.env),
                         AddRightK(value, kont.kont), state.sink)
        if isinstance(kont, AddRightK):
            return State(ReturnValue(poop_add(kont.left_val, value)), state.env,
                         kont.kont, state.sink)
        if isinstance(kont, NeqLeftK):
            return State(EvalExpr(kont.right), dict(kont.env),
                         NeqRightK(value, kont.kont), state.sink)
        if isinstance(kont, NeqRightK):
            return State(ReturnValue(poop_neq(kont.left_val, value)), state.env,
                         kont.kont, state.sink)
        if isinstance(kont, PredK):
            return State(ReturnValue(poop_pred(value)), state.env, kont.kont, state.sink)
        if isinstance(kont, SubLeftK):
            return State(EvalExpr(kont.right), dict(kont.env),
                         SubRightK(value, kont.kont), state.sink)
        if isinstance(kont, SubRightK):
            return State(ReturnValue(poop_sub(kont.left_val, value)), state.env,
                         kont.kont, state.sink)
        if isinstance(kont, ModLeftK):
            return State(EvalExpr(kont.right), dict(kont.env),
                         ModRightK(value, kont.kont), state.sink)
        if isinstance(kont, ModRightK):
            return State(ReturnValue(poop_mod(kont.left_val, value)), state.env,
                         kont.kont, state.sink)
        if isinstance(kont, EqLeftK):
            return State(EvalExpr(kont.right), dict(kont.env),
                         EqRightK(value, kont.kont), state.sink)
        if isinstance(kont, EqRightK):
            return State(ReturnValue(poop_eq(kont.left_val, value)), state.env,
                         kont.kont, state.sink)
        if isinstance(kont, WhileK):
            if value.to_int() == 0:
                return State(kont.rest, dict(kont.env), kont.kont, state.sink)
            return State(kont.stmt.body + (kont.stmt,) + kont.rest,
                         dict(kont.env), kont.kont, state.sink)
        raise ScatError(f"unknown continuation: {kont!r}")

    raise ScatError(f"unknown control: {ctrl!r}")


# ─────────────────────────────────────────
# CEK trace / capture
# ─────────────────────────────────────────

@dataclass(frozen=True)
class TraceEvent:
    step: int
    control_kind: str
    expr_kind: str
    kont_kind: str
    kont_depth: int
    env_keys: tuple[str, ...]
    observed_count: int
    frontend: str

    def signature(self, *, include_frontend: bool = False) -> tuple:
        row = (self.control_kind, self.expr_kind, self.kont_kind,
               self.kont_depth, self.env_keys, self.observed_count)
        return row + ((self.frontend,) if include_frontend else ())

    def to_json_obj(self) -> dict:
        return {
            "step": self.step,
            "control_kind": self.control_kind,
            "expr_kind": self.expr_kind,
            "kont_kind": self.kont_kind,
            "kont_depth": self.kont_depth,
            "env_keys": list(self.env_keys),
            "observed_count": self.observed_count,
            "frontend": self.frontend,
        }


@dataclass(frozen=True)
class TraceErrorEvent:
    step: int
    control_kind: str
    expr_kind: str
    kont_kind: str
    kont_depth: int
    env_keys: tuple[str, ...]
    observed_count: int
    frontend: str
    error_type: str
    error_message: str

    def signature(self, *, include_frontend: bool = False) -> tuple:
        row = (self.control_kind, self.expr_kind, self.kont_kind,
               self.kont_depth, self.env_keys, self.observed_count,
               self.error_type, self.error_message)
        return row + ((self.frontend,) if include_frontend else ())

    def to_json_obj(self) -> dict:
        return {
            "step": self.step,
            "control_kind": self.control_kind,
            "expr_kind": self.expr_kind,
            "kont_kind": self.kont_kind,
            "kont_depth": self.kont_depth,
            "env_keys": list(self.env_keys),
            "observed_count": self.observed_count,
            "frontend": self.frontend,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


class TraceCollector:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def __call__(self, event: TraceEvent) -> None:
        self.events.append(event)

    def signature(self, *, include_frontend: bool = False) -> tuple[tuple, ...]:
        return tuple(e.signature(include_frontend=include_frontend) for e in self.events)


@dataclass(frozen=True)
class RunCapture:
    final_state: State | None
    trace: TraceCollector
    error: TraceErrorEvent | None

    def ok(self) -> bool:
        return self.error is None


def kont_depth(kont: Kont) -> int:
    depth = 0
    current = kont
    while not isinstance(current, Halt):
        depth += 1
        if hasattr(current, "kont"):
            current = getattr(current, "kont")
        else:
            break
    return depth


def control_kind_str(control: object) -> str:
    if isinstance(control, tuple): return "StmtSeq"
    return type(control).__name__


def expr_kind_str(control: object) -> str:
    if isinstance(control, tuple): return f"len={len(control)}"
    if isinstance(control, EvalExpr): return type(control.expr).__name__
    if isinstance(control, ReturnValue): return control.value.pretty()
    return ""


def make_trace_event(step_no: int, state: State) -> TraceEvent:
    return TraceEvent(
        step=step_no,
        control_kind=control_kind_str(state.control),
        expr_kind=expr_kind_str(state.control),
        kont_kind=type(state.kont).__name__,
        kont_depth=kont_depth(state.kont),
        env_keys=tuple(sorted(state.env.keys())),
        observed_count=len(state.sink.observations),
        frontend=state.sink.frontend,
    )


def make_error_event(step_no: int, state: State, exc: Exception) -> TraceErrorEvent:
    t = make_trace_event(step_no, state)
    return TraceErrorEvent(
        step=t.step, control_kind=t.control_kind, expr_kind=t.expr_kind,
        kont_kind=t.kont_kind, kont_depth=t.kont_depth, env_keys=t.env_keys,
        observed_count=t.observed_count, frontend=t.frontend,
        error_type=type(exc).__name__, error_message=str(exc),
    )


def run_capture(
    program: list[Stmt],
    env: Mapping[str, Value] | None = None,
    *,
    frontend: str,
    max_steps: int = 200_000,
) -> RunCapture:
    collector = TraceCollector()
    state = State(tuple(program), dict(env or {}), Halt(), ObservationSink(frontend=frontend))
    for step_no in range(max_steps):
        if is_halted(state):
            return RunCapture(state, collector, None)
        collector(make_trace_event(step_no, state))
        try:
            state = step(state)
        except ScatError as exc:
            return RunCapture(None, collector, make_error_event(step_no, state, exc))

    exc2 = StepLimitError(f"step limit exceeded: {max_steps}")
    return RunCapture(None, collector, make_error_event(max_steps, state, exc2))


# ─────────────────────────────────────────
# Lexer / Parser  (ScatLang & SeaIR 共有)
# ─────────────────────────────────────────

@dataclass(frozen=True)
class Token:
    kind: str; text: str; pos: int


TOKEN_SPEC = [
    ("WS",         r"[ \t\r\n]+"),
    ("COMMENT",    r"[#;][^\n]*"),
    ("POOPN",      r"💩×[0-9]+|🌊×[0-9]+|p[0-9]+|poop[0-9]+"),
    ("SCAT_ZERO",  r"💩₀|poop0|p0"),
    ("SEA_ZERO",   r"🌊"),
    ("SCAT_SUCC",  r"💩⁺|succ\b"),
    ("SEA_SUCC",   r"〰️?|〰"),
    ("SEA_PRED",   r"↘️?|↘"),
    ("PRED",       r"pred\b"),
    ("SCAT_FLUSH", r"🚽⇐|flush\b"),
    ("SEA_FLUSH",  r"🏝️?⇐|🏝️?|🏝"),
    ("SCAT_WHILE", r"⟳|while\b"),
    ("SEA_WHILE",  r"🌀"),
    ("SEA_ASSIGN", r"⚓"),
    ("ASSIGN",     r"←|<-"),
    ("SEA_ADD",    r"🫧|➕"),
    ("ADD",        r"⊕|\+"),
    ("SEA_SUB",    r"➖"),
    ("SUB",        r"⊖|-"),
    ("SEA_MOD",    r"⚫"),
    ("MOD",        r"⊛|%"),
    ("SEA_EQ",     r"⚖️?|⚖"),
    ("EQ2",        r"=="),
    ("NEQ",        r"≠|!="),
    ("LPAREN",     r"\("),
    ("RPAREN",     r"\)"),
    ("LBRACE",     r"\{"),
    ("RBRACE",     r"\}"),
    ("SEMI",       r";"),
    ("IDENT",      r"[A-Za-z_][A-Za-z0-9_]*"),
]

TOKEN_RE = re.compile("|".join(f"(?P<{k}>{p})" for k, p in TOKEN_SPEC))


def lex(source: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(source):
        m = TOKEN_RE.match(source, pos)
        if not m:
            raise ParseError(f"unexpected character at {pos}: {source[pos:pos+10]!r}")
        kind = m.lastgroup or ""
        text = m.group(kind)
        if kind not in {"WS", "COMMENT"}:
            tokens.append(Token(kind, text, pos))
        pos = m.end()
    tokens.append(Token("EOF", "", len(source)))
    return tokens


def poop_expr_lit(n: int) -> Expr:
    expr: Expr = PoopZeroExpr()
    for _ in range(n):
        expr = PoopSuccExpr(expr)
    return expr


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens; self.i = 0

    def peek(self) -> Token: return self.tokens[self.i]
    def adv(self) -> Token:
        t = self.peek(); self.i += 1; return t
    def match(self, *kinds: str) -> Token | None:
        if self.peek().kind in kinds: return self.adv()
        return None
    def expect(self, kind: str) -> Token:
        t = self.peek()
        if t.kind != kind:
            raise ParseError(f"expected {kind}, got {t.kind} {t.text!r}")
        return self.adv()

    def parse_program(self) -> list[Stmt]:
        stmts: list[Stmt] = []
        while self.peek().kind not in {"EOF", "RBRACE"}:
            if self.match("SEMI"): continue
            stmts.append(self.parse_stmt())
            self.match("SEMI")
        return stmts

    def parse_stmt(self) -> Stmt:
        if self.match("SCAT_FLUSH", "SEA_FLUSH"):
            return Flush(self.parse_expr())
        if self.match("SCAT_WHILE", "SEA_WHILE"):
            left = self.parse_add_sub()
            self.expect("NEQ")
            right = self.parse_add_sub()
            self.expect("LBRACE")
            body = tuple(self.parse_program())
            self.expect("RBRACE")
            return While(left, right, body)
        if self.peek().kind == "IDENT":
            name = self.adv().text
            if self.match("ASSIGN", "SEA_ASSIGN"):
                return Assign(name, self.parse_expr())
        t = self.peek()
        raise ParseError(f"expected statement at {t.pos}: {t.kind} {t.text!r}")

    def parse_expr(self) -> Expr: return self.parse_eq()

    def parse_eq(self) -> Expr:
        expr = self.parse_add_sub()
        while self.peek().kind in {"EQ2", "SEA_EQ", "NEQ"}:
            op = self.adv()
            right = self.parse_add_sub()
            expr = ScatEq(expr, right) if op.kind in {"EQ2", "SEA_EQ"} else ScatNeq(expr, right)
        return expr

    def parse_add_sub(self) -> Expr:
        expr = self.parse_mod()
        while self.peek().kind in {"ADD", "SEA_ADD", "SUB", "SEA_SUB"}:
            op = self.adv()
            right = self.parse_mod()
            expr = ScatAdd(expr, right) if op.kind in {"ADD", "SEA_ADD"} else ScatSub(expr, right)
        return expr

    def parse_mod(self) -> Expr:
        expr = self.parse_unary()
        while self.peek().kind in {"MOD", "SEA_MOD"}:
            self.adv()
            expr = ScatMod(expr, self.parse_unary())
        return expr

    def parse_unary(self) -> Expr:
        if self.match("SCAT_SUCC"):
            self.expect("LPAREN"); inner = self.parse_expr(); self.expect("RPAREN")
            return PoopSuccExpr(inner)
        if self.match("SEA_SUCC"):
            return PoopSuccExpr(self.parse_unary())
        if self.match("PRED"):
            self.expect("LPAREN"); inner = self.parse_expr(); self.expect("RPAREN")
            return ScatPred(inner)
        if self.match("SEA_PRED"):
            return ScatPred(self.parse_unary())
        return self.parse_primary()

    def parse_primary(self) -> Expr:
        t = self.peek()
        if self.match("POOPN"):
            return poop_expr_lit(int(re.search(r"[0-9]+", t.text).group(0)))
        if self.match("SCAT_ZERO", "SEA_ZERO"):
            return PoopZeroExpr()
        if self.match("IDENT"):
            return Var(t.text)
        if self.match("LPAREN"):
            expr = self.parse_expr(); self.expect("RPAREN"); return expr
        raise ParseError(f"expected expression at {t.pos}: {t.kind} {t.text!r}")


def parse(source: str) -> list[Stmt]:
    return Parser(lex(source)).parse_program()


# ─────────────────────────────────────────
# Error Federation  (key names as per spec)
# ─────────────────────────────────────────

def paired_error_report(name: str, scat_src: str, sea_src: str, *, max_steps: int = 200_000) -> dict:
    scat_ast = parse(scat_src)
    sea_ast  = parse(sea_src)
    ast_equal = scat_ast == sea_ast

    scat = run_capture(scat_ast, frontend="💩ScatLang", max_steps=max_steps)
    sea  = run_capture(sea_ast,  frontend="🌊SeaIR",    max_steps=max_steps)

    if scat.error is None or sea.error is None:
        raise AssertionError(f"{name}: both programs are expected to produce an error")

    trace_equal  = scat.trace.signature() == sea.trace.signature()
    error_equal  = scat.error.signature() == sea.error.signature()
    surface_diff = (
        scat.error.signature(include_frontend=True)
        != sea.error.signature(include_frontend=True)
    )

    return {
        "case":             name,
        "ast_equal":        ast_equal,
        "trace_equal":      trace_equal,
        "error_equal":      error_equal,
        "surface_diff":     surface_diff,
        "step_count_left":  len(scat.trace.events),
        "step_count_right": len(sea.trace.events),
        "left_error":       scat.error.to_json_obj(),
        "right_error":      sea.error.to_json_obj(),
        "left_trace_tail":  [e.to_json_obj() for e in scat.trace.events[-5:]],
        "right_trace_tail": [e.to_json_obj() for e in sea.trace.events[-5:]],
    }


# ─────────────────────────────────────────
# Failure case definitions
# ─────────────────────────────────────────

ERROR_CASES = [
    (
        "mod by zero",
        "x ← 💩×3 ⊛ 💩₀",
        "x ⚓ 🌊×3 ⚫ 🌊",
        200_000,
    ),
    (
        "unbound variable",
        "🚽⇐ missing",
        "🏝️ missing",
        200_000,
    ),
    (
        "step limit / infinite loop",
        "⟳ 💩₀ ≠ 💩⁺(💩₀) { x ← 💩₀ }",
        "🌀 🌊 ≠ 〰️🌊 { x ⚓ 🌊 }",
        40,
    ),
]


# ─────────────────────────────────────────
# main
# ─────────────────────────────────────────

def main() -> None:
    reports = [
        paired_error_report(name, scat, sea, max_steps=max_steps)
        for name, scat, sea, max_steps in ERROR_CASES
    ]

    all_ok = True
    print("MysticIR Federation v0.8.5 — Error Federation")
    print("Verifying that representative failure cases travel through the same underground pipeline.\n")

    for report in reports:
        ok = report["ast_equal"] and report["trace_equal"] and report["error_equal"] and report["surface_diff"]
        all_ok = all_ok and ok
        mark = "✅" if ok else "❌"
        le = report["left_error"]
        print(f"{mark} {report['case']}")
        print(f"   step_count  : {report['step_count_left']} == {report['step_count_right']}")
        print(f"   ast_equal   : {report['ast_equal']}")
        print(f"   trace_equal : {report['trace_equal']}")
        print(f"   error_equal : {report['error_equal']}")
        print(f"   surface_diff: {report['surface_diff']}")
        print(f"   error: {le['error_type']}({le['error_message']}) @ step {le['step']}\n")

    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, "mysticir_v085_error_federation_report.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"version": "MysticIR Federation v0.8.5", "cases": reports},
                  fh, ensure_ascii=False, indent=2)

    if not all_ok:
        raise SystemExit("❌ Error Federation: one or more cases did not match")

    print("✅ v0.8.5 complete: Error Federation confirmed on representative failure cases.")
    print(f"📄 JSON report: {out_path}")


if __name__ == "__main__":
    main()
