"""Print the tokens or syntax tree of a Mini-C source file."""

import os
import sys

from .ast_printer import format_ast
from .lexer import LexError, lex
from .parser import ParseError, parse


def error(message: str) -> int:
    sys.stderr.buffer.write(os.fsencode(message) + b"\n")
    return 1


def main(args: list[str]) -> int:
    if args in (["--help"], ["-h"]):
        print("Usage: python3 -m minic --tokens <file>\n       python3 -m minic --ast <file>")
        return 0
    if len(args) != 2 or args[0] not in ("--tokens", "--ast"):
        mode = "--ast" if args and args[0] == "--ast" else "--tokens"
        return error(f"minic: error: Expected {mode} <file>. Use --help for usage.")

    path = args[1]
    try:
        source_file = open(path, "rb")
    except OSError:
        return error(f"{path}: error: Cannot open file.")

    try:
        with source_file:
            source = source_file.read()
    except OSError:
        return error(f"{path}: error: Cannot read file.")

    try:
        tokens = lex(source)
        if args[0] == "--ast":
            tree = parse(tokens)
            sys.stdout.buffer.write(format_ast(tree).encode("ascii"))
            return 0
    except (LexError, ParseError) as exc:
        return error(f"{path}:{exc.line}:{exc.column}: error: {exc}")

    for token in tokens:
        row = f'{token.line}:{token.column} {token.kind.name} "{token.text}"\n'
        sys.stdout.buffer.write(row.encode("ascii"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
