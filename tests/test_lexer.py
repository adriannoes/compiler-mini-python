import unittest

from minic.lexer import LexError, Token, TokenKind, lex


class LexerTests(unittest.TestCase):
    def test_names_and_numbers_keep_their_spelling(self):
        self.assertEqual(
            lex(b"int int2 Return _return 007a"),
            [
                Token(TokenKind.INT, "int", 1, 1),
                Token(TokenKind.IDENTIFIER, "int2", 1, 5),
                Token(TokenKind.IDENTIFIER, "Return", 1, 10),
                Token(TokenKind.IDENTIFIER, "_return", 1, 17),
                Token(TokenKind.INTEGER, "007", 1, 25),
                Token(TokenKind.IDENTIFIER, "a", 1, 28),
                Token(TokenKind.EOF, "", 1, 29),
            ],
        )

    def test_comments_count_bytes_and_separate_tokens(self):
        self.assertEqual(
            lex(b"int/*\xc3\xa9*/return\r\n//\xff\r\t{\n}"),
            [
                Token(TokenKind.INT, "int", 1, 1),
                Token(TokenKind.RETURN, "return", 1, 10),
                Token(TokenKind.LEFT_BRACE, "{", 3, 2),
                Token(TokenKind.RIGHT_BRACE, "}", 4, 1),
                Token(TokenKind.EOF, "", 4, 2),
            ],
        )

    def test_keywords_require_an_exact_case_sensitive_name(self):
        for word in ("int", "bool", "void", "if", "else", "while", "return", "true", "false"):
            for name in (word + "2", "_" + word, word.upper()):
                with self.subTest(name=name):
                    self.assertEqual(lex(name.encode("ascii"))[0], Token(TokenKind.IDENTIFIER, name, 1, 1))

    def test_operators_take_the_longest_supported_spelling(self):
        cases = [
            (b"===", ["==", "="]),
            (b"!==", ["!=", "="]),
            (b"<==>==", ["<=", "=", ">=", "="]),
            (b"&&!!||", ["&&", "!", "!", "||"]),
            (b"-42,++--+=/=", ["-", "42", ",", "+", "+", "-", "-", "+", "=", "/", "="]),
        ]
        for source, spellings in cases:
            with self.subTest(source=source):
                self.assertEqual([token.text for token in lex(source)[:-1]], spellings)

    def test_comments_separate_operators_from_each_other(self):
        self.assertEqual(
            lex(b"=/**/= 8/2// /\r\n/"),
            [
                Token(TokenKind.ASSIGN, "=", 1, 1),
                Token(TokenKind.ASSIGN, "=", 1, 6),
                Token(TokenKind.INTEGER, "8", 1, 8),
                Token(TokenKind.SLASH, "/", 1, 9),
                Token(TokenKind.INTEGER, "2", 1, 10),
                Token(TokenKind.SLASH, "/", 2, 1),
                Token(TokenKind.EOF, "", 2, 2),
            ],
        )

    def test_unpaired_logical_operator_points_to_the_unpaired_byte(self):
        for source, column in [(b"&&&", 3), (b"|||", 3), (b"&/**/&", 1), (b"| |", 1)]:
            with self.subTest(source=source):
                with self.assertRaises(LexError) as caught:
                    lex(source)
                self.assertEqual((caught.exception.line, caught.exception.column), (1, column))

    def test_eof_follows_the_last_byte(self):
        for source, column in [(b"", 1), (b"//", 3), (b"/* /* */", 9)]:
            with self.subTest(source=source):
                self.assertEqual(lex(source), [Token(TokenKind.EOF, "", 1, column)])

    def test_unterminated_comment_points_to_its_opening_slash(self):
        with self.assertRaises(LexError) as caught:
            lex(b"return\r\n  /*/\nint")
        error = caught.exception
        self.assertEqual(
            (error.line, error.column, str(error)), (2, 3, "Unterminated block comment.")
        )

    def test_unexpected_bytes_preserve_the_first_error(self):
        cases = [
            (b'"', r'Unexpected character "\"".'),
            (b"\\", r'Unexpected character "\\".'),
            (b"\x00", "Unexpected byte 0x00."),
            (b"\xff", "Unexpected byte 0xFF."),
        ]
        for byte, message in cases:
            with self.subTest(byte=byte):
                with self.assertRaises(LexError) as caught:
                    lex(b";\n\t" + byte + b"@")
                error = caught.exception
                self.assertEqual((error.line, error.column, str(error)), (2, 2, message))
