import unittest

from minic.bytecode import IntegerConstant, Op, format_bytecode
from minic.bytecode_compiler import compile_bytecode
from minic.lexer import lex
from minic.parser import parse


def compile_source(source):
    return compile_bytecode(parse(lex(source.encode("ascii"))))


class BytecodeTests(unittest.TestCase):
    def test_empty_program_and_functions_without_an_entry_compile(self):
        self.assertEqual(format_bytecode(compile_source("")), "bytecode\n")
        function, = compile_source("int helper(int x){return x;}").functions
        self.assertEqual((function.name.text, function.parameter_count), ("helper", 1))
        self.assertEqual([local.name.text for local in function.locals], ["x"])

    def test_integer_constants_keep_the_original_digits_and_sign(self):
        digits = "0" * 5000 + "9223372036854775809"
        function, = compile_source("int f(){return -(\n" + digits + ");}").functions
        self.assertEqual(function.constants, [IntegerConstant(digits, negative=True)])
        steps = [(i.token.line, i.token.column) for i in function.code if i.op is Op.STEP]
        self.assertEqual(steps, [(1, 8), (1, 9), (1, 16), (2, 1)])
        load, = [i for i in function.code if i.op is Op.LOAD_CONSTANT]
        self.assertEqual((load.operand, load.token.line, load.token.column), (0, 1, 16))

    def test_shadowed_names_use_separate_slots(self):
        function, = compile_source("int f(int x){ {int x=x; x=3;} return x;}").functions
        locals_used = [(i.op, i.operand) for i in function.code
                       if i.op in (Op.RESET_LOCAL, Op.STORE_LOCAL, Op.LOAD_LOCAL)]
        self.assertEqual(locals_used, [
            (Op.RESET_LOCAL, 1), (Op.LOAD_LOCAL, 1), (Op.STORE_LOCAL, 1),
            (Op.STORE_LOCAL, 1), (Op.LOAD_LOCAL, 0),
        ])

    def test_void_call_discards_no_value_and_forward_calls_use_source_order(self):
        main, helper = compile_source("void main(){helper(01,02);} void helper(int a,int b){}").functions
        self.assertEqual(main.constants, [IntegerConstant("01"), IntegerConstant("02")])
        self.assertEqual([(i.op, i.operand) for i in main.code if i.op is not Op.STEP], [
            (Op.LOAD_CONSTANT, 0), (Op.LOAD_CONSTANT, 1), (Op.CALL, 1), (Op.RETURN_VOID, None),
        ])
        self.assertEqual([i.op for i in helper.code], [Op.STEP, Op.RETURN_VOID])

    def test_loop_jumps_to_the_condition_and_exits_at_the_next_statement(self):
        function, = compile_source("int f(){while(false); return 7;}").functions
        back, = [i for i in function.code if i.op is Op.JUMP]
        exit_loop, = [i for i in function.code if i.op is Op.JUMP_IF_FALSE]
        for jump, text in [(back, "false"), (exit_loop, "return")]:
            target = function.code[jump.operand]
            self.assertEqual((target.op, target.token.text), (Op.STEP, text))

    def test_long_expressions_compile_without_python_recursion(self):
        function, = compile_source("int f(){return " + "1+" * 1500 + "1;}").functions
        self.assertEqual(sum(i.op is Op.ADD for i in function.code), 1500)
        self.assertEqual(len(function.constants), 1501)
