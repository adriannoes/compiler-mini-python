"""Bind Mini-C name uses to declarations in lexical scopes."""

from dataclasses import dataclass, field
from typing import Optional, Union

from . import ast
from .lexer import Token


class AnalysisError(Exception):
    def __init__(self, token: Token, message: str):
        super().__init__(message)
        self.line = token.line
        self.column = token.column


Declaration = Union[ast.Function, ast.Parameter, ast.Variable]


@dataclass(frozen=True)
class Symbol:
    number: int
    scope: int
    declaration: Declaration


@dataclass
class Scope:
    kind: str
    parent: Optional[int]
    line: int
    column: int
    names: dict[str, Symbol] = field(default_factory=dict)


@dataclass(frozen=True)
class Binding:
    kind: str
    scope: int
    symbol: Symbol


@dataclass
class Resolution:
    scopes: list[Scope]
    symbols: list[Symbol]
    bindings: dict[ast.Expr, Binding]


class _Resolver:
    def __init__(self):
        self.result = Resolution([Scope("GLOBAL", None, 1, 1)], [], {})

    def child_scope(self, kind: str, parent: int, token: Token) -> int:
        number = len(self.result.scopes)
        self.result.scopes.append(Scope(kind, parent, token.line, token.column))
        return number

    def declare(self, scope: int, node: Declaration) -> None:
        token = node.token
        names = self.result.scopes[scope].names
        if token.text in names:
            raise AnalysisError(token, f'Name "{token.text}" is already declared in this scope.')
        symbol = Symbol(len(self.result.symbols), scope, node)
        names[token.text] = symbol
        self.result.symbols.append(symbol)

    def bind(self, scope: int, node: ast.Expr, kind: str) -> None:
        token = node.token
        current = self.result.scopes[scope]
        while token.text not in current.names:
            if current.parent is None:
                raise AnalysisError(token, f'Undeclared name "{token.text}".')
            current = self.result.scopes[current.parent]
        symbol = current.names[token.text]
        function = isinstance(symbol.declaration, ast.Function)
        if kind == "Call" and not function:
            raise AnalysisError(token, f'Name "{token.text}" does not refer to a function.')
        if kind != "Call" and function:
            raise AnalysisError(token, f'Name "{token.text}" does not refer to a variable or parameter.')
        self.result.bindings[node] = Binding(kind, scope, symbol)

    def expression(self, scope: int, root: ast.Expr) -> None:
        pending = [root]
        while pending:
            expr = pending.pop()
            if isinstance(expr, ast.Name):
                self.bind(scope, expr, "Read")
            elif isinstance(expr, ast.Index):
                self.bind(scope, expr, "Read")
                pending.append(expr.index)
            elif isinstance(expr, ast.Call):
                self.bind(scope, expr, "Call")
                pending.extend(reversed(expr.arguments))
            elif isinstance(expr, ast.Assign):
                self.bind(scope, expr.target, "Write")
                pending.append(expr.value)
                if isinstance(expr.target, ast.Index):
                    pending.append(expr.target.index)
            elif isinstance(expr, ast.Unary):
                pending.append(expr.operand)
            elif isinstance(expr, ast.Binary):
                pending.extend((expr.right, expr.left))

    def block(self, scope: int, block: ast.Block) -> None:
        for statement in block.statements:
            if isinstance(statement, ast.Variable):
                self.declare(scope, statement)
                if statement.initializer is not None:
                    self.expression(scope, statement.initializer)
            else:
                self.statement(scope, statement)

    def statement(self, scope: int, stmt: ast.Stmt) -> None:
        if isinstance(stmt, ast.Block):
            self.block(self.child_scope("BLOCK", scope, stmt.token), stmt)
        elif isinstance(stmt, (ast.ExpressionStmt, ast.Return)):
            if stmt.value is not None:
                self.expression(scope, stmt.value)
        elif isinstance(stmt, (ast.If, ast.While)):
            self.expression(scope, stmt.condition)
            if isinstance(stmt, ast.While):
                self.statement(scope, stmt.body)
            else:
                self.statement(scope, stmt.then_branch)
                if stmt.else_branch is not None:
                    self.statement(scope, stmt.else_branch)
        elif isinstance(stmt, ast.Variable):
            raise AnalysisError(stmt.type_token, "A variable declaration must appear directly in a block.")


def resolve_names(program: ast.Program) -> Resolution:
    resolver = _Resolver()
    for function in program.functions:
        resolver.declare(0, function)
    for function in program.functions:
        scope = resolver.child_scope("FUNCTION", 0, function.token)
        for parameter in function.parameters:
            resolver.declare(scope, parameter)
        resolver.block(scope, function.body)
    return resolver.result


def format_resolution(result: Resolution) -> str:
    lines = ["Resolution"]
    for number, scope in enumerate(result.scopes):
        parent = "" if scope.parent is None else f" parent=#{scope.parent}"
        lines.append(f"  Scope #{number} {scope.kind}{parent} @{scope.line}:{scope.column}")
    for symbol in result.symbols:
        declaration = symbol.declaration
        kind = type(declaration).__name__.upper()
        token = declaration.token
        lines.append(f'  Symbol #{symbol.number} {kind} "{token.text}" scope=#{symbol.scope} '
                     f'@{token.line}:{token.column}')
    for node, binding in result.bindings.items():
        use = node.token
        symbol = binding.symbol
        target = symbol.declaration.token
        lines.append(f'  {binding.kind} "{use.text}" scope=#{binding.scope} @{use.line}:{use.column} '
                     f'-> Symbol #{symbol.number} @{target.line}:{target.column}')
    return "\n".join(lines) + "\n"
