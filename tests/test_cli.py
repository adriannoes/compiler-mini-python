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
    def test_optimized_listing_and_execution_match_the_reference_example(self):
        path = "examples/optimization.mc"
        expected = (ROOT / "tests/fixtures/optimization.optimized.bytecode").read_bytes()
        self.assertEqual(run_cli("--bytecode-opt", path), (0, expected, b""))
        self.assertEqual(run_cli("--run-vm-opt", path), (0, b"24\n", b""))

    def test_bytecode_matches_the_reference_instructions_and_positions(self):
        for name in ("hello", "short_circuit"):
            with self.subTest(name=name):
                expected = (ROOT / f"tests/fixtures/{name}.bytecode").read_bytes()
                self.assertEqual(run_cli("--bytecode", f"examples/{name}.mc"), (0, expected, b""))

    def test_bytecode_checks_the_whole_source_before_it_prints(self):
        for path in ("examples/expressions.mc", "examples/type_error.mc",
                     "tests/fixtures/syntax_error.mc", "tests/fixtures/lex_before_syntax.mc"):
            with self.subTest(path=path):
                expected = run_cli("--check", path)
                self.assertEqual(expected[:2], (1, b""))
                self.assertEqual(run_cli("--bytecode", path), expected)

    def test_run_prints_the_entry_result_and_exits_successfully(self):
        for path, expected in [
            ("examples/interpreter.mc", b"42\n"), ("examples/factorial.mc", b"720\n"),
            ("examples/fibonacci.mc", b"55\n"), ("examples/short_circuit.mc", b"true\n"),
            ("tests/fixtures/void_main.mc", b""),
        ]:
            for mode in ("--run", "--run-vm", "--run-vm-opt"):
                with self.subTest(path=path, mode=mode):
                    self.assertEqual(run_cli(mode, path), (0, expected, b""))

    def test_run_reports_the_first_execution_error_without_a_result(self):
        path = "examples/runtime_error.mc"
        self.assertEqual(run_cli("--check", path), (0, b"", b""))
        diagnostic = b'examples/runtime_error.mc:3:15: error: The variable "value" has no value.\n'
        for mode in ("--run", "--run-vm", "--run-vm-opt"):
            with self.subTest(mode=mode):
                self.assertEqual(run_cli(mode, path), (1, b"", diagnostic))

    def test_resolution_matches_the_reference_scopes_and_recursion(self):
        for name in ("scopes", "recursion"):
            with self.subTest(name=name):
                expected = (ROOT / f"tests/fixtures/{name}.resolution").read_bytes()
                self.assertEqual(run_cli("--resolve", f"examples/{name}.mc"), (0, expected, b""))

    def test_type_error_stops_only_the_type_checker(self):
        path = "examples/type_error.mc"
        code, listing, error = run_cli("--resolve", path)
        self.assertEqual((code, error), (0, b""))
        self.assertIn(b'VARIABLE "ready"', listing)
        self.assertEqual(run_cli("--check", path),
                         (1, b"", b"examples/type_error.mc:3:16: error: Expected type bool. Received int.\n"))
        self.assertEqual(run_cli("--check", "examples/types.mc"), (0, b"", b""))

    def test_undeclared_name_prints_no_partial_analysis(self):
        error = b'examples/expressions.mc:9:10: error: Undeclared name "left".\n'
        for mode in ("--resolve", "--check"):
            with self.subTest(mode=mode):
                self.assertEqual(run_cli(mode, "examples/expressions.mc"), (1, b"", error))

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
        for mode in ("--tokens", "--ast", "--resolve", "--check", "--bytecode", "--bytecode-opt",
                     "--run", "--run-vm", "--run-vm-opt"):
            with self.subTest(mode=mode):
                expected = f"minic: error: Expected {mode} <file>. Use --help for usage.\n"
                self.assertEqual(run_cli(mode), (1, b"", expected.encode("ascii")))

    def test_help_shows_the_module_command(self):
        expected = (b"Usage: python3 -m minic --tokens <file>\n       python3 -m minic --ast <file>\n"
                    b"       python3 -m minic --resolve <file>\n       python3 -m minic --check <file>\n"
                    b"       python3 -m minic --bytecode <file>\n       python3 -m minic --bytecode-opt <file>\n"
                    b"       python3 -m minic --run <file>\n       python3 -m minic --run-vm <file>\n"
                    b"       python3 -m minic --run-vm-opt <file>\n")
        for flag in ("-h", "--help"):
            with self.subTest(flag=flag):
                self.assertEqual(run_cli(flag), (0, expected, b""))
