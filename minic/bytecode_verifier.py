"""Check bytecode structure and operand types before execution."""

from collections import deque
from dataclasses import dataclass

from .bytecode import BytecodeFunction, BytecodeProgram, Instruction, IntegerConstant, InvalidBytecode, Local, Op
from .control_flow import CONDITIONAL_JUMPS, JUMPS, ControlFlow, analyze_control_flow
from .lexer import Token, TokenKind
from .type_checker import MAX_ARRAY_LENGTH, Type


_SCALAR = frozenset((Type.INT, Type.BOOL))
_SCALAR_ACCESS = frozenset((Op.LOAD_LOCAL, Op.STORE_LOCAL))
_ARRAY_ACCESS = frozenset((Op.CHECK_INDEX, Op.LOAD_ELEMENT, Op.STORE_ELEMENT))
_LOCAL_ACCESS = _SCALAR_ACCESS | _ARRAY_ACCESS | {Op.RESET_LOCAL}
_WITH_OPERAND = _LOCAL_ACCESS | JUMPS | {Op.LOAD_CONSTANT, Op.CALL}
_ARITHMETIC = frozenset((Op.ADD, Op.SUBTRACT, Op.MULTIPLY, Op.DIVIDE, Op.REMAINDER))
_ORDERED = frozenset((Op.LESS, Op.LESS_EQUAL, Op.GREATER, Op.GREATER_EQUAL))


@dataclass(frozen=True)
class FunctionVerification:
    function_index: int
    function_name: str
    max_stack: int
    incoming: tuple[tuple[int, tuple[Type, ...]], ...]


def _fail(label: str, offset: int, message: str) -> None:
    raise InvalidBytecode(f"{label} at instruction {offset}: {message}")


def _token(value: Token, label: str, offset: int, identifier: bool = False) -> None:
    if (not isinstance(value, Token) or not isinstance(value.kind, TokenKind)
            or not isinstance(value.text, str)
            or type(value.line) is not int or value.line < 1
            or type(value.column) is not int or value.column < 1):
        _fail(label, offset, "The source token has invalid metadata.")
    if identifier:
        text = value.text
        first = text[:1]
        if (value.kind is not TokenKind.IDENTIFIER or not first
                or not (first == "_" or "a" <= first <= "z" or "A" <= first <= "Z")
                or any(not (char == "_" or "a" <= char <= "z" or "A" <= char <= "Z"
                            or "0" <= char <= "9") for char in text)):
            _fail(label, offset, "The declaration name is not an ASCII identifier.")


def _metadata(program: BytecodeProgram) -> None:
    if not isinstance(program, BytecodeProgram) or not isinstance(program.functions, tuple):
        _fail("program", 0, "The program must contain a tuple of functions.")
    names = set()
    for index, function in enumerate(program.functions):
        label = f"function {index}"
        if not isinstance(function, BytecodeFunction):
            _fail(label, 0, "The function record has an invalid type.")
        _token(function.name, label, 0, identifier=True)
        label = function.name.text
        if label in names:
            _fail(label, 0, "The function name occurs more than once.")
        names.add(label)
        if not isinstance(function.result, Type):
            _fail(label, 0, "The function result type is invalid.")
        if not all(isinstance(items, list) for items in (function.locals, function.constants, function.code)):
            _fail(label, 0, "The local, constant, and instruction sequences must be lists.")
        count = function.parameter_count
        if type(count) is not int or not 0 <= count <= len(function.locals):
            _fail(label, 0, "The function has insufficient parameter slots.")
        for slot, local in enumerate(function.locals):
            if not isinstance(local, Local):
                _fail(label, 0, f"Local slot {slot} has an invalid record.")
            _token(local.name, label, 0, identifier=True)
            if not isinstance(local.type, Type) or local.type not in _SCALAR:
                _fail(label, 0, f"Local slot {slot} must have type int or bool.")
            if local.length is not None:
                if type(local.length) is not int or not 1 <= local.length <= MAX_ARRAY_LENGTH:
                    _fail(label, 0, "The array length is outside the supported range.")
                if slot < count:
                    _fail(label, 0, "Array parameters are not supported.")
        for constant in function.constants:
            if type(constant) is bool:
                continue
            if not isinstance(constant, IntegerConstant):
                _fail(label, 0, "The constant must be an integer or a boolean.")
            if (not isinstance(constant.digits, str) or not constant.digits
                    or any(not "0" <= digit <= "9" for digit in constant.digits)
                    or type(constant.negative) is not bool):
                _fail(label, 0, "The integer constant must contain ASCII digits and a boolean sign.")


