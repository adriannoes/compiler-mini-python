from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from minic.bytecode_compiler import compile_bytecode
from minic.bytecode_optimizer import optimize_bytecode
from minic.interpreter import interpret
from minic.lexer import LexError, lex
from minic.parser import ParseError, parse
from minic.resolver import AnalysisError
from minic.runtime import VOID, BoolValue, ExecutionError, ExecutionLimits, IntValue
from minic.vm import execute_bytecode
from scripts.generated_cases import DEFAULT_SEED, Diagnostic, generate_cases
from scripts.validate_generated import validate


def outcome(call):
    try:
        return call()
    except (LexError, ParseError, AnalysisError, ExecutionError) as error:
        return Diagnostic(error.line, error.column, str(error))


def execute(source, mode):
    tree = parse(lex(source.encode("ascii")))
    if mode == "interpreter":
        return interpret(tree)
    code = compile_bytecode(tree)
    return execute_bytecode(optimize_bytecode(code) if mode == "optimized" else code)


class GeneratedCasesTests(unittest.TestCase):
    def test_seed_is_reproducible_and_does_not_change_global_random_state(self):
        state = random.getstate()
        first = generate_cases(31, 2)
        self.assertEqual(first, generate_cases(31, 2))
        self.assertNotEqual(first, generate_cases(32, 2))
        self.assertEqual(random.getstate(), state)
        self.assertEqual(len({case.name for case in first}), len(first))

    def test_default_corpus_matches_independent_expected_values_and_diagnostics(self):
        for case in generate_cases():
            if case.error is not None:
                expected = case.error
            elif case.value is None:
                expected = VOID
            elif type(case.value) is bool:
                expected = BoolValue(case.value)
            else:
                expected = IntValue(case.value)
            for mode in ("interpreter", "vm", "optimized"):
                with self.subTest(case=case.name, mode=mode):
                    self.assertEqual(outcome(lambda: execute(case.source, mode)), expected)

    def test_generated_loops_arrays_and_calls_agree_at_budget_boundaries(self):
        categories = {"loop", "saved_index", "recursion", "short_circuit"}
        for case in generate_cases(97, 1):
            if case.category not in categories or not case.name.endswith("-000"):
                continue
            tree = parse(lex(case.source.encode("ascii")))
            code = compile_bytecode(tree)
            optimized = optimize_bytecode(code)
            for steps in range(1, 81):
                for depth in (1, 2, 4):
                    with self.subTest(case=case.name, steps=steps, depth=depth):
                        limits = ExecutionLimits(steps, depth)
                        expected = outcome(lambda: interpret(tree, limits=limits))
                        self.assertEqual(outcome(lambda: execute_bytecode(code, limits=limits)), expected)
                        self.assertEqual(outcome(lambda: execute_bytecode(optimized, limits=limits)), expected)

    def test_timeout_preserves_the_seed_and_exact_failing_program(self):
        case = generate_cases(DEFAULT_SEED, 1)[0]
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(StringIO()):
            error = subprocess.TimeoutExpired(["compiler"], 1)
            with patch("scripts.validate_generated.subprocess.run", side_effect=error):
                with self.assertRaisesRegex(ValueError, "report.json"):
                    validate([case], [("reference", ["compiler"])], Path(directory), DEFAULT_SEED, 1, 1)
            source, = Path(directory).rglob("failure.mc")
            report = json.loads((source.parent / "report.json").read_text())
            self.assertEqual(source.read_text(), case.source)
            self.assertEqual(report["seed"], DEFAULT_SEED)
            self.assertEqual(report["failure"]["case"], case.name)
            self.assertIn("process_error", report["failure"]["actual"])

    def test_wrong_result_preserves_raw_output_for_reproduction(self):
        case = generate_cases(DEFAULT_SEED, 1)[0]
        actual = subprocess.CompletedProcess(["compiler"], 0, b"wrong\xff\n", b"")
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(StringIO()):
            with patch("scripts.validate_generated.subprocess.run", return_value=actual):
                with self.assertRaises(ValueError):
                    validate([case], [("reference", ["compiler"])], Path(directory), DEFAULT_SEED, 1, 1)
            source, = Path(directory).rglob("failure.mc")
            report = json.loads((source.parent / "report.json").read_text())
            self.assertEqual(bytes.fromhex(report["failure"]["actual"]["stdout_hex"]), actual.stdout)
            self.assertEqual(source.read_text(), case.source)
