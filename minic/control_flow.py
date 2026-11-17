"""Describe possible instruction paths without executing bytecode."""

from dataclasses import dataclass

from .bytecode import BytecodeFunction, BytecodeProgram, Instruction, InvalidBytecode, Op


CONDITIONAL_JUMPS = frozenset((Op.JUMP_IF_FALSE, Op.JUMP_IF_TRUE))
JUMPS = CONDITIONAL_JUMPS | {Op.JUMP}
TERMINALS = frozenset((Op.RETURN, Op.RETURN_VOID, Op.UNREACHABLE))


@dataclass(frozen=True)
class BasicBlock:
    start: int
    stop: int
    successors: tuple[int, ...]


@dataclass(frozen=True)
class ControlFlow:
    blocks: tuple[BasicBlock, ...]
    reachable: frozenset[int]
    instruction_successors: tuple[tuple[int, ...], ...]


def _error(function: BytecodeFunction, offset: int, message: str) -> InvalidBytecode:
    return InvalidBytecode(f'{function.name.text} at instruction {offset}: {message}')


def analyze_control_flow(function: BytecodeFunction) -> ControlFlow:
    """Partition instructions into blocks and find blocks reachable from entry."""
    size = len(function.code)
    if size == 0:
        raise _error(function, 0, "The function has no entry instruction.")

    leaders = {0}
    edges = []
    for offset, instruction in enumerate(function.code):
        if not isinstance(instruction, Instruction) or not isinstance(instruction.op, Op):
            raise _error(function, offset, "The opcode does not exist.")
        op = instruction.op
        if op in JUMPS:
            target = instruction.operand
            if type(target) is not int or not 0 <= target < size:
                raise _error(function, offset, "The jump target is outside the function.")
            leaders.add(target)
            successors = (target,) if op is Op.JUMP else tuple(dict.fromkeys((target, offset + 1)))
        elif op in TERMINALS:
            successors = ()
        else:
            successors = (offset + 1,)
        edges.append(successors)
        if (op in JUMPS or op in TERMINALS) and offset + 1 < size:
            leaders.add(offset + 1)

    visited = set()
    pending = [0]
    while pending:
        offset = pending.pop()
        if offset in visited:
            continue
        visited.add(offset)
        for target in edges[offset]:
            if target >= size:
                raise _error(function, offset, "Control flow leaves the instruction sequence.")
            pending.append(target)

    starts = sorted(leaders)
    stops = starts[1:] + [size]
    containing = [0] * size
    for start, stop in zip(starts, stops):
        containing[start:stop] = [start] * (stop - start)
    blocks = tuple(
        BasicBlock(start, stop, tuple(containing[target] if target < size else target
                                      for target in edges[stop - 1]))
        for start, stop in zip(starts, stops)
    )
    return ControlFlow(blocks, frozenset(containing[offset] for offset in visited), tuple(edges))


def format_control_flow(program: BytecodeProgram) -> str:
    """Print block ranges, successor offsets, and entry reachability."""
    lines = ["control flow"]
    for index, function in enumerate(program.functions):
        graph = analyze_control_flow(function)
        lines.append(f'function {index} "{function.name.text}"')
        for block in graph.blocks:
            state = "reachable" if block.start in graph.reachable else "unreachable"
            successors = ", ".join(str(target) if target < len(function.code) else f"outside({target})"
                                   for target in block.successors) or "none"
            lines.append(f"  block {block.start}..{block.stop - 1} {state} -> {successors}")
        lines.append("end")
    return "\n".join(lines) + "\n"
