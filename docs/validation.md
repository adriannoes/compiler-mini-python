# Validate generated programs

The [case generator](../scripts/generated_cases.py) produces bounded Mini-C programs from a recorded random seed.
A seed reproduces the same cases for this generator version. It leaves Python's global random state unchanged.
Independent expected values supplement comparisons between the implementations.

## What the corpus covers

The default seed is `20261117`, and the default round count is eight.
Each round produces twelve programs. Thirty fixed cases add numeric boundaries and specified failures, for 126 cases in total.

| Cases | Behavior |
|---|---|
| Arithmetic | Addition, subtraction, multiplication, signed division, and signed remainder |
| Evaluation order | Chained state changes, argument order, and an array target saved before its value changes the index |
| Booleans | Distinct boolean values, short-circuit state changes, skipped failures, and boolean arrays |
| Control flow | Finite loops, recursive calls, and void calls |
| Storage | Filled arrays, maximum array length, missing values, and array declarations inside loops |
| Numeric boundaries | Signed minimum and maximum, long literal spelling, overflow, and zero divisors |
| Static errors | Wrong operand types, invalid lengths and indices, argument counts, unresolved names, lexical errors, and syntax errors |

Successful cases use formulas outside the compiler as their oracles. An oracle supplies an independently expected result.
The generator uses Python's exact `Fraction` arithmetic for division, then truncates its rational value toward zero.
It calculates the remainder from that quotient. The oracle never calls Mini-C's arithmetic functions.
Loop and recursion totals use closed formulas. Expected diagnostics specify the message, line, and column before any engine runs.

## Compare the Python engines

From the repository root, run the generated regression tests with Python 3.9 or later.

```sh
PYTHONPATH=tests python3 -m unittest test_generated_cases
```

The tests execute the default corpus through the AST interpreter, VM, and optimized VM.
All 378 outcomes must match independent values or diagnostics. Typed wrappers distinguish `bool` from `int`, including values such as `true` and `1`.
Void results also have a distinct representation.

Four additional generated programs use seed `97` for boundary comparisons.
They combine loops, recursion, saved array indices, and short-circuit expressions.
Each program runs with source-step limits from 1 through 80 and call-depth limits of 1, 2, and 4.
These 960 configurations compare all three engines, including the exact diagnostic position when a limit interrupts execution.

The [verifier tests](../tests/test_bytecode_verifier.py) separately supply malformed instructions and incompatible paths to the bytecode analysis.
The [stack analysis guide](stack-analysis.md) explains that analysis.
Source generation tests the complete compiler pipeline, while malformed bytecode tests the verifier directly.

## Compare all three implementations

The [runner](../scripts/validate_generated.py) requires built C++ and Rust reference executables.
It searches ancestor directories for the sibling repositories, which supports both the main checkout and nested worktrees.
Python always executes the compiler in the checkout that contains the runner.

From the Python repository root, run the default corpus.

```sh
python3 scripts/validate_generated.py --seed 20261117 --rounds 8
```

Each case runs in `--run`, `--run-vm`, and `--run-vm-opt` for C++, Rust, and Python.
The complete default run performs 1,134 command comparisons.
Each command must match the independent expected exit status, standard output, and standard error byte for byte.
Every implementation receives the same temporary source path, so diagnostic paths also match.

To select reference executables explicitly, use their paths.

```sh
python3 scripts/validate_generated.py --rounds 1 --cpp ../compiler-mini-c/build/minic --rust ../compiler-mini-rust/target/debug/compiler-mini-rust
```

A one-round run selects 42 cases and performs 378 command comparisons.
Use `--limit 12` for the first twelve cases. This limit omits the fixed cases at the end of the corpus.
Use `--timeout 10` to set the maximum seconds for each process. Ten seconds is also the default.
These bounds prevent one reference process from blocking the entire comparison indefinitely.

## Inspect a failure

Each invocation creates a separate run directory under `build/validation` and prints its path.
Use `--output PATH` to select another parent directory.
The runner writes `report.json` with the seed, round count, selected case count, commands, category counts, and attempted comparison count.

On a mismatch or process failure, the runner also saves the exact input as `failure.mc`.
The report identifies the implementation, mode, command, and expected outcome.
Output bytes use hexadecimal strings so invalid UTF-8 cannot lose information.
Timeouts and process startup errors include their error text.
The runner removes temporary comparison inputs after the run. The report and failed source remain.

To reproduce a failed execution, use the saved file with the command's implementation and mode.
The diagnostic path changes to the saved path. The source line, column, and message remain comparable.
To regenerate the full case sequence, use the recorded seed and round count with the same generator version.

## Acceptance and limits

From the repository root, run the complete compiler suite after integrating changes.

```sh
python3 -m unittest discover -s tests
```

Then run the generated reference comparison and the documented parsing, bytecode, and LLVM laboratories.
The compiler suite and generated Python tests require only Python's standard library.
Reference comparisons and the separate LLVM laboratory require their documented executables.

The extension acceptance run used Python 3.14.7, Apple Clang 17, and Rust 1.98.1 on macOS.

| Gate | Observed result |
|---|---|
| Complete Python suite | 131 tests passed, including generated outcomes and 960 execution-budget configurations. |
| Generated reference corpus | 126 cases passed all 1,134 command comparisons. |
| Existing examples, fixtures, and lab sources | 24 files matched across all nine modes and three implementations, for 648 commands. |
| LLVM laboratory | All 45 executions passed across nine paths. |
| Parsing, graph, and stack study commands | All nine documented commands passed. |
| Documentation | All 121 local links resolved, and the structural prose scan reported no findings. |

Python's parser also accepted all 38 Python files with its Python 3.9 syntax configuration.
The suite did not run on a Python 3.9 interpreter.

The corpus samples a finite set of program shapes and bounded values. It does not enumerate every valid or invalid Mini-C program.
Agreement between engines can miss a shared defect, which is why the successful cases also use independent expected results.
Those oracles and fixed diagnostic cases still do not prove exhaustive correctness.
Performance measurements, arbitrary hostile object graphs, and all possible recursion or memory limits are outside this corpus.
