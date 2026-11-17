"""Execute a checked scalar Mini-C syntax tree."""

from dataclasses import dataclass, field
from typing import Generator, Optional, Union

from . import ast
from .lexer import Token, TokenKind as Kind
from .resolver import Declaration, Resolution
from .runtime import VOID, BoolValue, ExecutionError, ExecutionLimits, Value, binary, integer_literal, unary
from .type_checker import check_types


@dataclass
class _Frame:
    function: ast.Function
    depth: int
    slots: dict[Declaration, Optional[Value]] = field(default_factory=dict)


_Node = Union[ast.Expr, ast.Stmt]
_Visit = Generator[Union[_Node, _Frame], Optional[Value], Optional[Value]]


class _Interpreter:
    def __init__(self, resolution: Resolution, limits: ExecutionLimits):
        self.bindings = resolution.bindings
        self.steps_left = limits.max_steps
        self.max_depth = limits.max_call_depth

    def step(self, token: Token) -> None:
        if self.steps_left == 0:
            raise ExecutionError(token, "The execution step limit was reached.")
        self.steps_left -= 1

    def visit(self, frame: _Frame, node: _Node) -> _Visit:
        self.step(node.token)
        if isinstance(node, ast.Expr):
            return self.expression(frame, node)
        return self.statement(frame, node)

    def run(self, entry: ast.Function) -> Value:
        """Resume each AST visit with the result from its most recent child."""
        frame = _Frame(entry, 1)
        pending = [(frame, self.visit(frame, entry.body))]
        result = None
        while pending:
            frame, visitor = pending[-1]
            try:
                child = visitor.send(result)
            except StopIteration as done:
                result = done.value
                pending.pop()
            else:
                # A new frame starts at its function body. Other children use the caller's frame.
                if isinstance(child, _Frame):
                    frame = child
                    child = frame.function.body
                pending.append((frame, self.visit(frame, child)))
                result = None
        return VOID if result is None else result

    def statement(self, frame: _Frame, stmt: ast.Stmt) -> _Visit:
        # None continues the block. Every return carries a value, including VOID.
        if isinstance(stmt, ast.Block):
            for child in stmt.statements:
                returned = yield child
                if returned is not None:
                    return returned
        elif isinstance(stmt, ast.Variable):
            frame.slots[stmt] = None
            if stmt.initializer is not None:
                frame.slots[stmt] = yield stmt.initializer
        elif isinstance(stmt, ast.ExpressionStmt):
            yield stmt.value
        elif isinstance(stmt, ast.Return):
            return VOID if stmt.value is None else (yield stmt.value)
        elif isinstance(stmt, ast.If):
            condition = yield stmt.condition
            assert isinstance(condition, BoolValue)
            branch = stmt.then_branch if condition.value else stmt.else_branch
            if branch is not None:
                return (yield branch)
        elif isinstance(stmt, ast.While):
            while True:
                condition = yield stmt.condition
                assert isinstance(condition, BoolValue)
                if not condition.value:
                    break
                returned = yield stmt.body
                if returned is not None:
                    return returned
        elif not isinstance(stmt, ast.Empty):
            raise TypeError(f"Unknown statement: {type(stmt).__name__}.")
        return None

    def expression(self, frame: _Frame, expr: ast.Expr) -> _Visit:
        token = expr.token
        if isinstance(expr, ast.Literal):
            if token.kind is Kind.INTEGER:
                return integer_literal(token.text, False, token)
            return BoolValue(token.kind is Kind.TRUE)
        if isinstance(expr, ast.Name):
            value = frame.slots[self.bindings[expr].symbol.declaration]
            if value is None:
                raise ExecutionError(token, f'The variable "{token.text}" has no value.')
            return value
        if isinstance(expr, ast.Assign):
            value = yield expr.value
            frame.slots[self.bindings[expr.target].symbol.declaration] = value
            return value
        if isinstance(expr, ast.Unary):
            operand = expr.operand
            if token.kind is Kind.MINUS and isinstance(operand, ast.Literal) and operand.token.kind is Kind.INTEGER:
                self.step(operand.token)
                return integer_literal(operand.token.text, True, token)
            value = yield operand
            assert value is not None
            return unary(token, value)
        if isinstance(expr, ast.Binary):
            left = yield expr.left
            assert left is not None
            if token.kind in (Kind.AND_AND, Kind.OR_OR):
                assert isinstance(left, BoolValue)
                if token.kind is Kind.AND_AND and not left.value:
                    return left
                if token.kind is Kind.OR_OR and left.value:
                    return left
            right = yield expr.right
            assert right is not None
            return binary(token, left, right)
        if isinstance(expr, ast.Call):
            function = self.bindings[expr].symbol.declaration
            assert isinstance(function, ast.Function)
            arguments = []
            for argument in expr.arguments:
                arguments.append((yield argument))
            if frame.depth >= self.max_depth:
                raise ExecutionError(token, "The call depth limit was reached.")
            callee = _Frame(function, frame.depth + 1, dict(zip(function.parameters, arguments)))
            returned = yield callee
            return VOID if returned is None else returned
        raise TypeError(f"Unknown expression: {type(expr).__name__}.")


def interpret(program: ast.Program, entry: str = "main", limits: ExecutionLimits = ExecutionLimits()) -> Value:
    analysis = check_types(program)
    for function in program.functions:
        if function.token.text == entry:
            if function.parameters:
                raise ExecutionError(function.token, f'The entry function "{entry}" must not have parameters.')
            return _Interpreter(analysis.resolution, limits).run(function)
    start = Token(Kind.EOF, "", 1, 1)
    raise ExecutionError(start, f'The entry function "{entry}" does not exist.')
