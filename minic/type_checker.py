"""Check scalar Mini-C types and return paths before execution."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from . import ast
from .lexer import Token, TokenKind as Kind
from .resolver import AnalysisError, Resolution, resolve_names


class Type(Enum):
    INT = "int"
    BOOL = "bool"
    VOID = "void"


_TYPE_KEYWORDS = {Kind.INT: Type.INT, Kind.BOOL: Type.BOOL, Kind.VOID: Type.VOID}


def _declared_type(token: Token) -> Type:
    if token.kind not in _TYPE_KEYWORDS:
        raise AnalysisError(token, "Expected a type keyword.")
    return _TYPE_KEYWORDS[token.kind]


def _value_type(token: Token) -> Type:
    ty = _declared_type(token)
    if ty is Type.VOID:
        raise AnalysisError(token, "Variables and parameters cannot have type void.")
    return ty


def _require(actual: Type, expected: Type, token: Token) -> None:
    if actual is not expected:
        raise AnalysisError(token, f"Expected type {expected.value}. Received {actual.value}.")


def _binary_type(operator: Token, left: Type, right: Type) -> Type:
    kind = operator.kind
    if kind in (Kind.PLUS, Kind.MINUS, Kind.STAR, Kind.SLASH, Kind.PERCENT):
        operand, result = Type.INT, Type.INT
    elif kind in (Kind.LESS, Kind.LESS_EQUAL, Kind.GREATER, Kind.GREATER_EQUAL):
        operand, result = Type.INT, Type.BOOL
    elif kind in (Kind.AND_AND, Kind.OR_OR):
        operand, result = Type.BOOL, Type.BOOL
    elif kind in (Kind.EQUAL_EQUAL, Kind.BANG_EQUAL):
        if Type.VOID in (left, right):
            raise AnalysisError(operator, "Equality requires int or bool operands.")
        operand, result = left, Type.BOOL
    else:
        raise AnalysisError(operator, "Expected a binary operator.")
    _require(left, operand, operator)
    _require(right, operand, operator)
    return result


@dataclass(frozen=True)
class Signature:
    result: Type
    parameters: tuple[Type, ...]


@dataclass
class TypeAnalysis:
    resolution: Resolution
    types: dict[ast.Expr, Type]


class _Checker:
    def __init__(self, resolution: Resolution, signatures: dict[ast.Function, Signature]):
        self.resolution = resolution
        self.signatures = signatures
        self.types: dict[ast.Expr, Type] = {}

    def signature(self, call: ast.Call) -> Signature:
        declaration = self.resolution.bindings[call].symbol.declaration
        assert isinstance(declaration, ast.Function)
        return self.signatures[declaration]

    def expression(self, root: ast.Expr) -> Type:
        # Finish each child before its parent. A call checks each argument before the next one.
        pending: list[tuple[ast.Expr, bool, Optional[Type]]] = [(root, False, None)]
        while pending:
            expr, finish, expected = pending.pop()
            if finish:
                ty = self.result_type(expr)
                if expected is not None:
                    _require(ty, expected, expr.token)
                self.types[expr] = ty
                continue
            pending.append((expr, True, expected))
            if isinstance(expr, ast.Binary):
                pending.extend(((expr.right, False, None), (expr.left, False, None)))
            elif isinstance(expr, ast.Unary):
                pending.append((expr.operand, False, None))
            elif isinstance(expr, ast.Assign):
                pending.extend(((expr.value, False, None), (expr.target, False, None)))
            elif isinstance(expr, ast.Call):
                parameters = self.signature(expr).parameters
                count = len(parameters)
                if len(expr.arguments) != count:
                    noun = "argument" if count == 1 else "arguments"
                    raise AnalysisError(expr.token, f'Function "{expr.token.text}" expects {count} {noun}. '
                                                    f'Received {len(expr.arguments)}.')
                for arg, parameter in zip(reversed(expr.arguments), reversed(parameters)):
                    pending.append((arg, False, parameter))
        return self.types[root]

    def result_type(self, expr: ast.Expr) -> Type:
        if isinstance(expr, ast.Literal):
            return Type.INT if expr.token.kind is Kind.INTEGER else Type.BOOL
        if isinstance(expr, ast.Name):
            declaration = self.resolution.bindings[expr].symbol.declaration
            assert isinstance(declaration, (ast.Variable, ast.Parameter))
            return _value_type(declaration.type_token)
        if isinstance(expr, ast.Call):
            return self.signature(expr).result
        if isinstance(expr, ast.Assign):
            target = self.types[expr.target]
            _require(self.types[expr.value], target, expr.token)
            return target
        if isinstance(expr, ast.Unary):
            if expr.token.kind is Kind.BANG:
                operand = Type.BOOL
            elif expr.token.kind is Kind.MINUS:
                operand = Type.INT
            else:
                raise AnalysisError(expr.token, "Expected a unary operator.")
            _require(self.types[expr.operand], operand, expr.token)
            return operand
        if isinstance(expr, ast.Binary):
            return _binary_type(expr.token, self.types[expr.left], self.types[expr.right])
        raise TypeError(f"Unknown expression: {type(expr).__name__}.")

    def statement(self, stmt: ast.Stmt, result: Type) -> bool:
        """Check the statement and report whether every path returns."""
        if isinstance(stmt, ast.Block):
            returns = False
            for child in stmt.statements:
                if self.statement(child, result):
                    returns = True
            return returns
        if isinstance(stmt, ast.If):
            _require(self.expression(stmt.condition), Type.BOOL, stmt.condition.token)
            then_returns = self.statement(stmt.then_branch, result)
            else_returns = stmt.else_branch is not None and self.statement(stmt.else_branch, result)
            return then_returns and else_returns
        if isinstance(stmt, ast.While):
            _require(self.expression(stmt.condition), Type.BOOL, stmt.condition.token)
            self.statement(stmt.body, result)
        elif isinstance(stmt, ast.Variable):
            ty = _value_type(stmt.type_token)
            if stmt.initializer is not None:
                _require(self.expression(stmt.initializer), ty, stmt.initializer.token)
        elif isinstance(stmt, ast.ExpressionStmt):
            self.expression(stmt.value)
        elif isinstance(stmt, ast.Return):
            if result is Type.VOID and stmt.value is not None:
                raise AnalysisError(stmt.token, "A void function cannot return a value.")
            if result is not Type.VOID and stmt.value is None:
                raise AnalysisError(stmt.token, "A non-void function must return a value.")
            if stmt.value is not None:
                _require(self.expression(stmt.value), result, stmt.token)
            return True
        return False


def check_types(program: ast.Program) -> TypeAnalysis:
    resolution = resolve_names(program)
    signatures = {
        function: Signature(_declared_type(function.return_type),
                            tuple(_value_type(p.type_token) for p in function.parameters))
        for function in program.functions
    }
    checker = _Checker(resolution, signatures)
    for function, signature in signatures.items():
        returns = checker.statement(function.body, signature.result)
        if signature.result is not Type.VOID and not returns:
            raise AnalysisError(function.token, f'Function "{function.token.text}" does not guarantee a return value.')
    return TypeAnalysis(resolution, checker.types)
