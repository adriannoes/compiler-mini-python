"""Execute Mini-C bytecode with an explicit stack of calls."""

from dataclasses import dataclass, field
from typing import Optional

from .bytecode import (
    BINARY_KINDS, UNARY_KINDS, BytecodeFunction, BytecodeProgram, Instruction, InvalidBytecode, Op, constant_value,
)
from .bytecode_verifier import verify_bytecode
from .lexer import Token, TokenKind as Kind
from .runtime import (
    VOID, ArrayStorage, BoolValue, ExecutionError, ExecutionLimits, IntValue, Storage, Value,
    apply_binary, apply_unary,
)
from .type_checker import MAX_ARRAY_LENGTH, Type


def _index(operand: Optional[int], size: int, message: str) -> int:
    if type(operand) is not int or not 0 <= operand < size:
        raise InvalidBytecode(message)
    return operand


def _require_type(value: Value, expected: Type) -> None:
    if expected is Type.INT and isinstance(value, IntValue):
        return
    if expected is Type.BOOL and isinstance(value, BoolValue):
        return
    raise InvalidBytecode("The operand type does not match the instruction.")


@dataclass
class _Frame:
    function: BytecodeFunction
    locals: list[Storage]
    stack: list[Value] = field(default_factory=list)
    pc: int = 0

    @classmethod
    def enter(cls, function: BytecodeFunction, caller_stack: list[Value]) -> "_Frame":
        count = function.parameter_count
        if type(count) is not int or not 0 <= count <= len(function.locals):
            raise InvalidBytecode("The function has insufficient parameter slots.")
        start = len(caller_stack) - count
        if start < 0:
            raise InvalidBytecode("The call has insufficient argument values.")
        slots: list[Storage] = [None] * len(function.locals)
        for index, argument in enumerate(caller_stack[start:]):
            if function.locals[index].length is not None:
                raise InvalidBytecode("Array parameters are not supported.")
            _require_type(argument, function.locals[index].type)
            slots[index] = argument
        del caller_stack[start:]
        return cls(function, slots)

    def top(self) -> Value:
        if not self.stack:
            raise InvalidBytecode("The instruction underflows the value stack.")
        return self.stack[-1]

    def pop(self) -> Value:
        if not self.stack:
            raise InvalidBytecode("The instruction underflows the value stack.")
        return self.stack.pop()

    def jump(self, target: Optional[int]) -> None:
        self.pc = _index(target, len(self.function.code), "The jump target is outside the function.")

    def local_instruction(self, instruction: Instruction) -> None:
        index = _index(instruction.operand, len(self.locals), "The local index is outside the function.")
        local = self.function.locals[index]
        if instruction.op is Op.RESET_LOCAL:
            if local.length is None:
                self.locals[index] = None
            elif type(local.length) is int and 1 <= local.length <= MAX_ARRAY_LENGTH:
                self.locals[index] = ArrayStorage([None] * local.length)
            else:
                raise InvalidBytecode("The array length is outside the supported range.")
            return
        if local.length is not None:
            raise InvalidBytecode("A scalar instruction selected an array slot.")
        if instruction.op is Op.STORE_LOCAL:
            value = self.top()
            _require_type(value, local.type)
            self.locals[index] = value
        else:
            value = self.locals[index]
            assert not isinstance(value, ArrayStorage)
            if value is None:
                raise ExecutionError(instruction.token, f'The variable "{local.name.text}" has no value.')
            self.stack.append(value)

    def element_instruction(self, instruction: Instruction) -> None:
        slot = _index(instruction.operand, len(self.locals), "The local index is outside the function.")
        local = self.function.locals[slot]
        array = self.locals[slot]
        if not isinstance(array, ArrayStorage) or len(array.elements) != local.length:
            raise InvalidBytecode("The array slot has no active storage.")
        if instruction.op is Op.STORE_ELEMENT:
            value = self.pop()
            _require_type(value, local.type)
        index = self.top() if instruction.op is Op.CHECK_INDEX else self.pop()
        if not isinstance(index, IntValue):
            raise InvalidBytecode("An array index must be an integer.")
        offset = array.offset(index, local.name.text, instruction.token)
        if instruction.op is Op.LOAD_ELEMENT:
            self.stack.append(array.load(offset, local.name.text, instruction.token))
        elif instruction.op is Op.STORE_ELEMENT:
            array.elements[offset] = value
            self.stack.append(value)

    def load_constant(self, instruction: Instruction) -> None:
        constants = self.function.constants
        index = _index(instruction.operand, len(constants), "The constant index is outside the function.")
        self.stack.append(constant_value(constants[index], instruction.token))

    def apply_binary(self, instruction: Instruction) -> None:
        right = self.pop()
        left = self.pop()
        equality = instruction.op in (Op.EQUAL, Op.NOT_EQUAL)
        expected = Type.BOOL if equality and isinstance(right, BoolValue) else Type.INT
        _require_type(left, expected)
        _require_type(right, expected)
        self.stack.append(apply_binary(BINARY_KINDS[instruction.op], left, right, instruction.token))

    def finish(self, op: Op) -> Value:
        if op is Op.RETURN:
            result = self.pop()
            _require_type(result, self.function.result)
        else:
            if self.function.result is not Type.VOID:
                raise InvalidBytecode("A non-void function returned no value.")
            result = VOID
        if self.stack:
            raise InvalidBytecode("A return left temporary values on the stack.")
        return result


