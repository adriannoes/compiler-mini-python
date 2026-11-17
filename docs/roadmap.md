# Study roadmap

The Python implementation follows the Mini-C language defined by the C++ project and compares its design with the Rust implementation.
Each completed phase adds an observable command or a documented explanation of that command.
The phase numbers below describe the Python sequence.

## Completed sequence

| Phase | What to learn | Observable delivery | Regression tests |
|---|---|---|---|
| 1 | Token kinds, original text, and source positions | `--tokens examples/hello.mc` | `test_lexer`, `test_cli` |
| 2 | Keyword boundaries, longest operator match, comments, and brackets | `--tokens examples/lexer.mc` and `examples/arrays.mc` | `test_lexer`, `test_cli` |
| 3 | Recursive descent, precedence, assignment grouping, and AST nodes | `--ast examples/control_flow.mc` | `test_parser`, `test_cli` |
| 4 | Lexical scope, bindings, scalar types, and return guarantees | `--resolve examples/scopes.mc` and `--check examples/type_error.mc` | `test_resolver`, `test_type_checker`, `test_cli` |
| 5 | Runtime values, checked arithmetic, evaluation order, and calls | `--run examples/factorial.mc` prints `720` | `test_runtime`, `test_interpreter`, `test_cli` |
| 6 | Constant pools, local slots, instruction emission, and jump targets | `--bytecode examples/short_circuit.mc` | `test_bytecode`, `test_cli` |
| 7 | Instruction dispatch, operand stacks, call frames, and execution limits | `--run-vm examples/factorial.mc` prints `720` | `test_vm`, `test_runtime`, `test_cli` |
| 8 | Constant folding, basic blocks, and unreachable code | `--run-vm-opt examples/optimization.mc` prints `24` | `test_optimizer`, `test_vm`, `test_cli` |
| 9 | Fixed storage, initialization, bounds, and saved assignment indices | All three execution modes print `10` for `examples/arrays.mc` | `test_arrays_frontend`, `test_arrays_runtime`, `test_cli` |
| 10 | Relate the implementation to its language contract and history | [Architecture](architecture.md), [language rules](language.md), and this roadmap | Documented commands, reference comparisons, and link inspection |

Run the command arguments in the delivery column with `python3 -m minic` from the repository root.
The type-error example in phase 4 exits with status 1 and reports a boolean initializer with an integer value.
The other listed execution examples exit with status 0.

From the repository root, select the relevant test modules with the standard library.

```sh
PYTHONPATH=tests python3 -m unittest test_arrays_frontend test_arrays_runtime test_cli
```

