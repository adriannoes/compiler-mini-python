# Analyze the bytecode operand stack

The operand stack holds temporary values for one function call.
Arguments enter local slots before execution, so a function starts with an empty operand stack.
The [verifier](../minic/bytecode_verifier.py) follows each reachable block in the [control-flow graph](control-flow.md) without computing program values.

The VM verifies bytecode before execution. The optimizer verifies its input and output.
These checks detect malformed instructions before an execution reaches them.
They also detect type errors in a branch that a runtime condition skips.

## Trace a nested call

From the repository root, print the [call example](../examples/calls.mc).

```sh
python3 -m minic --bytecode examples/calls.mc
```

In `add(1, add(2, 3))`, the caller retains its first argument while computing the nested call.
The rightmost value is the top of the stack.

| Instruction in `main` | Operation | Stack after execution |
|---|---|---|
| 7 | Load the outer argument. | `[1]` |
| 10 | Load the first inner argument. | `[1, 2]` |
| 12 | Load the second inner argument. | `[1, 2, 3]` |
| 13 | Call `add(2, 3)`. | `[1, 5]` |
| 14 | Call `add(1, 5)`. | `[6]` |

The maximum height is three in `main` and two in `add`.
The verifier uses the parameter types and result type to determine each call's stack effect.
A call to a `void` function consumes its arguments and produces no operand value.

## Compare incoming types

An incoming state is the ordered operand-type sequence at a block entry.
Every edge into that block must supply the same sequence.
Equal heights are insufficient: `[int, int]` and `[bool, int]` disagree below the top value.
The verifier reports the function, instruction offset, and first mismatched slot.

The same rule applies when a loop returns to its condition.
The loop's first entry and later iterations must supply equal type sequences.
Once another edge supplies the recorded state, the verifier needs no second visit to the block.

From the repository root, compare the maximum heights before and after optimization.

```python
from pathlib import Path
from minic.bytecode_compiler import compile_bytecode
from minic.bytecode_optimizer import optimize_bytecode
from minic.bytecode_verifier import verify_bytecode
from minic.lexer import lex
from minic.parser import parse

tree = parse(lex(Path("examples/short_circuit.mc").read_bytes()))
original = compile_bytecode(tree)
for name, code in (("original", original), ("optimized", optimize_bytecode(original))):
    for report in verify_bytecode(code):
        print(name, report.function_name, report.max_stack)
```

The example prints `original main 2` and `optimized main 1`.
The original graph includes both paths through `true || (1 / 0 == 0)`.
The optimizer removes the skipped path, which lowers the maximum height.
The verifier checks operand types without dividing by zero or converting the integer literals to runtime values.

## Validation boundaries

The verifier first examines every function's metadata and every instruction's shape.
Indices must be Python integers, excluding booleans. Instructions without operands must contain `None` in their operand field.
Locals require scalar element types, and arrays require lengths from 1 through 1024.
Parameters occupy the first local slots and cannot be arrays.

The verifier then propagates operand types through blocks reachable from each function's entry.
It examines both conditional successors without predicting the condition's value.
Each return must match its function signature and leave no temporary values.
Reaching `UNREACHABLE` is invalid bytecode.

Unreachable blocks have no incoming stack state. Their instruction shapes still require valid opcodes, indices, and metadata.
The verifier does not invent a stack to evaluate instructions after a return.
The verifier accepts a dead cycle because execution cannot reach it from that function's entry.

Every reachable cycle within a function must contain a `STEP` instruction.
The verifier removes those nodes conceptually and rejects any cycle that remains.
This rule prevents a repeated local instruction path from bypassing the source-step budget.
Recursive calls remain subject to the VM's separate call-depth limit.

Integer constants require decimal ASCII digits and a boolean sign field. Validation does not enforce the signed 64-bit value range.
Execution still determines integer overflow, division by zero, uninitialized reads, and array bounds.
The verifier does not prove that an array has active storage or that an execution terminates.

## Implementation cost and ownership

`verify_bytecode(program)` returns one immutable `FunctionVerification` per function, in source order.
Each report contains the function index, function name, maximum stack height, and incoming type tuples keyed by block entry offset.
The report's `incoming` field is an immutable tuple of `(offset, types)` pairs.

The analyzer keeps one mutable stack while it processes a block. It saves a type tuple at each reachable block entry.
This avoids copying a deep stack for every instruction in a long block.
Storage includes the graph and saved block-entry stacks. Graph traversal and stack propagation use explicit work lists.

Bytecode function records contain mutable lists, so the verifier does not cache previous results.
Each public execution and optimization request analyzes the current records again.
This costs an additional pass but detects mutations after an earlier successful analysis.

The [Rust verifier](https://github.com/adriannoes/compiler-mini-rust/blob/main/src/bytecode/stack_analysis.rs) supplies a test-only comparison for stack heights and types.
Python uses the analysis during execution and optimization and also checks instruction metadata and source-step cycles.

From the repository root, run the verifier tests.

```sh
PYTHONPATH=tests python3 -m unittest test_bytecode_verifier
```

The tests include nested calls, arrays, conflicting paths, malformed records, skipped failures, repeated mutations, and a large operand stack.
