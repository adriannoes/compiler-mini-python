"""Represent Mini-C syntax with positioned nodes."""

from dataclasses import dataclass
from typing import Optional, Union

from .lexer import Token


@dataclass(frozen=True, eq=False)
class Node:
    token: Token


class Expr(Node):
    pass


class Literal(Expr):
    pass


class Name(Expr):
    pass


@dataclass(frozen=True, eq=False)
class Index(Expr):
    index: Expr


@dataclass(frozen=True, eq=False)
class Call(Expr):
    arguments: tuple[Expr, ...]


@dataclass(frozen=True, eq=False)
class Unary(Expr):
    operand: Expr


@dataclass(frozen=True, eq=False)
class Binary(Expr):
    left: Expr
    right: Expr


@dataclass(frozen=True, eq=False)
class Assign(Expr):
    target: Union[Name, Index]
    value: Expr


class Stmt(Node):
    pass


@dataclass(frozen=True, eq=False)
class Block(Stmt):
    statements: tuple[Stmt, ...]


@dataclass(frozen=True, eq=False)
class Variable(Stmt):
    type_token: Token
    initializer: Optional[Expr]
    length: Optional[Token] = None


@dataclass(frozen=True, eq=False)
class Return(Stmt):
    value: Optional[Expr]


class Empty(Stmt):
    pass


@dataclass(frozen=True, eq=False)
class ExpressionStmt(Stmt):
    value: Expr


@dataclass(frozen=True, eq=False)
class If(Stmt):
    condition: Expr
    then_branch: Stmt
    else_branch: Optional[Stmt]


@dataclass(frozen=True, eq=False)
class While(Stmt):
    condition: Expr
    body: Stmt


@dataclass(frozen=True, eq=False)
class Parameter(Node):
    type_token: Token


@dataclass(frozen=True, eq=False)
class Function(Node):
    return_type: Token
    parameters: tuple[Parameter, ...]
    body: Block


@dataclass(frozen=True)
class Program:
    functions: tuple[Function, ...]
