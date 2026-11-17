"""Print the control-flow graph of a Mini-C source file."""

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from minic.bytecode import InvalidBytecode
from minic.bytecode_compiler import compile_bytecode
from minic.bytecode_optimizer import optimize_bytecode
from minic.control_flow import format_control_flow
from minic.lexer import LexError, lex
from minic.parser import ParseError, parse
from minic.resolver import AnalysisError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--optimized", action="store_true", help="Inspect the optimized instructions.")
    args = parser.parse_args()
    try:
        source = args.file.read_bytes()
    except OSError:
        parser.exit(1, f"{args.file}: error: Cannot read file.\n")
    try:
        program = compile_bytecode(parse(lex(source)))
        if args.optimized:
            program = optimize_bytecode(program)
        report = format_control_flow(program)
    except (LexError, ParseError, AnalysisError) as error:
        parser.exit(1, f"{args.file}:{error.line}:{error.column}: error: {error}\n")
    except InvalidBytecode as error:
        parser.exit(1, f"{args.file}: error: {error}\n")
    sys.stdout.write(report)


if __name__ == "__main__":
    main()
