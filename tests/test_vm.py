import unittest
from dataclasses import replace

from minic.bytecode import Op, format_bytecode
from minic.bytecode_compiler import compile_bytecode
from minic.bytecode_optimizer import optimize_bytecode
from minic.interpreter import interpret
from minic.lexer import lex
from minic.parser import parse
from minic.runtime import BoolValue, ExecutionError, ExecutionLimits, IntValue
from minic.vm import InvalidBytecode, execute_bytecode


def tree(source):
    return parse(lex(source.encode("ascii")))


def outcome(engine, program, limits):
    try:
        return engine(program, limits=limits)
    except ExecutionError as error:
        return error.line, error.column, str(error)


class VmTests(unittest.TestCase):
    def test_calls_preserve_pending_values_and_copy_arguments_in_order(self):
        source = """
            int main() {
              int x = 3;
              return 100 + pair(x = x + 1, zero() + (x = x + 1)) + x;
            }
            int zero() { return 0; }
            int pair(int a, int b) { int n = a * 10 + b; a = 0; return n; }
        """
        self.assertEqual(execute_bytecode(compile_bytecode(tree(source))), IntValue(150))

    def test_next_entry_starts_with_fresh_state_after_a_runtime_error(self):
        code = compile_bytecode(tree("int bad(){return 1/0;} bool ok(){bool x=true; return x;}"))
        before = format_bytecode(code)
        for _ in range(2):
            with self.assertRaises(ExecutionError) as caught:
                execute_bytecode(code, "bad")
            self.assertEqual((caught.exception.column, str(caught.exception)), (19, "The divisor is zero."))
            self.assertEqual(execute_bytecode(code, "ok"), BoolValue(True))
        self.assertEqual(format_bytecode(code), before)

    def test_source_steps_and_depth_match_the_interpreter_at_each_boundary(self):
        for source in (
            "int main(){return 42;}",
            "int main(){int x; return x=-1;}",
            "bool main(){return true || 1/0==0;}",
            "bool main(){return false && 9223372036854775808==0;}",
            "int main(){if(true){return 2;}else return 3;}",
            "int main(){int i=0; while(i<2){int x; if(i==0)x=1; i=i+1; x;} return i;}",
            "void main(){while(true);}",
            "void f(){} void main(){f(); f();}",
            "int f(int n){if(n==0)return 0; return 1+f(n-1);} int main(){return f(3);}",
            "int id(int n){return n;} int main(){return id(id(1/0));}",
            "int main(){int x=(2+3)*4; if(1<2)x=x+4;else x=1/0; 6*7; return x;}",
            "void main(){while(1+2==3){4*5;}}",
        ):
            ast = tree(source)
            code = compile_bytecode(ast)
            optimized = optimize_bytecode(code)
            for steps in range(1, 81):
                for depth in (1, 2, 4):
                    with self.subTest(source=source, steps=steps, depth=depth):
                        limits = ExecutionLimits(steps, depth)
                        expected = outcome(interpret, ast, limits)
                        self.assertEqual(outcome(execute_bytecode, code, limits), expected)
                        self.assertEqual(outcome(execute_bytecode, optimized, limits), expected)

    def test_deep_recursion_unwinds_without_python_calls(self):
        source = ("int main(){return sum(5000);}"
                  "int sum(int n){if(n==0)return 0; return 1+sum(n-1);}")
        code = compile_bytecode(tree(source))
        self.assertEqual(execute_bytecode(code, limits=ExecutionLimits(200_000, 5002)), IntValue(5000))

    def test_opcode_selects_arithmetic_and_source_position_selects_the_diagnostic(self):
        code = compile_bytecode(tree("int main(){return 3 + 0;}"))
        instructions = code.functions[0].code
        offset = next(i for i, ins in enumerate(instructions) if ins.op is Op.ADD)
        instructions[offset] = replace(instructions[offset], op=Op.DIVIDE)
        with self.assertRaises(ExecutionError) as caught:
            execute_bytecode(code)
        self.assertEqual((str(caught.exception), caught.exception.column), ("The divisor is zero.", 21))

    def test_malformed_instructions_cannot_use_python_negative_indices_or_caller_operands(self):
        for op, operand, reason in (
            (Op.LOAD_CONSTANT, -1, "The constant index is outside the function."),
            (Op.LOAD_LOCAL, -1, "The local index is outside the function."),
            (Op.CALL, -1, "The function index is outside the program."),
            (Op.JUMP, -1, "The jump target is outside the function."),
            (Op.JUMP, 99, "The jump target is outside the function."),
            (Op.POP, None, "The instruction underflows the value stack."),
            (Op.RETURN_VOID, None, "A non-void function returned no value."),
        ):
            with self.subTest(op=op, operand=operand):
                code = compile_bytecode(tree("int f(int x){return x+0;} int main(){return 2+f(1);}"))
                instructions = code.functions[0].code
                instructions[0] = replace(instructions[0], op=op, operand=operand)
                with self.assertRaises(InvalidBytecode) as caught:
                    execute_bytecode(code)
                self.assertEqual(str(caught.exception), f"Invalid bytecode: f at instruction 0: {reason}")
