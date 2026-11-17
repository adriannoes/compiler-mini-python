# Compare Mini-C bytecode with LLVM

The Python compiler translates Mini-C into bytecode for its virtual machine.
The separate [loop laboratory](../labs/loop-ir/README.md) compiles small C and Rust programs into LLVM IR and native executables.
Python coordinates the experiment. This compiler's execution targets remain its interpreter and bytecode VM.

## Map the stages

A front end analyzes source syntax and meaning. A back end produces instructions for an execution target.
An intermediate representation (IR) sits between these stages. A transformation pass changes that representation while preserving its required behavior.

| Purpose | Python Mini-C | Clang and Rust |
|---|---|---|
| Read the source | Lexer and recursive-descent parser | The native compiler's front end |
| Resolve names and types | AST analysis tables | Source-language semantic analysis |
| Select an execution representation | Bytecode with local slots, operands, and `STEP` | LLVM IR with typed values and blocks |
| Optimize | Local constant folding and control-flow simplification | An LLVM optimization pipeline |
| Execute | Interpreter or stack VM | Target-specific machine instructions |

Clang combines compilation stages behind one command. `-S -emit-llvm` produces textual LLVM IR, while `-S` alone produces assembly.
The linker combines object files and libraries into an executable. These stages appear in the [Clang toolchain guide](https://clang.llvm.org/docs/Toolchain.html).
The laboratory uses Clang directly, so it needs no standalone `opt` or `llc` installation.

The compiler is the Python program that translates the source. Its input language remains Mini-C.
The C and Rust sources in the laboratory provide native examples for comparison. They do not change that distinction.

## Read memory and SSA values

Static single assignment (SSA) gives each named value one definition.
That definition can execute repeatedly when control returns to a loop block.
Memory contents can still change. `alloca` reserves local storage, and `load` and `store` read and write that storage.
The [LLVM mutable-variable tutorial](https://llvm.org/docs/tutorial/MyFirstLanguageFrontend/LangImpl07.html#memory-in-llvm) explains why SSA values and mutable memory coexist.

At optimization level 0, the C listing stores `index` and `total` in memory.
The condition loads the index, and the body stores the updated values before its back edge.
This resembles Mini-C's mutable local slots, although the instruction formats differ.

At level 1 on the recorded toolchain, Clang carries these values through `phi` instructions.
A `phi` instruction selects the input associated with the predecessor block that transferred control to its block.
It selects an existing value rather than evaluating both paths. See the [LLVM instruction contract](https://llvm.org/docs/LangRef.html#phi-instruction).

| Moment in the loop | Mini-C bytecode | Optimized LLVM IR |
|---|---|---|
| First entry | Read the initial local values. | Select zero from the entry block. |
| Execute the body | Call `next`, add, and store the new values. | Produce the sum and increment as new named values. |
| Next entry | Read the updated local slots. | Select the previous iteration's sum and increment. |
| Exit | Load the total and return it. | Select the exit value and return it. |

The [control-flow study](control-flow.md) follows the corresponding Mini-C blocks and edges.
An LLVM module also records target information. Its generated instructions and data layout depend on the compiler and target.
The laboratory saves each compiler's version and keeps the complete IR listings for inspection.

## Compare arithmetic contracts

Mini-C reports signed 64-bit overflow, division by zero, missing values, and invalid array indices at source positions.
Its bytecode also records `STEP` instructions to preserve the execution budget through optimization.
The [language contract](language.md#execution) defines those rules.

The laboratory's C and Rust programs share the loop's bounded results.
C uses signed 64-bit storage, but its signed-overflow rules differ from Mini-C's runtime errors.
Rust enables overflow checks, but its failure diagnostics and execution accounting also differ from Mini-C.
The experiment therefore uses only inputs whose arithmetic stays within range.

A Mini-C LLVM backend needs explicit behavior for these runtime errors, source positions, arrays, and execution limits.
Mapping an addition to a native instruction alone does not implement that contract.
This laboratory studies the representations and their observed results without adding such a backend.

## Reproduce and explain the result

With Clang and Rust on `PATH`, run the laboratory from the repository root.

```sh
python3 labs/loop-ir/run.py
```

Read the output directory from the first line. Open `results.json` to inspect the command arguments and comparison results.
Locate `sum_next` in each LLVM listing. Follow the condition, body, back edge, and exit.
Trace limit 4 through its four iterations, then compare the total with the Mini-C bytecode listing.

The five inputs cover a negative limit, an empty loop, one iteration, and two longer loops.
The script requires 45 matching executions across nine paths. Every execution must have the expected output, status 0, and empty standard error.
It also rejects compiler warnings and records a failure when a command exceeds its timeout.

The predecessors supply complementary examples: the [C++ project's C laboratory](../../compiler-mini-c/docs/theory-llvm.md)
and the [Rust loop study](../../compiler-mini-rust/labs/loop-ir/README.md).
The Python experiment combines both native comparisons in one reproducible run.
