import unittest

from minic import ast
from minic.ast_printer import format_ast
from minic.lexer import TokenKind, lex
from minic.parser import ParseError, parse


def statements(source):
    return parse(lex(b"int f() { " + source + b" }")).functions[0].body.statements


class ParserTests(unittest.TestCase):
    def test_empty_source_needs_no_entry_function(self):
        self.assertEqual(format_ast(parse(lex(b"// empty"))), "Program\n")

    def test_precedence_associativity_and_original_digits(self):
        expr = statements(b"return 009 - a * b - c;")[0].value
        self.assertIsInstance(expr, ast.Binary)
        self.assertEqual(expr.token.kind, TokenKind.MINUS)
        self.assertEqual(expr.right.token.text, "c")
        self.assertEqual(expr.left.token.kind, TokenKind.MINUS)
        self.assertEqual(expr.left.left.token.text, "009")
        self.assertEqual(expr.left.right.token.kind, TokenKind.STAR)

    def test_parenthesized_target_and_chained_assignment(self):
        stmt = statements(b"(a) = b = -x;")[0]
        outer = stmt.value
        self.assertIsInstance(outer, ast.Assign)
        self.assertEqual((stmt.token.column, outer.target.token.column, outer.token.column), (11, 12, 15))
        self.assertIsInstance(outer.value, ast.Assign)
        self.assertEqual(outer.value.target.token.text, "b")
        self.assertIsInstance(outer.value.value, ast.Unary)

    def test_braces_select_which_if_owns_the_else(self):
        inner_else, outer_else = statements(
            b"if (a) if (b) return; else ;   if (a) { if (b) return; } else ;"
        )
        self.assertIsNone(inner_else.else_branch)
        self.assertIsInstance(inner_else.then_branch.else_branch, ast.Empty)
        self.assertIsInstance(outer_else.else_branch, ast.Empty)
        self.assertIsNone(outer_else.then_branch.statements[0].else_branch)

    def test_syntax_accepts_unresolved_names_and_mixed_types(self):
        expr = statements(b"return missing(true + 1);")[0].value
        self.assertIsInstance(expr, ast.Call)
        self.assertEqual(expr.arguments[0].token.kind, TokenKind.PLUS)

    def test_diagnostics_use_the_first_unexpected_token(self):
        cases = [
            (b"int f(int a,\n) {}", (2, 1), "Expected a type. Received RIGHT_PAREN."),
            (b"int f() { if (true)\nint x; }", (2, 1), "Expected an expression. Received INT."),
            (b"int f() { g()\n= ; }", (2, 1), 'Expected a name before "=".'),
            (b"int f() { return 1;\r\n", (2, 1), 'Expected "}" after block. Received EOF.'),
            (b"int f() { int a[2]; }", (1, 16), 'Expected ";" after declaration. Received LEFT_BRACKET.'),
        ]
        for source, position, message in cases:
            with self.subTest(source=source):
                with self.assertRaises(ParseError) as caught:
                    parse(lex(source))
                error = caught.exception
                self.assertEqual((error.line, error.column, str(error)), (*position, message))

    def test_parser_requires_a_final_eof_token(self):
        for tokens, column in [([], 1), (lex(b"int name")[:-1], 5)]:
            with self.subTest(tokens=tokens):
                with self.assertRaises(ParseError) as caught:
                    parse(tokens)
                error = caught.exception
                self.assertEqual(error.column, column)
                self.assertEqual(str(error), "Expected tokens with a final EOF token.")

    def test_long_operator_chain_prints_without_python_recursion(self):
        source = b"int f() { return " + b"x+" * 1100 + b"x; }"
        listing = format_ast(parse(lex(source)))
        self.assertEqual(listing.count("Binary PLUS"), 1100)
        self.assertEqual(listing.count('Name "x"'), 1101)

    def test_deeply_nested_parentheses_report_a_source_position(self):
        source = b"int f() { return " + b"(" * 2000 + b"1" + b")" * 2000 + b"; }"
        with self.assertRaises(ParseError) as caught:
            parse(lex(source))
        self.assertEqual(str(caught.exception), "Syntax nesting exceeds the parser limit.")
        self.assertEqual(caught.exception.line, 1)
        self.assertGreater(caught.exception.column, 17)
