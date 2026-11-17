import unittest

from minic.bytecode import IntegerConstant, Op, format_bytecode
from minic.bytecode_compiler import compile_bytecode
from minic.bytecode_optimizer import optimize_bytecode
from minic.lexer import lex
from minic.parser import parse
from minic.runtime import BoolValue, ExecutionError, IntValue
from minic.vm import execute_bytecode


def compile_source(source):
    return compile_bytecode(parse(lex(source.encode("ascii"))))


class OptimizerTests(unittest.TestCase):
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
