import unittest

from labs.parsing.grammar import DANGLING_ELSE, EXPRESSION, analyze
from minic import ast
from minic.lexer import lex
from minic.parser import parse


class ParsingLabTests(unittest.TestCase):
    def test_expression_sets_and_predictive_entries(self):
        result = analyze(EXPRESSION, "E")
        self.assertEqual(result.nullable, {"E_tail", "T_tail"})
        self.assertEqual(result.first, {
            "E": {"id", "("}, "E_tail": {"+"}, "T": {"id", "("},
            "T_tail": {"*"}, "F": {"id", "("},
        })
        self.assertEqual(result.follow, {
            "E": {"$", ")"}, "E_tail": {"$", ")"}, "T": {"+", "$", ")"},
            "T_tail": {"+", "$", ")"}, "F": {"*", "+", "$", ")"},
        })
        self.assertEqual(result.conflicts, {})
        self.assertEqual(result.table["T_tail", "+"], ((),))
        self.assertEqual(result.table["E_tail", "+"], (("+", "T", "E_tail"),))
        self.assertNotIn(("T", "*"), result.table)

    def test_cycles_and_nullable_suffixes_reach_a_fixed_point(self):
        grammar = {
            "S": (("A", "B"),), "A": (("C",), ("a",)),
            "C": (("A",), ()), "B": (("D",),), "D": (("b",), ()),
        }
        result = analyze(grammar, "S")
        self.assertEqual(result.nullable, set(grammar))
        self.assertEqual(result.first["S"], {"a", "b"})
        self.assertEqual(result.first["C"], {"a"})
        self.assertEqual(result.follow["C"], {"b", "$"})
        self.assertEqual(result.follow["D"], {"$"})
        reversed_result = analyze(dict(reversed(list(grammar.items()))), "S")
        self.assertEqual(result, reversed_result)

    def test_nonproductive_cycle_terminates_without_inventing_terminals(self):
        result = analyze({"S": (("A",),), "A": (("S",),)}, "S")
        self.assertEqual(result.nullable, set())
        self.assertEqual(result.first, {"S": set(), "A": set()})
        self.assertEqual(result.follow, {"S": {"$"}, "A": {"$"}})
        self.assertEqual(result.table, {})

    def test_shared_prefix_keeps_both_choices(self):
        result = analyze({"S": (("id",), ("id", "(", ")"))}, "S")
        self.assertEqual(result.conflicts, {("S", "id"): (("id",), ("id", "(", ")"))})

    def test_else_conflict_and_the_parser_attachment_policy(self):
        result = analyze(DANGLING_ELSE, "S")
        self.assertEqual(result.conflicts, {("O", "else"): (("else", "S"), ())})
        for braces in (False, True):
            body = b"{ if(b) return 1; }" if braces else b"if(b) return 1;"
            source = b"int f(){ if(a) " + body + b" else return 2; }"
            outer = parse(lex(source)).functions[0].body.statements[0]
            with self.subTest(braces=braces):
                if braces:
                    self.assertIsInstance(outer.else_branch, ast.Return)
                    self.assertIsNone(outer.then_branch.statements[0].else_branch)
                else:
                    self.assertIsNone(outer.else_branch)
                    self.assertIsInstance(outer.then_branch.else_branch, ast.Return)

    def test_reserved_end_marker_and_missing_start_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "start symbol"):
            analyze(EXPRESSION, "missing")
        for grammar in ({"S": (("$",),)}, {"$": ((),)}):
            with self.subTest(grammar=grammar), self.assertRaisesRegex(ValueError, "reserved"):
                analyze(grammar, next(iter(grammar)))
