"""Read Mini-C source bytes and record where each token starts."""

from dataclasses import dataclass
from enum import Enum, auto


class TokenKind(Enum):
    INT = auto()
    BOOL = auto()
    VOID = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    RETURN = auto()
    TRUE = auto()
    FALSE = auto()
    IDENTIFIER = auto()
    INTEGER = auto()
    LEFT_PAREN = auto()
    RIGHT_PAREN = auto()
    LEFT_BRACE = auto()
    RIGHT_BRACE = auto()
    LEFT_BRACKET = auto()
    RIGHT_BRACKET = auto()
    SEMICOLON = auto()
    COMMA = auto()
    ASSIGN = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    EQUAL_EQUAL = auto()
    BANG_EQUAL = auto()
    LESS = auto()
    LESS_EQUAL = auto()
    GREATER = auto()
    GREATER_EQUAL = auto()
    BANG = auto()
    AND_AND = auto()
    OR_OR = auto()
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


_KEYWORDS = {
    "int": TokenKind.INT,
    "bool": TokenKind.BOOL,
    "void": TokenKind.VOID,
    "if": TokenKind.IF,
    "else": TokenKind.ELSE,
    "while": TokenKind.WHILE,
    "return": TokenKind.RETURN,
    "true": TokenKind.TRUE,
    "false": TokenKind.FALSE,
}
_SYMBOLS = {
    b"(": TokenKind.LEFT_PAREN,
    b")": TokenKind.RIGHT_PAREN,
    b"{": TokenKind.LEFT_BRACE,
    b"}": TokenKind.RIGHT_BRACE,
    b"[": TokenKind.LEFT_BRACKET,
    b"]": TokenKind.RIGHT_BRACKET,
    b";": TokenKind.SEMICOLON,
    b",": TokenKind.COMMA,
    b"=": TokenKind.ASSIGN,
    b"+": TokenKind.PLUS,
    b"-": TokenKind.MINUS,
    b"*": TokenKind.STAR,
    b"/": TokenKind.SLASH,
    b"%": TokenKind.PERCENT,
    b"==": TokenKind.EQUAL_EQUAL,
    b"!=": TokenKind.BANG_EQUAL,
    b"<": TokenKind.LESS,
    b"<=": TokenKind.LESS_EQUAL,
    b">": TokenKind.GREATER,
    b">=": TokenKind.GREATER_EQUAL,
    b"!": TokenKind.BANG,
    b"&&": TokenKind.AND_AND,
    b"||": TokenKind.OR_OR,
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

        spelling = self.source[start:start + 2]
        if spelling not in _SYMBOLS:
            spelling = self.source[start:start + 1]
        kind = _SYMBOLS.get(spelling)
        if kind is None:
            raise LexError(line, column, _unexpected_byte(byte))
        for _ in spelling:
            self.advance()
        return Token(kind, spelling.decode("ascii"), line, column)


def lex(source: bytes) -> list[Token]:
    """Return all tokens through EOF or raise the first lexical error."""
    scanner = _Scanner(source)
    tokens = []
    while True:
        token = scanner.next_token()
        tokens.append(token)
        if token.kind is TokenKind.EOF:
            return tokens
