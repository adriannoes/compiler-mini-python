import unittest
from dataclasses import replace
from pathlib import Path

from minic.bytecode import BytecodeFunction, BytecodeProgram, Instruction, IntegerConstant, InvalidBytecode, Local, Op
from minic.bytecode_compiler import compile_bytecode
from minic.bytecode_optimizer import optimize_bytecode
from minic.bytecode_verifier import verify_bytecode
from minic.lexer import Token, TokenKind, lex
from minic.parser import parse
from minic.runtime import BoolValue, ExecutionError, ExecutionLimits
from minic.type_checker import Type
from minic.vm import execute_bytecode


ROOT = Path(__file__).resolve().parents[1]
TOKEN = Token(TokenKind.IDENTIFIER, "main", 1, 1)
INT = IntegerConstant("1")


def compile_source(source):
    return compile_bytecode(parse(lex(source.encode("ascii"))))


def program(operations, result=Type.INT, locals=(), constants=(INT, True)):
    function = BytecodeFunction(TOKEN, result, 0, list(locals), list(constants), [
        Instruction(op, TOKEN, operand) for op, operand in operations
    ])
    return BytecodeProgram((function,))


class BytecodeVerifierTests(unittest.TestCase):
    def assert_invalid(self, code, offset, message):
        with self.assertRaises(InvalidBytecode) as caught:
            verify_bytecode(code)
        self.assertEqual(str(caught.exception), f"Invalid bytecode: main at instruction {offset}: {message}")

    def test_examples_pass_before_and_after_optimization(self):
        for path in sorted((ROOT / "examples").glob("*.mc")):
            if path.name in ("expressions.mc", "type_error.mc"):
                continue
            with self.subTest(example=path.name):
                original = compile_bytecode(parse(lex(path.read_bytes())))
                for code in (original, optimize_bytecode(original)):
                    reports = verify_bytecode(code)
                    self.assertEqual([report.function_name for report in reports],
                                     [function.name.text for function in code.functions])
                    self.assertEqual([report.function_index for report in reports], list(range(len(reports))))
                    self.assertTrue(all(report.incoming[0] == (0, ()) for report in reports))

    def test_peak_counts_calls_and_optimized_short_circuits(self):
        for filename, peaks in (("calls.mc", ((2, 3), (2, 3))), ("short_circuit.mc", ((2,), (1,)))):
            code = compile_bytecode(parse(lex((ROOT / "examples" / filename).read_bytes())))
            self.assertEqual(tuple(report.max_stack for report in verify_bytecode(code)), peaks[0])
            self.assertEqual(tuple(report.max_stack for report in verify_bytecode(optimize_bytecode(code))), peaks[1])

    def test_hidden_branches_still_need_operands_with_matching_types(self):
        underflow = program([(Op.LOAD_CONSTANT, 1), (Op.JUMP_IF_TRUE, 5), (Op.LOAD_CONSTANT, 0),
                             (Op.ADD, None), (Op.RETURN, None), (Op.LOAD_CONSTANT, 0), (Op.RETURN, None)])
        self.assert_invalid(underflow, 3, "The instruction underflows the value stack.")
        wrong_type = program([(Op.LOAD_CONSTANT, 1), (Op.JUMP_IF_TRUE, 6), (Op.LOAD_CONSTANT, 0),
                              (Op.LOAD_CONSTANT, 1), (Op.ADD, None), (Op.RETURN, None),
                              (Op.LOAD_CONSTANT, 0), (Op.RETURN, None)])
        self.assert_invalid(wrong_type, 4, "ADD expects int for operand 2. Found bool.")
        for engine in (execute_bytecode, optimize_bytecode):
            with self.assertRaises(InvalidBytecode):
                engine(wrong_type)

    def test_joins_compare_heights_and_types_below_the_top(self):
        heights = program([(Op.LOAD_CONSTANT, 1), (Op.JUMP_IF_TRUE, 4), (Op.LOAD_CONSTANT, 0),
                           (Op.JUMP, 4), (Op.RETURN_VOID, None)], result=Type.VOID)
        self.assert_invalid(heights, 4, "Paths supply stack heights 0 and 1.")
        types = program([(Op.LOAD_CONSTANT, 1), (Op.JUMP_IF_TRUE, 5), (Op.LOAD_CONSTANT, 0),
                         (Op.LOAD_CONSTANT, 0), (Op.JUMP, 7), (Op.LOAD_CONSTANT, 1),
                         (Op.LOAD_CONSTANT, 0), (Op.POP, None), (Op.POP, None), (Op.RETURN_VOID, None)],
                        result=Type.VOID)
        self.assert_invalid(types, 7, "Paths supply bool and int at stack slot 0.")

    def test_calls_use_parameter_and_result_types(self):
        code = compile_source("int take(bool flag){return 1;} int main(){return take(true);}")
        caller = code.functions[1]
        constant = next(index for index, value in enumerate(caller.constants) if type(value) is bool)
        caller.constants[constant] = INT
        offset = next(index for index, instruction in enumerate(caller.code) if instruction.op is Op.CALL)
        with self.assertRaisesRegex(InvalidBytecode, f"main at instruction {offset}: CALL expects bool"):
            verify_bytecode(code)
        code = compile_source("void take(int n){} void main(){take(1);}")
        self.assertEqual([report.max_stack for report in verify_bytecode(code)], [0, 1])

    def test_array_indices_and_values_use_distinct_types(self):
        array = Local(TOKEN, Type.BOOL, 2)
        for operations, offset, reason in (
            ([(Op.LOAD_CONSTANT, 1), (Op.LOAD_ELEMENT, 0), (Op.RETURN, None)], 1,
             "LOAD_ELEMENT expects int for operand 1. Found bool."),
            ([(Op.LOAD_CONSTANT, 0), (Op.LOAD_CONSTANT, 0), (Op.STORE_ELEMENT, 0), (Op.RETURN, None)], 2,
             "STORE_ELEMENT expects bool for operand 2. Found int."),
            ([(Op.LOAD_CONSTANT, 1), (Op.CHECK_INDEX, 0), (Op.RETURN, None)], 1,
             "CHECK_INDEX expects int for operand 1. Found bool."),
        ):
            with self.subTest(reason=reason):
                self.assert_invalid(program(operations, result=Type.BOOL, locals=(array,)), offset, reason)
        valid = compile_source("bool main(){bool values[2];values[0]=true;return values[0];}")
        self.assertEqual(verify_bytecode(valid)[0].max_stack, 2)
        self.assertEqual(execute_bytecode(valid), BoolValue(True))

    def test_return_type_and_leftover_values_are_errors(self):
        cases = [
            ([(Op.LOAD_CONSTANT, 1), (Op.RETURN, None)], Type.INT, 1,
             "RETURN expects int for operand 1. Found bool."),
            ([(Op.RETURN_VOID, None)], Type.INT, 0, "A non-void function returned no value."),
            ([(Op.LOAD_CONSTANT, 0), (Op.RETURN, None)], Type.VOID, 1, "A void function returned a value."),
            ([(Op.LOAD_CONSTANT, 0), (Op.LOAD_CONSTANT, 0), (Op.RETURN, None)], Type.INT, 2,
             "A return left temporary values on the stack."),
            ([(Op.UNREACHABLE, None)], Type.INT, 0, "A typed function ended without a return value."),
        ]
        for operations, result, offset, reason in cases:
            with self.subTest(reason=reason):
                self.assert_invalid(program(operations, result=result), offset, reason)

    def test_runtime_errors_keep_their_original_execution_conditions(self):
        digits = "9" * 5000
        safe = compile_source(f"bool main(){{return true || {digits}==0 || 1/0==0;}}")
        self.assertEqual(execute_bytecode(safe), BoolValue(True))
        self.assertEqual(execute_bytecode(optimize_bytecode(safe)), BoolValue(True))
        for source, reason in (
            (f"int main(){{return {digits};}}", "The integer literal is outside the signed 64-bit range."),
            ("int main(){return 1/0;}", "The divisor is zero."),
            ("int main(){int value;return value;}", 'The variable "value" has no value.'),
            ("int main(){int a[2];return a[2];}", 'The array index 2 is outside "a" with length 2.'),
        ):
            with self.subTest(source=source[:50]):
                code = compile_source(source)
                verify_bytecode(code)
                with self.assertRaises(ExecutionError) as caught:
                    execute_bytecode(code)
                self.assertEqual(str(caught.exception), reason)

    def test_reachable_cycles_must_cross_a_source_step(self):
        for operations in (
            [(Op.JUMP, 0)],
            [(Op.JUMP, 1), (Op.JUMP, 0)],
            [(Op.STEP, None), (Op.LOAD_CONSTANT, 1), (Op.JUMP_IF_TRUE, 1), (Op.RETURN_VOID, None)],
        ):
            with self.subTest(operations=operations):
                with self.assertRaisesRegex(InvalidBytecode, "Control flow can repeat without a STEP"):
                    verify_bytecode(program(operations, result=Type.VOID))
        code = program([(Op.STEP, None), (Op.JUMP, 0)], result=Type.VOID)
        self.assertEqual(verify_bytecode(code)[0].max_stack, 0)
        with self.assertRaisesRegex(ExecutionError, "The execution step limit was reached"):
            execute_bytecode(code, limits=ExecutionLimits(3, 2))

    def test_dead_cycles_and_dead_stack_operations_have_no_invented_state(self):
        code = program([(Op.LOAD_CONSTANT, 0), (Op.RETURN, None), (Op.POP, None),
                        (Op.JUMP, 4), (Op.JUMP, 3)])
        report, = verify_bytecode(code)
        self.assertEqual(report.incoming, ((0, ()),))
        optimized = optimize_bytecode(code)
        self.assertEqual(len(optimized.functions[0].code), 2)

    def test_unreachable_instruction_shapes_are_still_checked(self):
        for instruction, message in (
            (Instruction(Op.STEP, TOKEN, 0), "The instruction does not accept an operand."),
            (Instruction(Op.LOAD_CONSTANT, TOKEN, True), "The constant index is outside the function."),
            (Instruction(Op.JUMP, TOKEN, False), "The jump target is outside the function."),
            (Instruction(Op.CALL, TOKEN, 1), "The function index is outside the program."),
            (Instruction(Op.LOAD_LOCAL, TOKEN, -1), "The local index is outside the function."),
            (Instruction("POP", TOKEN), "The opcode does not exist."),
            (Instruction(Op.STEP, replace(TOKEN, line=True)), "The source token has invalid metadata."),
        ):
            with self.subTest(instruction=instruction):
                code = program([(Op.LOAD_CONSTANT, 0), (Op.RETURN, None)])
                code.functions[0].code.append(instruction)
                self.assert_invalid(code, 2, message)

    def test_scalar_and_array_instructions_require_the_correct_slot_kind(self):
        for local, op, reason in (
            (Local(TOKEN, Type.INT, 1), Op.LOAD_LOCAL, "A scalar instruction selected an array slot."),
            (Local(TOKEN, Type.INT), Op.LOAD_ELEMENT, "An element instruction selected a scalar slot."),
        ):
            code = program([(Op.LOAD_CONSTANT, 0), (Op.RETURN, None), (op, 0)], locals=(local,))
            self.assert_invalid(code, 2, reason)

    def test_metadata_rejects_booleans_as_counts_and_array_lengths(self):
        code = program([(Op.LOAD_CONSTANT, 0), (Op.RETURN, None)], locals=(Local(TOKEN, Type.INT),))
        code.functions[0].parameter_count = True
        self.assert_invalid(code, 0, "The function has insufficient parameter slots.")
        for length in (True, 0, 1025, -1, 1.0):
            code = program([(Op.LOAD_CONSTANT, 0), (Op.RETURN, None)], locals=(Local(TOKEN, Type.INT, length),))
            self.assert_invalid(code, 0, "The array length is outside the supported range.")
        code = program([(Op.LOAD_CONSTANT, 0), (Op.RETURN, None)], locals=(Local(TOKEN, Type.BOOL, 2),))
        code.functions[0].parameter_count = 1
        self.assert_invalid(code, 0, "Array parameters are not supported.")

    def test_constant_metadata_has_a_separate_contract_from_range(self):
        for constant in (IntegerConstant(""), IntegerConstant("-1"), IntegerConstant("١"),
                         IntegerConstant("1", negative=1), IntegerConstant(1)):
            code = program([(Op.LOAD_CONSTANT, 0), (Op.RETURN, None)], constants=(constant,))
            self.assert_invalid(code, 0, "The integer constant must contain ASCII digits and a boolean sign.")
        self.assert_invalid(program([(Op.RETURN_VOID, None)], result=Type.VOID, constants=(1,)),
                            0, "The constant must be an integer or a boolean.")
        self.assertEqual(verify_bytecode(BytecodeProgram(())), ())

    def test_malformed_records_fail_with_context_instead_of_host_errors(self):
        for field, value in (("name", None), ("result", "int"), ("parameter_count", -1),
                             ("locals", None), ("constants", (INT,)), ("code", None),
                             ("locals", [None]), ("locals", [Local(TOKEN, Type.VOID)]),
                             ("code", [None])):
            with self.subTest(field=field, value=value):
                code = program([(Op.LOAD_CONSTANT, 0), (Op.RETURN, None)])
                setattr(code.functions[0], field, value)
                with self.assertRaisesRegex(InvalidBytecode, "at instruction 0:"):
                    verify_bytecode(code)
        code = program([(Op.LOAD_CONSTANT, 0), (Op.RETURN, None)])
        with self.assertRaisesRegex(InvalidBytecode, "The function name occurs more than once"):
            verify_bytecode(BytecodeProgram((code.functions[0], code.functions[0])))
        for malformed in (None, BytecodeProgram([code.functions[0]]), BytecodeProgram((None,))):
            with self.assertRaisesRegex(InvalidBytecode, "at instruction 0:"):
                verify_bytecode(malformed)

    def test_analysis_rechecks_mutable_records_after_a_success(self):
        code = compile_source("int main(){return 1;}")
        first = verify_bytecode(code)
        instruction = code.functions[0].code[0]
        code.functions[0].code[0] = replace(instruction, op=Op.POP)
        self.assert_invalid(code, 0, "The instruction underflows the value stack.")
        self.assertEqual(first[0].incoming, ((0, ()),))

    def test_large_operand_stacks_need_no_state_copy_per_instruction(self):
        count = 5000
        operations = [(Op.LOAD_CONSTANT, 0)] * count + [(Op.POP, None)] * count + [(Op.RETURN_VOID, None)]
        report, = verify_bytecode(program(operations, result=Type.VOID))
        self.assertEqual(report.max_stack, count)
        self.assertEqual(report.incoming, ((0, ()),))
