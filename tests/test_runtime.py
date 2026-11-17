import unittest

from minic.lexer import lex
from minic.runtime import (
    MAX_INT, MIN_INT, BoolValue, ExecutionError, IntValue, binary, integer_literal, unary,
)


class RuntimeTests(unittest.TestCase):
    def test_result_types_do_not_conflate_zero_and_false(self):
        self.assertNotEqual(IntValue(0), BoolValue(False))
        self.assertEqual(str(IntValue(0)), "0")
        self.assertEqual(str(BoolValue(False)), "false")

    def test_literal_range_includes_the_signed_minimum(self):
        token = lex(b"\n  -")[0]
        self.assertEqual(integer_literal("0" * 5000 + str(-MIN_INT), True, token), IntValue(MIN_INT))
        self.assertEqual(integer_literal(str(MAX_INT), False, token), IntValue(MAX_INT))
        for digits, negative in [(str(-MIN_INT), False), (str(-MIN_INT + 1), True), ("9" * 5000, False)]:
            with self.subTest(negative=negative, prefix=digits[:20]):
                with self.assertRaises(ExecutionError) as caught:
                    integer_literal(digits, negative, token)
                error = caught.exception
                self.assertEqual((error.line, error.column, str(error)),
                                 (2, 3, "The integer literal is outside the signed 64-bit range."))

    def test_signed_division_and_remainder_do_not_use_floats(self):
        for a, b, q, r in [(-7, 2, -3, -1), (7, -2, -3, 1), (-7, -2, 3, -1),
                            (MIN_INT, 1, MIN_INT, 0), (MAX_INT, 2, 4611686018427387903, 1)]:
            with self.subTest(a=a, b=b):
                self.assertEqual(binary(lex(b"/")[0], IntValue(a), IntValue(b)), IntValue(q))
                self.assertEqual(binary(lex(b"%")[0], IntValue(a), IntValue(b)), IntValue(r))

    def test_invalid_arithmetic_points_to_the_operator(self):
        overflow = "Integer arithmetic exceeds the signed 64-bit range."
        for op, a, b, message in [
            ("+", MAX_INT, 1, overflow), ("-", MIN_INT, 1, overflow), ("*", MAX_INT, 2, overflow),
            ("/", MIN_INT, -1, overflow), ("%", MIN_INT, -1, overflow),
            ("/", 1, 0, "The divisor is zero."), ("%", 1, 0, "The divisor is zero."),
        ]:
            with self.subTest(op=op, a=a, b=b):
                token = lex(("\r\n\t" + op).encode())[0]
                with self.assertRaises(ExecutionError) as caught:
                    binary(token, IntValue(a), IntValue(b))
                error = caught.exception
                self.assertEqual((error.line, error.column, str(error)), (2, 2, message))
        with self.assertRaises(ExecutionError) as caught:
            unary(lex(b"-")[0], IntValue(MIN_INT))
        self.assertEqual(str(caught.exception), overflow)
