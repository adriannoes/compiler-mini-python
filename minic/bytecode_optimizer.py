"""Simplify compiler-produced bytecode and preserve reachable source steps."""

from dataclasses import dataclass, replace
from typing import Optional

from .bytecode import (
    BINARY_KINDS, UNARY_KINDS, BytecodeFunction, BytecodeProgram, Constant, Instruction,
    IntegerConstant, Op, constant_value,
)
from .runtime import BoolValue, ExecutionError, IntValue, Value, apply_binary, apply_unary


_CONDITIONAL = {Op.JUMP_IF_FALSE, Op.JUMP_IF_TRUE}
_JUMPS = _CONDITIONAL | {Op.JUMP}
_TERMINALS = {Op.RETURN, Op.RETURN_VOID, Op.UNREACHABLE}


@dataclass(frozen=True)
class _Known:
    value: Value
    producer: int


def _operand(instruction: Instruction) -> int:
    assert instruction.operand is not None
    return instruction.operand


def _compact(edits: list[Optional[Instruction]]) -> list[Instruction]:
    # A jump to a deleted instruction resumes at the next instruction that survives.
    offsets = []
    code = []
    for instruction in edits:
        offsets.append(len(code))
        if instruction is not None:
            code.append(instruction)
    for i, instruction in enumerate(code):
        if instruction.op in _JUMPS:
            code[i] = replace(instruction, operand=offsets[_operand(instruction)])
    return code


def _fold(instruction: Instruction, known: list[_Known]) -> Optional[tuple[int, Value]]:
    op = instruction.op
    try:
        if op in UNARY_KINDS and known:
            return 1, apply_unary(UNARY_KINDS[op], known[-1].value, instruction.token)
        if op in BINARY_KINDS and len(known) >= 2:
            return 2, apply_binary(BINARY_KINDS[op], known[-2].value, known[-1].value, instruction.token)
    except ExecutionError:
        # Leave the operation in place so the VM can report the error if it reaches it.
        return None
    return None


def _folded_constant(value: Value) -> Constant:
    if isinstance(value, BoolValue):
        return value.value
    assert isinstance(value, IntValue)
    return IntegerConstant(str(abs(value.value)), negative=value.value < 0)


def _rewrite_blocks(function: BytecodeFunction) -> bool:
    entries = set()
    for i, instruction in enumerate(function.code):
        if instruction.op in _JUMPS:
            entries.add(_operand(instruction))
        if instruction.op in _JUMPS or instruction.op in _TERMINALS:
            entries.add(i + 1)

    edits: list[Optional[Instruction]] = list(function.code)
    known: list[_Known] = []
    for i, instruction in enumerate(function.code):
        if i in entries:
            known.clear()
        op = instruction.op
        if op is Op.STEP:
            continue
        if op is Op.LOAD_CONSTANT:
            try:
                value = constant_value(function.constants[_operand(instruction)], instruction.token)
            except ExecutionError:
                known.clear()
            else:
                known.append(_Known(value, i))
        elif op is Op.POP and known:
            edits[known.pop().producer] = None
            edits[i] = None
        elif op in _CONDITIONAL and known:
            condition = known[-1]
            if isinstance(condition.value, BoolValue):
                edits[condition.producer] = None
                taken = condition.value.value == (op is Op.JUMP_IF_TRUE)
                edits[i] = replace(instruction, op=Op.JUMP) if taken else None
            known.clear()
        elif op is Op.JUMP and instruction.operand == i + 1:
            edits[i] = None
            known.clear()
        else:
            folded = _fold(instruction, known)
            if folded is None:
                known.clear()
                continue
            count, result = folded
            for _ in range(count):
                edits[known.pop().producer] = None
            index = len(function.constants)
            function.constants.append(_folded_constant(result))
            edits[i] = Instruction(Op.LOAD_CONSTANT, instruction.token, index)
            known.append(_Known(result, i))

    if edits == function.code:
        return False
    function.code = _compact(edits)
    return True


def _thread_jumps(code: list[Instruction]) -> bool:
    changed = False
    for i, instruction in enumerate(code):
        if instruction.op in _JUMPS:
            target = _operand(instruction)
            # Every loop in compiler-produced bytecode has a STEP before its back edge repeats.
            while code[target].op is Op.JUMP and code[target].operand != target:
                target = _operand(code[target])
            if target != instruction.operand:
                code[i] = replace(instruction, operand=target)
                changed = True
    return changed


def _remove_unreachable(function: BytecodeFunction) -> bool:
    reachable = set()
    pending = [0] if function.code else []
    while pending:
        i = pending.pop()
        if i in reachable:
            continue
        reachable.add(i)
        instruction = function.code[i]
        if instruction.op in _JUMPS:
            pending.append(_operand(instruction))
        if instruction.op is not Op.JUMP and instruction.op not in _TERMINALS:
            pending.append(i + 1)
    if len(reachable) == len(function.code):
        return False
    function.code = _compact([instruction if i in reachable else None for i, instruction in enumerate(function.code)])
    return True


def _optimize_function(original: BytecodeFunction) -> BytecodeFunction:
    function = replace(original, locals=original.locals.copy(), constants=original.constants.copy(),
                       code=original.code.copy())
    while True:
        rewritten = _rewrite_blocks(function)
        threaded = _thread_jumps(function.code)
        pruned = _remove_unreachable(function)
        if not (rewritten or threaded or pruned):
            return function


def optimize_bytecode(program: BytecodeProgram) -> BytecodeProgram:
    """Return a separate program with optimized instructions for every function."""
    return BytecodeProgram(tuple(_optimize_function(function) for function in program.functions))
