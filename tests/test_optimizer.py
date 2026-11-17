import unittest
import subprocess
import sys
from pathlib import Path

from minic.bytecode import Instruction, IntegerConstant, Op, format_bytecode
from minic.bytecode_compiler import compile_bytecode
from minic.bytecode_optimizer import optimize_bytecode
from minic.lexer import lex
from minic.parser import parse
from minic.runtime import BoolValue, ExecutionError, IntValue
from minic.vm import execute_bytecode


def compile_source(source):
    return compile_bytecode(parse(lex(source.encode("ascii"))))


class OptimizerTests(unittest.TestCase):
    def test_dead_operands_need_no_invented_stack_types(self):
        for op in (Op.NEGATE, Op.NOT, Op.ADD, Op.LESS, Op.EQUAL):
            with self.subTest(op=op):
                code = compile_source("int main(){return 1;}")
                function = code.functions[0]
                function.constants.append(True)
                token = function.name
                first, second = (0, 1) if op is Op.NEGATE else (1, 0)
                function.code.extend([
                    Instruction(Op.LOAD_CONSTANT, token, first),
                    Instruction(Op.LOAD_CONSTANT, token, second),
                    Instruction(op, token),
                    Instruction(Op.POP, token),
                ])
                optimized = optimize_bytecode(code)
                self.assertEqual(execute_bytecode(optimized), IntValue(1))

    def test_deleted_dead_target_does_not_escape_jump_threading(self):
        code = compile_source("int main(){return 1;}")
        function = code.functions[0]
        start = len(function.code)
        token = function.name
        function.code.extend([
            Instruction(Op.JUMP, token, start + 2), Instruction(Op.POP, token),
            Instruction(Op.LOAD_CONSTANT, token, 0), Instruction(Op.POP, token),
        ])
        optimized = optimize_bytecode(code)
        self.assertEqual(execute_bytecode(optimized), IntValue(1))
        self.assertEqual(len(optimized.functions[0].code), start - 1)

    def test_dead_jump_cycles_finish_and_leave_the_input_unchanged(self):
        script = """
from minic.bytecode import Instruction, Op, format_bytecode
from minic.bytecode_compiler import compile_bytecode
from minic.bytecode_optimizer import optimize_bytecode
from minic.lexer import lex
from minic.parser import parse
program = compile_bytecode(parse(lex(b'void main(){}')))
function = program.functions[0]
start = len(function.code)
function.code.extend([Instruction(Op.JUMP, function.name, start + 1),
                      Instruction(Op.JUMP, function.name, start)])
before = format_bytecode(program)
optimized = optimize_bytecode(program)
assert len(optimized.functions[0].code) == start
assert format_bytecode(program) == before
print('ok')
"""
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, timeout=5,
                                cwd=Path(__file__).resolve().parents[1])
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"ok\n", b""))

    def test_optimization_preserves_original_digits_and_each_named_entry(self):
        original = compile_source("int f(){int x=0007/-2;return x;} bool g(){return !(2<3);}")
        before = format_bytecode(original)
        optimized = optimize_bytecode(original)
        self.assertEqual(format_bytecode(original), before)
        self.assertNotEqual(format_bytecode(optimized), before)
        self.assertEqual(optimize_bytecode(optimized), optimized)
        self.assertEqual(execute_bytecode(optimized, "f"), IntValue(-3))
        self.assertEqual(execute_bytecode(optimized, "g"), BoolValue(False))
        function = optimized.functions[0]
        self.assertEqual(function.constants[0], IntegerConstant("0007"))
        self.assertEqual(function.constants[-1], IntegerConstant("3", negative=True))
        for name in ("constants", "locals", "code"):
            self.assertIsNot(getattr(function, name), getattr(original.functions[0], name))

    def test_failing_discarded_values_keep_their_runtime_errors_and_positions(self):
        for expr, diagnostic in (
            ("1 / 0", "The divisor is zero."),
            ("9223372036854775808", "The integer literal is outside the signed 64-bit range."),
            ("9223372036854775807 + 1", "Integer arithmetic exceeds the signed 64-bit range."),
            ("-9223372036854775808 % -1", "Integer arithmetic exceeds the signed 64-bit range."),
            ("x * 0", 'The variable "x" has no value.'),
            ("fault()", "The divisor is zero."),
        ):
            with self.subTest(expr=expr):
                original = compile_source("int fault(){return 3/0;} int main(){int x;\n" + expr + ";return 7;}")
                with self.assertRaises(ExecutionError) as baseline:
                    execute_bytecode(original)
                optimized = optimize_bytecode(original)
                with self.assertRaises(ExecutionError) as result:
                    execute_bytecode(optimized)
                self.assertEqual(str(result.exception), diagnostic)
                self.assertEqual((result.exception.line, result.exception.column),
                                 (baseline.exception.line, baseline.exception.column))

    def test_merging_branches_does_not_assume_which_path_supplied_the_operand(self):
        code = optimize_bytecode(compile_source(
            "bool f(bool b){return (b || false) == false;}"
            "bool main(){return f(false) && !f(true);}"
        ))
        self.assertIn(Op.EQUAL, [i.op for i in code.functions[0].code])
        self.assertEqual(execute_bytecode(code), BoolValue(True))

    def test_known_branches_and_discarded_constants_preserve_assignment_and_call_order(self):
        code = optimize_bytecode(compile_source(
            "int pair(int a,int b){return a*10+b;}"
            "int main(){int x=0; false && ((x=99)==99); 6*7;"
            "if(1<2)return pair(x=x+1,x=x+1);else return 1/0;}"
        ))
        ops = [instruction.op for instruction in code.functions[1].code]
        for removed in (Op.JUMP_IF_FALSE, Op.JUMP, Op.MULTIPLY, Op.DIVIDE):
            self.assertNotIn(removed, ops)
        self.assertIn(Op.CALL, ops)
        self.assertEqual(execute_bytecode(code), IntValue(12))
