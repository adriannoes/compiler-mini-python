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