def _instructions(program: BytecodeProgram, function: BytecodeFunction) -> None:
    label = function.name.text
    for offset, instruction in enumerate(function.code):
        if not isinstance(instruction, Instruction) or not isinstance(instruction.op, Op):
            _fail(label, offset, "The opcode does not exist.")
        _token(instruction.token, label, offset)
        op, operand = instruction.op, instruction.operand
        if op not in _WITH_OPERAND:
            if operand is not None:
                _fail(label, offset, "The instruction does not accept an operand.")
        else:
            if op in _LOCAL_ACCESS:
                size, reason = len(function.locals), "The local index is outside the function."
            elif op in JUMPS:
                size, reason = len(function.code), "The jump target is outside the function."
            elif op is Op.CALL:
                size, reason = len(program.functions), "The function index is outside the program."
            else:
                size, reason = len(function.constants), "The constant index is outside the function."
            if type(operand) is not int or not 0 <= operand < size:
                _fail(label, offset, reason)
            if op in _SCALAR_ACCESS and function.locals[operand].length is not None:
                _fail(label, offset, "A scalar instruction selected an array slot.")
            if op in _ARRAY_ACCESS and function.locals[operand].length is None:
                _fail(label, offset, "An element instruction selected a scalar slot.")
        if op is Op.RETURN_VOID and function.result is not Type.VOID:
            _fail(label, offset, "A non-void function returned no value.")
        if op is Op.RETURN and function.result is Type.VOID:
            _fail(label, offset, "A void function returned a value.")


def _source_steps(function: BytecodeFunction, graph: ControlFlow) -> None:
    # Removing STEP nodes must leave no cycle reachable from the function entry.
    nodes = {offset for block in graph.blocks if block.start in graph.reachable
             for offset in range(block.start, block.stop) if function.code[offset].op is not Op.STEP}
    incoming = dict.fromkeys(nodes, 0)
    for offset in nodes:
        for target in graph.instruction_successors[offset]:
            if target in incoming:
                incoming[target] += 1
    pending = deque(offset for offset, count in incoming.items() if count == 0)
    removed = 0
    while pending:
        offset = pending.popleft()
        removed += 1
        for target in graph.instruction_successors[offset]:
            if target in incoming:
                incoming[target] -= 1
                if incoming[target] == 0:
                    pending.append(target)
    if removed != len(nodes):
        offset = min(offset for offset, count in incoming.items() if count)
        _fail(function.name.text, offset, "Control flow can repeat without a STEP instruction.")