The existing [README](../README.md#tests) describes the command for the complete suite.
Expected token, tree, binding, and bytecode listings come from the C++ reference.
The command tests compare standard output, standard error, and exit status.

## Match deliveries across projects

The C++ roadmap separates name resolution from type checking and adds a separate parsing theory phase.
Rust combines bytecode compilation with VM execution, then combines optimization with arrays.
The following mapping follows the observable deliveries in both histories.
[C++ roadmap](../../compiler-mini-c/docs/roadmap.md), [Rust roadmap](../../compiler-mini-rust/docs/roadmap.md).

| Python phase | C++ phase and source reference | Rust phase and source reference |
|---|---|---|
| 1 | Phase 1, [lexer.cpp](../../compiler-mini-c/src/lexer.cpp) | Phase 1, [lexer.rs](../../compiler-mini-rust/src/lexer.rs) |
| 2 | Phase 1, [lexer.cpp](../../compiler-mini-c/src/lexer.cpp) | Phase 2, [lexer.rs](../../compiler-mini-rust/src/lexer.rs) |
| 3 | Phase 2, [parser.cpp](../../compiler-mini-c/src/parser.cpp) | Phase 3, [parser.rs](../../compiler-mini-rust/src/parser.rs) |
| 4 | Phases 4 and 5, [name_resolution.cpp](../../compiler-mini-c/src/name_resolution.cpp) and [type_checker.cpp](../../compiler-mini-c/src/type_checker.cpp) | Phase 4, [resolver.rs](../../compiler-mini-rust/src/resolver.rs) and [type_checker.rs](../../compiler-mini-rust/src/type_checker.rs) |
| 5 | Phases 6 and 7, [interpreter.cpp](../../compiler-mini-c/src/interpreter.cpp) and [runtime.cpp](../../compiler-mini-c/src/runtime.cpp) | Phase 5, [interpreter.rs](../../compiler-mini-rust/src/interpreter.rs) and [runtime.rs](../../compiler-mini-rust/src/runtime.rs) |
| 6 | Phase 8, [bytecode_compiler.cpp](../../compiler-mini-c/src/bytecode_compiler.cpp) | Phase 6, [bytecode_compiler.rs](../../compiler-mini-rust/src/bytecode_compiler.rs) |
| 7 | Phase 9, [vm.cpp](../../compiler-mini-c/src/vm.cpp) | Phase 6, [vm.rs](../../compiler-mini-rust/src/vm.rs) |
| 8 | Phase 10, [bytecode_optimizer.cpp](../../compiler-mini-c/src/bytecode_optimizer.cpp) | Phase 7, [bytecode_optimizer.rs](../../compiler-mini-rust/src/bytecode_optimizer.rs) |
| 9 | Phase 11, [arrays_frontend_test.cpp](../../compiler-mini-c/tests/arrays_frontend_test.cpp) and [arrays_runtime_test.cpp](../../compiler-mini-c/tests/arrays_runtime_test.cpp) | Phase 7, [type_checker.rs](../../compiler-mini-rust/src/type_checker.rs) and [vm.rs](../../compiler-mini-rust/src/vm.rs) |
| 10 | Phase 13, [architecture.md](../../compiler-mini-c/docs/architecture.md) and [language.md](../../compiler-mini-c/docs/language.md) | Phase 8, [language.md](../../compiler-mini-rust/docs/language.md) and [compare_cli.py](../../compiler-mini-rust/scripts/reference/compare_cli.py) |

Python introduced bracket tokens in phase 2 and array syntax in phase 9.
C++ introduced bracket tokens with arrays in phase 11. Token recognition and syntactic support can therefore land in different phases.

## Read the development history

These commits identify executable milestones in each repository. Later commits extend the behavior of those milestones.

| Delivery | Python commit | C++ commit | Rust commit |
|---|---|---|---|
| First token command | `f3447e5` | `cd7e4f6` | `27e98a8` |
| Complete scalar lexer | `e5e8a32` | `2e2fa38` | `41b8bff` |
| Parser control flow and AST command | `446d829` | `473ba8a` | `bcd0cda` |
| Name and type commands | `31e4645` | `3263da1` | `0ea15b8` |
| Interpreter with calls and loops | `6132ebe` | `5d34566` | `dc385ad` |
| Bytecode command | `c678e13` | `f2d6f01` | `52bae64` |
| VM command | `3494e79` | `29238bf` | `967510f` |
| Optimized commands | `60ea28c` | `a5bbd5a` | `80ddd78` |
| Arrays across stages | `df3dd18` | `dc2feab` | `bf68976` |

From the Python repository root, read the ordered implementation commits and inspect the first lexer increment.

```sh
git log --reverse --oneline -- minic
git show f3447e5 -- minic
git -C ../compiler-mini-c show cd7e4f6 -- src
git -C ../compiler-mini-rust show 27e98a8 -- src
```

The C++ interpreter first acquired a command in `aac195e`. Its later commits added control flow, source-step limits, and isolated function calls.
The Python phase 5 command included those capabilities in its initial delivery.

## Compare a phase

With both reference executables available, compare a selected mode from the Python repository root.

```sh
python3 scripts/compare_cli.py tokens examples/hello.mc tests/fixtures/invalid.mc
python3 scripts/compare_cli.py bytecode-opt examples/optimization.mc
python3 scripts/compare_cli.py run-vm-opt examples/arrays.mc examples/array_error.mc
```

The script prints a success summary only when both output streams and the exit status agree.
It accepts reference executable paths through `--cpp` and `--rust`.
The checks above include a lexical error, a folded constant branch, and an uninitialized array read.

The comparison contract covers the selected command and input files.
Python's help describes `python3 -m minic`, while the predecessor help describes their executables.
The Python CLI reports a directory input as `Cannot open file.` on the current macOS host.
The C++ and Rust references treat that input as empty source. The file comparison script requires regular files.
