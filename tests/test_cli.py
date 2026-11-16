import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    result = subprocess.run(
        [sys.executable, "-m", "minic", *args], cwd=ROOT, capture_output=True, timeout=5
    )
    return result.returncode, result.stdout, result.stderr


class CommandTests(unittest.TestCase):
    def test_ast_matches_the_reference_trees(self):
        for name in ("hello", "expressions", "calls", "control_flow"):
            with self.subTest(name=name):
                expected = (ROOT / f"tests/fixtures/{name}.ast").read_bytes()
                self.assertEqual(run_cli("--ast", f"examples/{name}.mc"), (0, expected, b""))

    def test_ast_finishes_lexing_before_it_reports_a_syntax_error(self):
        path = "tests/fixtures/lex_before_syntax.mc"
        expected = f'{path}:2:1: error: Unexpected character "@".\n'.encode("ascii")
        self.assertEqual(run_cli("--ast", path), (1, b"", expected))

    def test_syntax_error_applies_only_to_the_ast_command(self):
        path = "tests/fixtures/syntax_error.mc"
        message = 'Expected ";" after return value. Received RIGHT_BRACE.'
        expected = f"{path}:2:22: error: {message}\n".encode("ascii")
        self.assertEqual(run_cli("--ast", path), (1, b"", expected))
        code, listing, error = run_cli("--tokens", path)
        self.assertEqual((code, error), (0, b""))
        self.assertTrue(listing.endswith(b'3:1 EOF ""\n'))

    def test_examples_match_the_reference_listings(self):
        for name in ("hello", "lexer", "arrays"):
            with self.subTest(name=name):
                expected = (ROOT / f"tests/fixtures/{name}.tokens").read_bytes()
                self.assertEqual(run_cli("--tokens", f"examples/{name}.mc"), (0, expected, b""))

    def test_lexical_error_prints_no_partial_tokens(self):
        cases = [
            ("tests/fixtures/invalid.mc", '2:3: error: Unexpected character "@".'),
            ("tests/fixtures/unpaired_and.mc", '2:17: error: Unexpected character "&".'),
        ]
        for path, diagnostic in cases:
            with self.subTest(path=path):
                error = f"{path}:{diagnostic}\n".encode("ascii")
                self.assertEqual(run_cli("--tokens", path), (1, b"", error))

    def test_missing_file(self):
        self.assertEqual(
            run_cli("--tokens", "tests/fixtures/missing.mc"),
            (1, b"", b"tests/fixtures/missing.mc: error: Cannot open file.\n"),
        )

    def test_missing_file_argument(self):
        for mode in ("--tokens", "--ast"):
            with self.subTest(mode=mode):
                expected = f"minic: error: Expected {mode} <file>. Use --help for usage.\n"
                self.assertEqual(run_cli(mode), (1, b"", expected.encode("ascii")))

    def test_help_shows_the_module_command(self):
        expected = b"Usage: python3 -m minic --tokens <file>\n       python3 -m minic --ast <file>\n"
        for flag in ("-h", "--help"):
            with self.subTest(flag=flag):
                self.assertEqual(run_cli(flag), (0, expected, b""))