def _apply(program: BytecodeProgram, function: BytecodeFunction, offset: int, stack: list[Type]) -> None:
    instruction = function.code[offset]
    op, operand = instruction.op, instruction.operand
    label = function.name.text

    def require(count: int) -> None:
        if len(stack) < count:
            _fail(label, offset, "The instruction underflows the value stack.")

    def replace(inputs: tuple[Type, ...], outputs: tuple[Type, ...]) -> None:
        require(len(inputs))
        start = len(stack) - len(inputs)
        for number, (actual, expected) in enumerate(zip(stack[start:], inputs), 1):
            if actual is not expected:
                _fail(label, offset, f"{op.name} expects {expected.value} for operand {number}. Found {actual.value}.")
        del stack[start:]
        stack.extend(outputs)

    if op in (Op.STEP, Op.RESET_LOCAL, Op.JUMP):
        return
    if op is Op.LOAD_CONSTANT:
        stack.append(Type.BOOL if type(function.constants[operand]) is bool else Type.INT)
    elif op is Op.LOAD_LOCAL:
        stack.append(function.locals[operand].type)
    elif op is Op.STORE_LOCAL:
        expected = function.locals[operand].type
        replace((expected,), (expected,))
    elif op is Op.CHECK_INDEX:
        replace((Type.INT,), (Type.INT,))
    elif op is Op.LOAD_ELEMENT:
        replace((Type.INT,), (function.locals[operand].type,))
    elif op is Op.STORE_ELEMENT:
        expected = function.locals[operand].type
        replace((Type.INT, expected), (expected,))
    elif op is Op.POP:
        require(1)
        stack.pop()
    elif op in (Op.NEGATE, Op.NOT):
        expected = Type.INT if op is Op.NEGATE else Type.BOOL
        replace((expected,), (expected,))
    elif op in _ARITHMETIC | _ORDERED:
        result = Type.INT if op in _ARITHMETIC else Type.BOOL
        replace((Type.INT, Type.INT), (result,))
    elif op in (Op.EQUAL, Op.NOT_EQUAL):
        require(2)
        replace((stack[-2], stack[-2]), (Type.BOOL,))
    elif op in CONDITIONAL_JUMPS:
        replace((Type.BOOL,), ())
    elif op is Op.CALL:
        callee = program.functions[operand]
        inputs = tuple(local.type for local in callee.locals[:callee.parameter_count])
        outputs = () if callee.result is Type.VOID else (callee.result,)
        replace(inputs, outputs)
    elif op in (Op.RETURN, Op.RETURN_VOID):
        count = 1 if op is Op.RETURN else 0
        require(count)
        if len(stack) != count:
            _fail(label, offset, "A return left temporary values on the stack.")
        if count:
            replace((function.result,), ())
    elif op is Op.UNREACHABLE:
        _fail(label, offset, "A typed function ended without a return value.")
    else:
        _fail(label, offset, "The opcode has no stack rule.")


def _function(program: BytecodeProgram, index: int) -> FunctionVerification:
    function = program.functions[index]
    graph = analyze_control_flow(function)
    _source_steps(function, graph)
    blocks = {block.start: block for block in graph.blocks}
    incoming: dict[int, tuple[Type, ...]] = {0: ()}
    pending = deque([0])
    peak = 0
    while pending:
        start = pending.popleft()
        stack = list(incoming[start])
        block = blocks[start]
        peak = max(peak, len(stack))
        for offset in range(block.start, block.stop):
            _apply(program, function, offset, stack)
            peak = max(peak, len(stack))
        outgoing = tuple(stack)
        for target in block.successors:
            if target not in incoming:
                incoming[target] = outgoing
                pending.append(target)
            elif incoming[target] != outgoing:
                previous = incoming[target]
                if len(previous) != len(outgoing):
                    _fail(function.name.text, target,
                          f"Paths supply stack heights {len(previous)} and {len(outgoing)}.")
                slot = next(slot for slot, (left, right) in enumerate(zip(previous, outgoing)) if left is not right)
                _fail(function.name.text, target,
                      f"Paths supply {previous[slot].value} and {outgoing[slot].value} at stack slot {slot}.")
    return FunctionVerification(index, function.name.text, peak, tuple(sorted(incoming.items())))


def verify_bytecode(program: BytecodeProgram) -> tuple[FunctionVerification, ...]:
    """Check every function and return its stack analysis without changing bytecode."""
    _metadata(program)
    for function in program.functions:
        _instructions(program, function)
    return tuple(_function(program, index) for index in range(len(program.functions)))
