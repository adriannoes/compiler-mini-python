import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path

from minic.bytecode import BytecodeFunction, Instruction, InvalidBytecode, Op
from minic.bytecode_compiler import compile_bytecode
from minic.bytecode_optimizer import optimize_bytecode
from minic.control_flow import analyze_control_flow, format_control_flow
from minic.lexer import Token, TokenKind, lex
from minic.parser import parse
from minic.type_checker import Type


ROOT = Path(__file__).resolve().parents[1]
TOKEN = Token(TokenKind.IDENTIFIER, "sample", 1, 1)


def function(*operations):
    return BytecodeFunction(TOKEN, Type.VOID, 0, code=[
        Instruction(op, TOKEN, operand) for op, operand in operations
    ])


def compile_source(source):
    return compile_bytecode(parse(lex(source.encode("ascii"))))


class ControlFlowTests(unittest.TestCase):
    def test_loop_edges_and_dead_tail_have_distinct_blocks(self):
        code = function((Op.STEP, None), (Op.JUMP_IF_FALSE, 4), (Op.STEP, None),
                        (Op.JUMP, 0), (Op.RETURN_VOID, None), (Op.UNREACHABLE, None))
        graph = analyze_control_flow(code)
        self.assertEqual([(b.start, b.stop, b.successors) for b in graph.blocks], [
            (0, 2, (4, 2)), (2, 4, (0,)), (4, 5, ()), (5, 6, ()),
        ])
        self.assertEqual(graph.reachable, frozenset((0, 2, 4)))

    def test_jump_into_a_straight_sequence_starts_a_block(self):
        code = function((Op.STEP, None), (Op.JUMP_IF_TRUE, 3), (Op.STEP, None),
                        (Op.STEP, None), (Op.RETURN_VOID, None))
        graph = analyze_control_flow(code)
        self.assertEqual([(b.start, b.stop, b.successors) for b in graph.blocks], [
            (0, 2, (3, 2)), (2, 3, (3,)), (3, 5, ()),
        ])

    def test_identical_conditional_destinations_have_one_edge(self):
        graph = analyze_control_flow(function((Op.JUMP_IF_TRUE, 1), (Op.RETURN_VOID, None)))
        self.assertEqual(graph.instruction_successors, ((1,), ()))
        self.assertEqual(graph.blocks[0].successors, (1,))

    def test_dead_cycles_and_dead_fallthrough_do_not_create_entry_paths(self):
        graph = analyze_control_flow(function((Op.RETURN_VOID, None), (Op.JUMP, 1)))
        self.assertEqual(graph.reachable, frozenset((0,)))
        self.assertEqual(graph.blocks[1].successors, (1,))
        graph = analyze_control_flow(function((Op.RETURN_VOID, None), (Op.STEP, None)))
        self.assertEqual(graph.reachable, frozenset((0,)))
        self.assertEqual(graph.blocks[1].successors, (2,))

    def test_bad_jump_targets_fail_even_in_dead_blocks(self):
        for target in (-1, 2, True, None, 1.0):
            with self.subTest(target=target):
                with self.assertRaisesRegex(InvalidBytecode, "sample at instruction 1: The jump target"):
                    analyze_control_flow(function((Op.RETURN_VOID, None), (Op.JUMP, target)))

    def test_reachable_fallthrough_and_empty_functions_report_context(self):
        for code, message in (
            (function(), "sample at instruction 0: The function has no entry instruction"),
            (function((Op.STEP, None)), "sample at instruction 0: Control flow leaves"),
            (function((Op.JUMP_IF_FALSE, 0)), "sample at instruction 0: Control flow leaves"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(InvalidBytecode, message):
                    analyze_control_flow(code)

    def test_unknown_opcodes_report_their_instruction(self):
        code = function((Op.RETURN_VOID, None))
        code.code[0] = replace(code.code[0], op="RETURN_VOID")
        with self.assertRaisesRegex(InvalidBytecode, "sample at instruction 0: The opcode does not exist"):
            analyze_control_flow(code)

    def test_long_graphs_do_not_use_python_recursion(self):
        size = 5000
        code = function(*[(Op.JUMP, offset + 1) for offset in range(size - 1)], (Op.RETURN_VOID, None))
        graph = analyze_control_flow(code)
        self.assertEqual(len(graph.blocks), size)
        self.assertEqual(len(graph.reachable), size)

    def test_known_branch_is_structurally_reachable_until_optimization(self):
        source = (ROOT / "examples/optimization.mc").read_text()
        original = compile_source(source)
        graph = analyze_control_flow(original.functions[0])
        self.assertEqual([block.start for block in graph.blocks], [0, 23, 39, 50, 62])
        self.assertEqual(graph.reachable, frozenset((0, 23, 39, 50)))
        optimized = analyze_control_flow(optimize_bytecode(original).functions[0])
        self.assertEqual([(b.start, b.stop, b.successors) for b in optimized.blocks], [(0, 36, ())])

    def test_short_circuit_lists_both_possible_paths(self):
        original = compile_source("bool main(){return true || false;}")
        graph = analyze_control_flow(original.functions[0])
        branch = next(block for block in graph.blocks if len(block.successors) == 2)
        self.assertTrue(set(branch.successors) <= graph.reachable)
        self.assertIn("unreachable", format_control_flow(original))

    def test_inspection_script_reports_graphs_and_positioned_errors(self):
        result = subprocess.run([sys.executable, "scripts/inspect_bytecode.py", "--optimized",
                                 "examples/optimization.mc"], cwd=ROOT, capture_output=True, timeout=10)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (
            0, b'control flow\nfunction 0 "main"\n  block 0..35 reachable -> none\nend\n', b""))
        result = subprocess.run([sys.executable, "scripts/inspect_bytecode.py", "tests/fixtures/invalid.mc"],
                                cwd=ROOT, capture_output=True, timeout=10)
        self.assertEqual((result.returncode, result.stdout), (1, b""))
        self.assertEqual(result.stderr, b'tests/fixtures/invalid.mc:2:3: error: Unexpected character "@".\n')
