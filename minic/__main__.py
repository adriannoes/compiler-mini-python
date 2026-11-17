"""Inspect a Mini-C source file through the selected compiler stage."""

import os
import sys

from .ast_printer import format_ast
from .bytecode import format_bytecode
from .bytecode_compiler import compile_bytecode
from .bytecode_optimizer import optimize_bytecode
from .interpreter import interpret
from .lexer import LexError, lex
from .parser import ParseError, parse
from .resolver import AnalysisError, format_resolution, resolve_names
from .runtime import VOID, ExecutionError, Value
from .type_checker import check_types
from .vm import execute_bytecode


MODES = ("--tokens", "--ast", "--resolve", "--check", "--bytecode", "--bytecode-opt",
         "--run", "--run-vm", "--run-vm-opt")


def error(message: str) -> int:
    sys.stderr.buffer.write(os.fsencode(message) + b"\n")
    return 1


def print_result(value: Value) -> None:
    if value is not VOID:
        sys.stdout.buffer.write(f"{value}\n".encode("ascii"))


def main(args: list[str]) -> int:
    if args in (["--help"], ["-h"]):
        print("Usage: " + "\n       ".join(f"python3 -m minic {mode} <file>" for mode in MODES))
        return 0
    if len(args) != 2 or args[0] not in MODES:
        mode = args[0] if args and args[0] in MODES else "--tokens"
        return error(f"minic: error: Expected {mode} <file>. Use --help for usage.")

    mode, path = args
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
        if mode == "--tokens":
            for token in tokens:
                row = f'{token.line}:{token.column} {token.kind.name} "{token.text}"\n'
                sys.stdout.buffer.write(row.encode("ascii"))
        else:
            tree = parse(tokens)
            if mode == "--ast":
                sys.stdout.buffer.write(format_ast(tree).encode("ascii"))
            elif mode == "--resolve":
                sys.stdout.buffer.write(format_resolution(resolve_names(tree)).encode("ascii"))
            elif mode == "--check":
                check_types(tree)
            elif mode == "--run":
                print_result(interpret(tree))
            else:
                program = compile_bytecode(tree)
                if mode in ("--bytecode-opt", "--run-vm-opt"):
                    program = optimize_bytecode(program)
                if mode in ("--bytecode", "--bytecode-opt"):
                    sys.stdout.buffer.write(format_bytecode(program).encode("ascii"))
                else:
                    print_result(execute_bytecode(program))
    except (LexError, ParseError, AnalysisError, ExecutionError) as exc:
        return error(f"{path}:{exc.line}:{exc.column}: error: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
