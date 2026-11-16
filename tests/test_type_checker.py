import unittest
from itertools import product

from minic import ast
from minic.lexer import lex
from minic.parser import parse
from minic.resolver import AnalysisError
from minic.type_checker import Type, check_types


def program(source):
    return parse(lex(source.encode("ascii")))


class TypeCheckerTests(unittest.TestCase):
    def test_types_and_bindings_follow_node_identity_at_identical_positions(self):
        integer = program("int  a(int  x) { x = a(x); return x; }").functions[0]
        boolean = program("bool b(bool x) { x = b(x); return x; }").functions[0]
        analysis = check_types(ast.Program((integer, boolean)))
        a = integer.body.statements[0].value.target.token
        b = boolean.body.statements[0].value.target.token
        self.assertEqual((a.line, a.column), (b.line, b.column))
        for f, ty in ((integer, Type.INT), (boolean, Type.BOOL)):
            assignment = f.body.statements[0].value
            call = assignment.value
            for node in (assignment, assignment.target, call, call.arguments[0], f.body.statements[1].value):
                self.assertIs(analysis.types[node], ty)
            self.assertIs(analysis.resolution.bindings[call].symbol.declaration, f)
            self.assertIs(analysis.resolution.bindings[assignment.target].symbol.declaration, f.parameters[0])

    def assert_operator(self, expression, expected):
        tree = program(f"void v() {{}} void f() {{ {expression}; }}")
        expr = tree.functions[1].body.statements[0].value
        if expected is None:
            with self.assertRaises(AnalysisError) as caught:
                check_types(tree)
            self.assertEqual((caught.exception.line, caught.exception.column), (expr.token.line, expr.token.column))
        else:
            self.assertIs(check_types(tree).types[expr], expected)

    def test_operator_results_for_all_scalar_operands(self):
        values = ("1", "true", "v()")
        for op in "+ - * / % < <= > >= == != && ||".split():
            for left, right in product(values, repeat=2):
                expr = f"{left} {op} {right}"
                expected = None
                if left == right == "1" and op not in ("&&", "||"):
                    expected = Type.INT if op in ("+", "-", "*", "/", "%") else Type.BOOL
                if left == right == "true" and op in ("==", "!=", "&&", "||"):
                    expected = Type.BOOL
                with self.subTest(expr=expr):
                    self.assert_operator(expr, expected)
        for op, value in product(("-", "!"), values):
            with self.subTest(expr=op + value):
                self.assert_operator(op + value, {"-1": Type.INT, "!true": Type.BOOL}.get(op + value))

    def test_first_error_across_phases_and_children(self):
        cases = [
            ("void f(){int x=true;}\nvoid g(){missing;}", 2, 10, 'Undeclared name "missing".'),
            ("void f(){int x=true;}\nvoid g(void p){}", 2, 8, "Variables and parameters cannot have type void."),
            ("void f(int x){}\nvoid g(){f(!1, true);}", 2, 10, 'Function "f" expects 1 argument. Received 2.'),
            ("void f(int a,int b){}\nvoid g(){f(true,!1);}", 2, 12, "Expected type int. Received bool."),
            ("void f(){true + (\n!1);}", 2, 1, "Expected type bool. Received int."),
            ("void f(){\nreturn !1;}", 2, 1, "A void function cannot return a value."),
            ("void f() {return;\nint x=true;}", 2, 7, "Expected type int. Received bool."),
        ]
        for source, line, column, message in cases:
            with self.subTest(source=source):
                with self.assertRaises(AnalysisError) as caught:
                    check_types(program(source))
                error = caught.exception
                self.assertEqual((error.line, error.column, str(error)), (line, column, message))

    def test_return_guarantees_depend_on_both_branches(self):
        for body in ("if (true) return 1;", "while (true) return 1;", "if (true) return 1; else ;"):
            with self.subTest(body=body):
                with self.assertRaises(AnalysisError) as caught:
                    check_types(program(f"int f() {{ {body} }}"))
                self.assertEqual(caught.exception.column, 5)
                self.assertEqual(str(caught.exception), 'Function "f" does not guarantee a return value.')
        check_types(program("int f(bool b) { if (b) return 1; else { return 2; } }"))
        check_types(program("int f(bool b) { if (b) return 1; return 2; }"))

    def test_execution_errors_do_not_fail_static_analysis(self):
        check_types(program("int f() { int x = x; 1 / 0; return 9223372036854775808; }"))

    def test_long_operator_chains_use_an_explicit_stack(self):
        tree = program("int f(int x) { return " + "x+" * 1400 + "x; }")
        analysis = check_types(tree)
        self.assertEqual(len(analysis.resolution.bindings), 1401)
        self.assertIs(analysis.types[tree.functions[0].body.statements[0].value], Type.INT)
