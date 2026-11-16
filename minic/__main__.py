"""Inspect a Mini-C source file through the selected compiler stage."""

import os
import sys

from .ast_printer import format_ast
from .lexer import LexError, lex
from .parser import ParseError, parse
from .resolver import AnalysisError, format_resolution, resolve_names
from .type_checker import check_types


MODES = ("--tokens", "--ast", "--resolve", "--check")


def error(message: str) -> int:
    sys.stderr.buffer.write(os.fsencode(message) + b"\n")
    return 1


def main(args: list[str]) -> int:
    if args in (["--help"], ["-h"]):
        print("Usage: " + "\n       ".join(f"python3 -m minic {mode} <file>" for mode in MODES))
        return 0
    if len(args) != 2 or args[0] not in MODES:
        mode = args[0] if args and args[0] in MODES else "--tokens"
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
        if args[0] == "--tokens":
            for token in tokens:
                row = f'{token.line}:{token.column} {token.kind.name} "{token.text}"\n'
                sys.stdout.buffer.write(row.encode("ascii"))
        else:
            tree = parse(tokens)
            if args[0] == "--ast":
                sys.stdout.buffer.write(format_ast(tree).encode("ascii"))
            elif args[0] == "--resolve":
                sys.stdout.buffer.write(format_resolution(resolve_names(tree)).encode("ascii"))
            else:
                check_types(tree)
    except (LexError, ParseError, AnalysisError) as exc:
        return error(f"{path}:{exc.line}:{exc.column}: error: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
