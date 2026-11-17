"""Scalar values and checked arithmetic for Mini-C execution."""

from dataclasses import dataclass
from enum import Enum
from typing import Union

from .lexer import Token, TokenKind as Kind


MIN_INT = -(1 << 63)
MAX_INT = (1 << 63) - 1


class ExecutionError(Exception):
    def __init__(self, token: Token, message: str):
        super().__init__(message)
        self.line = token.line
        self.column = token.column


@dataclass(frozen=True)
class IntValue:
    value: int

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class BoolValue:
    value: bool

    def __str__(self) -> str:
        return "true" if self.value else "false"


class VoidValue(Enum):
    VOID = "void"


VOID = VoidValue.VOID
Value = Union[IntValue, BoolValue, VoidValue]


@dataclass(frozen=True)
class ExecutionLimits:
    max_steps: int = 1_000_000
    max_call_depth: int = 128

    def __post_init__(self):
        for limit in (self.max_steps, self.max_call_depth):
            if type(limit) is not int or limit <= 0:
                raise ValueError("Execution limits must be greater than zero.")


def integer_literal(digits: str, negative: bool, token: Token) -> IntValue:
    significant = digits.lstrip("0") or "0"
    if len(significant) <= 19:
        magnitude = int(significant)
        value = -magnitude if negative else magnitude
        if MIN_INT <= value <= MAX_INT:
            return IntValue(value)
    raise ExecutionError(token, "The integer literal is outside the signed 64-bit range.")


def _checked(value: int, token: Token) -> IntValue:
    if MIN_INT <= value <= MAX_INT:
        return IntValue(value)
    raise ExecutionError(token, "Integer arithmetic exceeds the signed 64-bit range.")


def unary(operator: Token, operand: Value) -> Value:
    if operator.kind is Kind.MINUS and isinstance(operand, IntValue):
        return _checked(-operand.value, operator)
    if operator.kind is Kind.BANG and isinstance(operand, BoolValue):
        return BoolValue(not operand.value)
    raise AssertionError("Invalid operands for a checked unary expression.")


def binary(operator: Token, left: Value, right: Value) -> Value:
    kind = operator.kind
    if kind is Kind.EQUAL_EQUAL:
        return BoolValue(left == right)
    if kind is Kind.BANG_EQUAL:
        return BoolValue(left != right)
    if isinstance(left, BoolValue) and isinstance(right, BoolValue):
        if kind is Kind.AND_AND:
            return BoolValue(left.value and right.value)
        if kind is Kind.OR_OR:
            return BoolValue(left.value or right.value)

    assert isinstance(left, IntValue) and isinstance(right, IntValue)
    a, b = left.value, right.value
    if kind is Kind.PLUS:
        return _checked(a + b, operator)
    if kind is Kind.MINUS:
        return _checked(a - b, operator)
    if kind is Kind.STAR:
        return _checked(a * b, operator)
    if kind in (Kind.SLASH, Kind.PERCENT):
        if b == 0:
            raise ExecutionError(operator, "The divisor is zero.")
        quotient = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            quotient = -quotient
        # Both division and remainder require a representable quotient.
        result = _checked(quotient, operator)
        return result if kind is Kind.SLASH else IntValue(a - quotient * b)
    if kind is Kind.LESS:
        return BoolValue(a < b)
    if kind is Kind.LESS_EQUAL:
        return BoolValue(a <= b)
    if kind is Kind.GREATER:
        return BoolValue(a > b)
    if kind is Kind.GREATER_EQUAL:
        return BoolValue(a >= b)
    raise AssertionError("Invalid operator for a checked binary expression.")
