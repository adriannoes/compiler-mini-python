import unittest

from minic import ast
from minic.lexer import lex
from minic.parser import parse
from minic.resolver import AnalysisError, format_resolution, resolve_names


def program(source):
    return parse(lex(source.encode("ascii")))


class ResolverTests(unittest.TestCase):
    def test_empty_program_lists_only_the_global_scope(self):
        self.assertEqual(format_resolution(resolve_names(program(""))), "Resolution\n  Scope #0 GLOBAL @1:1\n")

    def test_initializer_selects_the_new_local_and_outer_name_returns_after_block(self):
        function = program("int f(int x) { { int x = x; x = x; } return x; }").functions[0]
        result = resolve_names(ast.Program((function,)))
        block, ret = function.body.statements
        var, stmt = block.statements
        for use in (var.initializer, stmt.value.target, stmt.value.value):
            self.assertIs(result.bindings[use].symbol.declaration, var)
        self.assertEqual(result.bindings[stmt.value.target].kind, "Write")
        self.assertIs(result.bindings[ret.value].symbol.declaration, function.parameters[0])

    def test_first_name_error_respects_declaration_and_use_order(self):
        cases = [
            ("int f() { missing; }\nint f() {}", 2, 5, 'Name "f" is already declared in this scope.'),
            ("void f(int x) {\nint x; }", 2, 5, 'Name "x" is already declared in this scope.'),
            ("void f() {\nx = y; }", 2, 1, 'Undeclared name "x".'),
            ("void f() { int f;\nf(missing); }", 2, 1, 'Name "f" does not refer to a function.'),
            ("void f() {\nf = 1; }", 2, 1, 'Name "f" does not refer to a variable or parameter.'),
            ("void f() { return; { int x; }\nx; }", 2, 1, 'Undeclared name "x".'),
        ]
        for source, line, column, message in cases:
            with self.subTest(source=source):
                with self.assertRaises(AnalysisError) as caught:
                    resolve_names(program(source))
                error = caught.exception
                self.assertEqual((error.line, error.column, str(error)), (line, column, message))

    def test_ast_declaration_cannot_be_an_unbraced_branch(self):
        function = program("void f() { while (true) { int x; } }").functions[0]
        loop = function.body.statements[0]
        variable = loop.body.statements[0]
        bad_loop = ast.While(loop.token, loop.condition, variable)
        body = ast.Block(function.body.token, (bad_loop,))
        bad_function = ast.Function(function.token, function.return_type, (), body)
        with self.assertRaises(AnalysisError) as caught:
            resolve_names(ast.Program((bad_function,)))
        self.assertEqual(caught.exception.column, variable.type_token.column)
        self.assertEqual(str(caught.exception), "A variable declaration must appear directly in a block.")
