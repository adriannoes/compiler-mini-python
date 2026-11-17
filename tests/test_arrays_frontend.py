import unittest

from minic import ast
from minic.ast_printer import format_ast
from minic.bytecode import Op
from minic.bytecode_compiler import compile_bytecode
from minic.lexer import lex
from minic.parser import ParseError, parse
from minic.resolver import AnalysisError, resolve_names
from minic.type_checker import Type, check_types


def tree(source):
    return parse(lex(source.encode("ascii")))


class ArrayFrontendTests(unittest.TestCase):
    def test_syntax_preserves_length_digits_and_parenthesized_assignment_targets(self):
        program = tree("void main(){int a[0002]; (a[1]) = a[0] = 3;}")
        declaration, stmt = program.functions[0].body.statements
        self.assertEqual(declaration.length.text, "0002")
        self.assertIsInstance(stmt.value.target, ast.Index)
        self.assertIsInstance(stmt.value.value.target, ast.Index)
        self.assertIn('Length "0002"', format_ast(program))
        bindings = list(resolve_names(program).bindings.values())
        self.assertEqual([binding.kind for binding in bindings], ["Write", "Write"])
        self.assertIs(bindings[0].symbol, bindings[1].symbol)

    def test_array_grammar_requires_a_literal_length_and_one_named_index(self):
        for body in ("int a[];", "int a[-1];", "int a[1+1];", "int a[2][3];",
                     "int a[2]=1;", "int a[2]; a[];", "int a[2]; a[0][1];", "int a[2]; a[0](1);"):
            with self.subTest(body=body):
                with self.assertRaises(ParseError):
                    tree("void f(){" + body + "}")
        with self.assertRaises(ParseError):
            tree("void f(int a[2]){}")

    def test_length_analysis_handles_long_digits_and_reports_the_length_position(self):
        for digits in ("0", "0000", "1025", "9" * 5000):
            with self.subTest(digits=digits[:20]):
                program = tree("void f(){int a[\n  " + digits + "];}")
                resolve_names(program)
                with self.assertRaises(AnalysisError) as caught:
                    check_types(program)
                error = caught.exception
                self.assertEqual((error.line, error.column, str(error)),
                                 (2, 3, "Array length must be from 1 through 1024."))
        program = tree("void f(){bool a[" + "0" * 5000 + "1024]; a[1023]=true;}")
        analysis = check_types(program)
        declaration, assignment = program.functions[0].body.statements
        self.assertEqual(analysis.lengths[declaration], 1024)
        self.assertIs(analysis.types[assignment.value.target], Type.BOOL)

    def test_static_errors_preserve_analysis_order(self):
        for source, message in (
            ("void f(){int a[0]; missing;}", 'Undeclared name "missing".'),
            ("void f(){int a[0];} void g(void p){}", "Variables and parameters cannot have type void."),
            ("void f(){int a; a[!1];}", 'Name "a" does not refer to an array.'),
            ("void f(){int a[2]; a[true];}", "Expected type int. Received bool."),
            ("void f(){int a[2]; a=1;}", 'Array "a" requires an index.'),
            ("void f(){void a[2];}", "Variables and parameters cannot have type void."),
            ("void f(){bool a[2]; a[0]=1;}", "Expected type bool. Received int."),
        ):
            with self.subTest(source=source):
                with self.assertRaises(AnalysisError) as caught:
                    check_types(tree(source))
                self.assertEqual(str(caught.exception), message)

    def test_lowering_checks_the_saved_index_before_the_rhs_call(self):
        program = tree("int f(){return 7;} int main(){int a[2]; a[1]=f(); return a[1];}")
        function = compile_bytecode(program).functions[1]
        self.assertEqual(function.locals[0].length, 2)
        operations = [instruction.op for instruction in function.code
                      if instruction.op in (Op.CHECK_INDEX, Op.CALL, Op.STORE_ELEMENT, Op.LOAD_ELEMENT)]
        self.assertEqual(operations, [Op.CHECK_INDEX, Op.CALL, Op.STORE_ELEMENT, Op.LOAD_ELEMENT])
