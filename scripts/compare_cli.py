"""Compare one Mini-C command across the C++, Rust, and Python implementations."""

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def compare(commands, arguments, source=None):
    expected = None
    for language, command in commands:
        result = subprocess.run([*command, *arguments], cwd=ROOT, input=source, capture_output=True, timeout=30)
        actual = (result.returncode, result.stdout, result.stderr)
        if expected is None:
            expected = actual
        elif expected != actual:
            for field, reference, value in zip(("exit status", "stdout", "stderr"), expected, actual):
                if value != reference:
                    raise ValueError(f"{arguments}: {field} differs. C++: {reference!r}. {language}: {value!r}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("tokens", "ast", "resolve", "check", "run"))
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--cpp", type=Path, default=ROOT.parent / "compiler-mini-c/build/minic")
    parser.add_argument("--rust", type=Path, default=ROOT.parent / "compiler-mini-rust/target/debug/compiler-mini-rust")
    args = parser.parse_args()
    commands = [("C++", [args.cpp.resolve()]), ("Rust", [args.rust.resolve()]),
                ("Python", [sys.executable, "-m", "minic"])]
    try:
        for path in args.files:
            if not path.is_file():
                parser.error(f"Expected a source file at {path}.")
            compare(commands, ["--" + args.mode, str(path.absolute())])
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")
    noun = "file" if len(args.files) == 1 else "files"
    print(f"All three implementations matched on {len(args.files)} {noun}.")


if __name__ == "__main__":
    main()