def execute_bytecode(
    program: BytecodeProgram, entry: str = "main", limits: ExecutionLimits = ExecutionLimits()
) -> Value:
    verify_bytecode(program)
    function = next((fn for fn in program.functions if fn.name.text == entry), None)
    if function is None:
        raise ExecutionError(Token(Kind.EOF, "", 1, 1), f'The entry function "{entry}" does not exist.')
    if function.parameter_count:
        raise ExecutionError(function.name, f'The entry function "{entry}" must not have parameters.')
    frames = [_Frame.enter(function, [])]
    remaining = limits.max_steps
    while True:
        frame = frames[-1]
        if frame.pc >= len(frame.function.code):
            raise InvalidBytecode("Control flow left the instruction vector.")
        instruction = frame.function.code[frame.pc]
        frame.pc += 1
        op = instruction.op
        token = instruction.token
        if op is Op.STEP:
            if remaining == 0:
                raise ExecutionError(token, "The execution step limit was reached.")
            remaining -= 1
        elif op is Op.LOAD_CONSTANT:
            frame.load_constant(instruction)
        elif op in (Op.LOAD_LOCAL, Op.STORE_LOCAL, Op.RESET_LOCAL):
            frame.local_instruction(instruction)
        elif op in (Op.CHECK_INDEX, Op.LOAD_ELEMENT, Op.STORE_ELEMENT):
            frame.element_instruction(instruction)
        elif op is Op.POP:
            frame.pop()
        elif op in UNARY_KINDS:
            value = frame.pop()
            _require_type(value, Type.INT if op is Op.NEGATE else Type.BOOL)
            frame.stack.append(apply_unary(UNARY_KINDS[op], value, token))
        elif op in BINARY_KINDS:
            frame.apply_binary(instruction)
        elif op is Op.JUMP:
            frame.jump(instruction.operand)
        elif op in (Op.JUMP_IF_FALSE, Op.JUMP_IF_TRUE):
            condition = frame.pop()
            if not isinstance(condition, BoolValue):
                raise InvalidBytecode("The operand type does not match the instruction.")
            if condition.value == (op is Op.JUMP_IF_TRUE):
                frame.jump(instruction.operand)
        elif op is Op.CALL:
            index = _index(instruction.operand, len(program.functions), "The function index is outside the program.")
            if len(frames) >= limits.max_call_depth:
                raise ExecutionError(token, "The call depth limit was reached.")
            frames.append(_Frame.enter(program.functions[index], frame.stack))
        elif op in (Op.RETURN, Op.RETURN_VOID):
            result = frame.finish(op)
            frames.pop()
            if not frames:
                return result
            if result is not VOID:
                frames[-1].stack.append(result)
        elif op is Op.UNREACHABLE:
            raise InvalidBytecode("A typed function ended without a return value.")
        else:
            raise InvalidBytecode("The opcode does not exist.")
