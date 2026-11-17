"""Parse Mini-C tokens with recursive descent."""

from collections.abc import Callable, Sequence
from typing import Optional, TypeVar

from . import ast
from .lexer import Token, TokenKind as Kind


_TYPES = {Kind.INT, Kind.BOOL, Kind.VOID}
_PRECEDENCE = {
    Kind.OR_OR: 1,
    Kind.AND_AND: 2,
    Kind.EQUAL_EQUAL: 3, Kind.BANG_EQUAL: 3,
    Kind.LESS: 4, Kind.LESS_EQUAL: 4, Kind.GREATER: 4, Kind.GREATER_EQUAL: 4,
    Kind.PLUS: 5, Kind.MINUS: 5,
    Kind.STAR: 6, Kind.SLASH: 6, Kind.PERCENT: 6,
}
_Item = TypeVar("_Item")


class ParseError(Exception):
    def __init__(self, token: Token, message: str):
        super().__init__(message)
        self.line = token.line
        self.column = token.column


class _Parser:
    def __init__(self, tokens: Sequence[Token]):
        self.tokens = tokens
        self.index = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def advance(self) -> Token:
        token = self.current
        if token.kind is not Kind.EOF:
            self.index += 1
        return token

    def take(self, kind: Kind) -> Optional[Token]:
        if self.current.kind is kind:
            return self.advance()
        return None

    def expected(self, message: str) -> ParseError:
        return ParseError(self.current, f"{message} Received {self.current.kind.name}.")

    def expect(self, kind: Kind, message: str) -> Token:
        if self.current.kind is not kind:
            raise self.expected(message)
        return self.advance()

    def type_token(self) -> Token:
        if self.current.kind not in _TYPES:
            raise self.expected("Expected a type.")
        return self.advance()

    def comma_list(self, item: Callable[[], _Item]) -> tuple[_Item, ...]:
        if self.current.kind is Kind.RIGHT_PAREN:
            return ()
        items = [item()]
        while self.take(Kind.COMMA):
            items.append(item())
        return tuple(items)

    def parameter(self) -> ast.Parameter:
        ty = self.type_token()
        name = self.expect(Kind.IDENTIFIER, "Expected a parameter name.")
        return ast.Parameter(name, ty)

    def function(self) -> ast.Function:
        ty = self.type_token()
        name = self.expect(Kind.IDENTIFIER, "Expected a function name.")
        self.expect(Kind.LEFT_PAREN, 'Expected "(" after function name.')
        parameters = self.comma_list(self.parameter)
        self.expect(Kind.RIGHT_PAREN, 'Expected ")" after parameters.')
        return ast.Function(name, ty, parameters, self.block())

    def block(self) -> ast.Block:
        opening = self.expect(Kind.LEFT_BRACE, 'Expected "{" before block.')
        statements = []
        while self.current.kind not in (Kind.RIGHT_BRACE, Kind.EOF):
            if self.current.kind in _TYPES:
                statements.append(self.declaration())
            else:
                statements.append(self.statement())
        self.expect(Kind.RIGHT_BRACE, 'Expected "}" after block.')
        return ast.Block(opening, tuple(statements))

    def declaration(self) -> ast.Variable:
        ty = self.type_token()
        name = self.expect(Kind.IDENTIFIER, "Expected a variable name.")
        length = None
        if self.take(Kind.LEFT_BRACKET):
            length = self.expect(Kind.INTEGER, "Expected an integer array length.")
            self.expect(Kind.RIGHT_BRACKET, 'Expected "]" after array length.')
            if self.current.kind is Kind.ASSIGN:
                raise ParseError(self.current, "Array initializers are not supported.")
        value = self.expression() if self.take(Kind.ASSIGN) else None
        self.expect(Kind.SEMICOLON, 'Expected ";" after declaration.')
        return ast.Variable(name, ty, value, length)

    def statement(self) -> ast.Stmt:
        start = self.current
        if start.kind is Kind.LEFT_BRACE:
            return self.block()
        if self.take(Kind.SEMICOLON):
            return ast.Empty(start)
        if self.take(Kind.RETURN):
            value = None if self.current.kind is Kind.SEMICOLON else self.expression()
            self.expect(Kind.SEMICOLON, 'Expected ";" after return value.')
            return ast.Return(start, value)
        if start.kind in (Kind.IF, Kind.WHILE):
            self.advance()
            self.expect(Kind.LEFT_PAREN, f'Expected "(" after "{start.text}".')
            condition = self.expression()
            self.expect(Kind.RIGHT_PAREN, 'Expected ")" after condition.')
            body = self.statement()
            if start.kind is Kind.WHILE:
                return ast.While(start, condition, body)
            alternative = self.statement() if self.take(Kind.ELSE) else None
            return ast.If(start, condition, body, alternative)
        value = self.expression()
        self.expect(Kind.SEMICOLON, 'Expected ";" after expression.')
        return ast.ExpressionStmt(start, value)

    def expression(self) -> ast.Expr:
        targets = []
        value = self.binary(1)
        while (equals := self.take(Kind.ASSIGN)) is not None:
            if not isinstance(value, (ast.Name, ast.Index)):
                raise ParseError(equals, 'Expected a name before "=".')
            targets.append((equals, value))
            value = self.binary(1)
        for equals, target in reversed(targets):
            value = ast.Assign(equals, target, value)
        return value

    def binary(self, minimum: int) -> ast.Expr:
        left = self.unary()
        while (precedence := _PRECEDENCE.get(self.current.kind, 0)) >= minimum:
            operator = self.advance()
            right = self.binary(precedence + 1)
            left = ast.Binary(operator, left, right)
        return left

    def unary(self) -> ast.Expr:
        operators = []
        while self.current.kind in (Kind.MINUS, Kind.BANG):
            operators.append(self.advance())
        value = self.primary()
        for operator in reversed(operators):
            value = ast.Unary(operator, value)
        return value

    def primary(self) -> ast.Expr:
        token = self.current
        if token.kind in (Kind.INTEGER, Kind.TRUE, Kind.FALSE):
            return ast.Literal(self.advance())
        if self.take(Kind.IDENTIFIER):
            if self.take(Kind.LEFT_BRACKET):
                index = self.expression()
                self.expect(Kind.RIGHT_BRACKET, 'Expected "]" after array index.')
                return ast.Index(token, index)
            if self.take(Kind.LEFT_PAREN):
                arguments = self.comma_list(self.expression)
                self.expect(Kind.RIGHT_PAREN, 'Expected ")" after arguments.')
                return ast.Call(token, arguments)
            return ast.Name(token)
        if self.take(Kind.LEFT_PAREN):
            value = self.expression()
            self.expect(Kind.RIGHT_PAREN, 'Expected ")" after expression.')
            return value
        raise self.expected("Expected an expression.")


def parse(tokens: Sequence[Token]) -> ast.Program:
    """Build a program from the complete token sequence, including EOF."""
    if not tokens or tokens[-1].kind is not Kind.EOF:
        last = tokens[-1] if tokens else Token(Kind.EOF, "", 1, 1)
        raise ParseError(last, "Expected tokens with a final EOF token.")

    parser = _Parser(tokens)
    functions = []
    try:
        while parser.index < len(tokens) - 1:
            functions.append(parser.function())
    except RecursionError:
        raise ParseError(parser.current, "Syntax nesting exceeds the parser limit.") from None
    return ast.Program(tuple(functions))
