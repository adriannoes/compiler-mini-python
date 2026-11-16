"""Format Mini-C syntax trees for the --ast command."""

from dataclasses import dataclass
from typing import Union

from . import ast
from .lexer import Token, TokenKind


@dataclass(frozen=True)
class _Branch:
    label: str
    child: ast.Node


_Entry = Union[ast.Program, ast.Node, Token, _Branch]


def _describe(entry: _Entry) -> tuple[str, tuple[_Entry, ...]]:
    if isinstance(entry, ast.Program):
        return "Program", entry.functions
    if isinstance(entry, _Branch):
        return entry.label, (entry.child,)
    if isinstance(entry, Token):
        return f"Type {entry.kind.name}", ()
    token = entry.token
    if isinstance(entry, ast.Function):
        return f'Function "{token.text}"', (entry.return_type, *entry.parameters, entry.body)
    if isinstance(entry, ast.Parameter):
        return f'Parameter "{token.text}"', (entry.type_token,)
    if isinstance(entry, ast.Block):
        return "Block", entry.statements
    if isinstance(entry, ast.Variable):
        children = (entry.type_token,)
        if entry.initializer is not None:
            children += (entry.initializer,)
        return f'Variable "{token.text}"', children
    if isinstance(entry, ast.Return):
        return "Return", () if entry.value is None else (entry.value,)
    if isinstance(entry, ast.Empty):
        return "Empty", ()
    if isinstance(entry, ast.ExpressionStmt):
        return "Expression", (entry.value,)
    if isinstance(entry, ast.If):
        branches = (_Branch("Condition", entry.condition), _Branch("Then", entry.then_branch))
        if entry.else_branch is not None:
            branches += (_Branch("Else", entry.else_branch),)
        return "If", branches
    if isinstance(entry, ast.While):
        return "While", (_Branch("Condition", entry.condition), _Branch("Body", entry.body))
    if isinstance(entry, ast.Name):
        return f'Name "{token.text}"', ()
    if isinstance(entry, ast.Literal):
        if token.kind is TokenKind.INTEGER:
            return f'Integer "{token.text}"', ()
        return f"Boolean {token.text}", ()
    if isinstance(entry, ast.Call):
        return f'Call "{token.text}"', entry.arguments
    if isinstance(entry, ast.Unary):
        return f"Unary {token.kind.name}", (entry.operand,)
    if isinstance(entry, ast.Binary):
        return f"Binary {token.kind.name}", (entry.left, entry.right)
    if isinstance(entry, ast.Assign):
        return "Assign", (entry.target, entry.value)
    raise TypeError(f"Unknown AST node: {type(entry).__name__}.")


def format_ast(program: ast.Program) -> str:
    lines = []
    pending: list[tuple[int, _Entry]] = [(0, program)]
    while pending:
        depth, entry = pending.pop()
        label, children = _describe(entry)
        if isinstance(entry, (Token, ast.Node)):
            token = entry if isinstance(entry, Token) else entry.token
            label += f" @{token.line}:{token.column}"
        lines.append("  " * depth + label + "\n")
        pending.extend((depth + 1, child) for child in reversed(children))
    return "".join(lines)
