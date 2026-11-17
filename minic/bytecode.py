"""Represent and print stack instructions for scalar Mini-C programs."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Union

from .lexer import Token, TokenKind as Kind
from .type_checker import Type


class Op(Enum):
    STEP = auto()
    LOAD_CONSTANT = auto()
    LOAD_LOCAL = auto()
    STORE_LOCAL = auto()
    RESET_LOCAL = auto()
    POP = auto()
    NEGATE = auto()
    NOT = auto()
    ADD = auto()
    SUBTRACT = auto()
    MULTIPLY = auto()
    DIVIDE = auto()
    REMAINDER = auto()
    EQUAL = auto()
    NOT_EQUAL = auto()
    LESS = auto()
    LESS_EQUAL = auto()
    GREATER = auto()
    GREATER_EQUAL = auto()
    JUMP = auto()
    JUMP_IF_FALSE = auto()
    JUMP_IF_TRUE = auto()
    CALL = auto()
    RETURN = auto()
    RETURN_VOID = auto()
    UNREACHABLE = auto()


BINARY_OPS = {
    Kind.PLUS: Op.ADD, Kind.MINUS: Op.SUBTRACT, Kind.STAR: Op.MULTIPLY,
    Kind.SLASH: Op.DIVIDE, Kind.PERCENT: Op.REMAINDER,
    Kind.EQUAL_EQUAL: Op.EQUAL, Kind.BANG_EQUAL: Op.NOT_EQUAL,
    Kind.LESS: Op.LESS, Kind.LESS_EQUAL: Op.LESS_EQUAL,
    Kind.GREATER: Op.GREATER, Kind.GREATER_EQUAL: Op.GREATER_EQUAL,
}


@dataclass(frozen=True)
class Instruction:
    op: Op
    token: Token
    operand: Optional[int] = None


@dataclass(frozen=True)
class IntegerConstant:
    digits: str
    negative: bool = False


Constant = Union[IntegerConstant, bool]


@dataclass(frozen=True)
class Local:
    name: Token
    type: Type


@dataclass
class BytecodeFunction:
    name: Token
    result: Type
    parameter_count: int
    locals: list[Local] = field(default_factory=list)
    constants: list[Constant] = field(default_factory=list)
    code: list[Instruction] = field(default_factory=list)


@dataclass(frozen=True)
class BytecodeProgram:
    functions: tuple[BytecodeFunction, ...]


def _position(token: Token) -> str:
    return f"@{token.line}:{token.column}"


def format_bytecode(program: BytecodeProgram) -> str:
    lines = ["bytecode"]
    for function_index, function in enumerate(program.functions):
        lines.append(f'function {function_index} "{function.name.text}" {function.result.value} '
                     f'parameters={function.parameter_count} {_position(function.name)}')
        for slot, local in enumerate(function.locals):
            lines.append(f'  local {slot} "{local.name.text}" {local.type.value} {_position(local.name)}')
        for index, constant in enumerate(function.constants):
            if isinstance(constant, IntegerConstant):
                sign = "-" if constant.negative else ""
                value = f'int "{sign}{constant.digits}"'
            else:
                value = "bool true" if constant else "bool false"
            lines.append(f"  constant {index} {value}")
        for offset, instruction in enumerate(function.code):
            operand = "" if instruction.operand is None else f" {instruction.operand}"
            lines.append(f"  {offset} {instruction.op.name}{operand} {_position(instruction.token)}")
        lines.append("end")
    return "\n".join(lines) + "\n"
