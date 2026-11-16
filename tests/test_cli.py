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
    def test_hello_matches_the_reference_listing(self):
        expected = (ROOT / "tests/fixtures/hello.tokens").read_bytes()
        self.assertEqual(run_cli("--tokens", "examples/hello.mc"), (0, expected, b""))

    def test_lexical_error_prints_no_partial_tokens(self):
        path = "tests/fixtures/invalid.mc"
        error = b'tests/fixtures/invalid.mc:2:3: error: Unexpected character "@".\n'
        self.assertEqual(run_cli("--tokens", path), (1, b"", error))

    def test_missing_file(self):
        self.assertEqual(
            run_cli("--tokens", "tests/fixtures/missing.mc"),
            (1, b"", b"tests/fixtures/missing.mc: error: Cannot open file.\n"),
        )

    def test_missing_file_argument(self):
        expected = b"minic: error: Expected --tokens <file>. Use --help for usage.\n"
        self.assertEqual(run_cli("--tokens"), (1, b"", expected))

    def test_help_shows_the_module_command(self):
        expected = b"Usage: python3 -m minic --tokens <file>\n"
        for flag in ("-h", "--help"):
            with self.subTest(flag=flag):
                self.assertEqual(run_cli(flag), (0, expected, b""))
