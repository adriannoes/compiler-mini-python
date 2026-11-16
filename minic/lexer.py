"""Read Mini-C source bytes and record where each token starts."""

from dataclasses import dataclass
from enum import Enum, auto


class TokenKind(Enum):
    INT = auto()
    RETURN = auto()
    IDENTIFIER = auto()
    INTEGER = auto()
    LEFT_PAREN = auto()
    RIGHT_PAREN = auto()
    LEFT_BRACE = auto()
    RIGHT_BRACE = auto()
    SEMICOLON = auto()
    EOF = auto()


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str
    line: int
    column: int


class LexError(Exception):
    def __init__(self, line: int, column: int, message: str):
        super().__init__(message)
        self.line = line
        self.column = column


_KEYWORDS = {"int": TokenKind.INT, "return": TokenKind.RETURN}
_PUNCTUATION = {
    ord("("): TokenKind.LEFT_PAREN,
    ord(")"): TokenKind.RIGHT_PAREN,
    ord("{"): TokenKind.LEFT_BRACE,
    ord("}"): TokenKind.RIGHT_BRACE,
    ord(";"): TokenKind.SEMICOLON,
}


def _starts_name(byte: int) -> bool:
    return ord("a") <= byte <= ord("z") or ord("A") <= byte <= ord("Z") or byte == ord("_")


def _is_digit(byte: int) -> bool:
    return ord("0") <= byte <= ord("9")


def _unexpected_byte(byte: int) -> str:
    if 0x20 <= byte <= 0x7E:
        char = chr(byte)
        if char in ('"', "\\"):
            char = "\\" + char
        return f'Unexpected character "{char}".'
    return f"Unexpected byte 0x{byte:02X}."


class _Scanner:
    def __init__(self, source: bytes):
        self.source = source
        self.offset = 0
        self.line = 1
        self.column = 1

    def advance(self) -> None:
        byte = self.source[self.offset]
        self.offset += 1
        if byte in b"\r\n":
            if byte == ord("\r") and self.source.startswith(b"\n", self.offset):
                self.offset += 1
            self.line += 1
            self.column = 1
        else:
            self.column += 1

    def skip_trivia(self) -> None:
        """Consume whitespace and comments before the next token."""
        while self.offset < len(self.source):
            if self.source[self.offset] in b" \t\n\r\v\f":
                self.advance()
            elif self.source.startswith(b"//", self.offset):
                while self.offset < len(self.source) and self.source[self.offset] not in b"\r\n":
                    self.advance()
            elif self.source.startswith(b"/*", self.offset):
                line, column = self.line, self.column
                self.advance()
                self.advance()
                while not self.source.startswith(b"*/", self.offset):
                    if self.offset == len(self.source):
                        raise LexError(line, column, "Unterminated block comment.")
                    self.advance()
                self.advance()
                self.advance()
            else:
                return

    def next_token(self) -> Token:
        self.skip_trivia()
        start = self.offset
        line, column = self.line, self.column
        if start == len(self.source):
            return Token(TokenKind.EOF, "", line, column)

        byte = self.source[start]
        if _starts_name(byte):
            self.advance()
            while self.offset < len(self.source):
                byte = self.source[self.offset]
                if not (_starts_name(byte) or _is_digit(byte)):
                    break
                self.advance()
            text = self.source[start:self.offset].decode("ascii")
            return Token(_KEYWORDS.get(text, TokenKind.IDENTIFIER), text, line, column)

        if _is_digit(byte):
            while self.offset < len(self.source) and _is_digit(self.source[self.offset]):
                self.advance()
            text = self.source[start:self.offset].decode("ascii")
            return Token(TokenKind.INTEGER, text, line, column)

        if byte in _PUNCTUATION:
            self.advance()
            return Token(_PUNCTUATION[byte], chr(byte), line, column)
        raise LexError(line, column, _unexpected_byte(byte))


def lex(source: bytes) -> list[Token]:
    """Return all tokens through EOF or raise the first lexical error."""
    scanner = _Scanner(source)
    tokens = []
    while True:
        token = scanner.next_token()
        tokens.append(token)
        if token.kind is TokenKind.EOF:
            return tokens
