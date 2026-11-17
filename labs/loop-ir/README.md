# Follow a loop through bytecode and LLVM IR

The same loop accumulates `next(index)` in Mini-C, C, and Rust. The function `next` returns its argument plus one.
The Python script compares execution results and saves compiler listings for study.
An intermediate representation (IR) describes a program between its source and executable instructions.

## Run the laboratory

The laboratory requires Python 3.9 or later, Clang, and a Rust compiler that supports edition 2021.
Clang and Rust must target the current host so their binaries can execute locally.
The Mini-C compiler and its normal tests require neither native compiler.

From the repository root, run the laboratory.

```sh
python3 labs/loop-ir/run.py
```

The script finds `clang` and `rustc` on `PATH`. Use `--clang` and `--rustc` to select other executable paths.
On macOS, the script uses `SDKROOT` if the environment supplies it. Otherwise, it obtains the SDK path with `xcrun`.
This makes the SDK selection explicit for both native compilers. The report records the selected SDK path.

The first output line names a new directory under `build/loop-ir/`. Git ignores this directory.
Each invocation retains its own artifacts, including a report if a command fails.
A missing compiler stops the laboratory with an error. It does not silently omit a comparison.

## Compare the execution paths

| Limit | Expected result | Loop behavior |
|---:|---:|---|
| -2 | 0 | Skip the body for a negative limit. |
| 0 | 0 | Skip the body at zero. |
| 1 | 1 | Execute one iteration. |
| 4 | 10 | Add 1, 2, 3, and 4. |
| 8 | 36 | Add the integers 1 through 8. |

Each case runs through nine paths: three Mini-C modes, two C builds, two builds from C-generated IR, and two Rust builds.
The three Mini-C modes are `--run`, `--run-vm`, and `--run-vm-opt`.
Each native pair uses optimization levels 0 and 1. Each execution must print the expected decimal result followed by a newline.
It must also exit with status 0 and produce empty standard error. All 45 executions must pass.

The script also rejects failed builds and compiler warnings. Each command has a 30-second timeout.
The [driver](run.py) stores command arguments, exit status, both output streams, and successful case results in `results.json`.
The `status` field becomes `passed` only after all comparisons succeed.

## Inspect the artifacts

| Artifact | Purpose |
|---|---|
| `python-version.txt`, `clang-version.txt`, `rustc-version.txt` | Identify the tools that produced the results. |
| `sum.bytecode`, `sum.opt.bytecode` | Follow the Mini-C function `sum_next` before and after optimization. |
| `sum.c.O0.ll`, `sum.c.O1.ll` | Compare Clang's memory accesses and optimized loop values. |
| `sum.rust.O0.ll`, `sum.rust.O1.ll` | Find the function definition whose name contains `sum_next`. |
| `sum.c.O0`, `sum.c.O1` | Execute the builds from C source. |
| `sum.ir.O0`, `sum.ir.O1` | Execute the builds from Clang-generated IR. |
| `sum.rust.O0`, `sum.rust.O1` | Execute the Rust builds. |
| `limit-*.mc` | Read the generated Mini-C entry function for each input. |
| `results.json` | Inspect the commands and all 45 comparison results. |

Windows executable names also have an `.exe` suffix.
The script compiles each C listing with the same Clang that emitted it. Rust emits its own IR and native executable together.
The laboratory does not pass Rust IR to Clang because the two compilers can use different LLVM versions.

## Trace the values

The [Mini-C source](sum.mc) keeps `limit`, `index`, and `total` in local slots 0, 1, and 2.
At the start of the second iteration for limit 4, those slots contain 4, 1, and 1.
The call `next(1)` produces 2. The body stores total 3 and index 2, then jumps back to the condition.

The [C function](sum.c) calls `next` from the separate [driver](driver.c).
Separate compilation without link-time optimization keeps that call in the loop.
The [Rust example](sum.rs) uses `#[inline(never)]` to keep both study functions visible.

Static single assignment (SSA) gives each named value one definition.
A `phi` instruction selects a value from the predecessor block. See the [LLVM language reference](https://llvm.org/docs/LangRef.html#phi-instruction).
In the observed Clang 17 output, the optimized body starts with these instructions:

```llvm
%total.07 = phi i64 [ %add, %while.body ], [ 0, %entry ]
%index.06 = phi i64 [ %add1, %while.body ], [ 0, %entry ]
```

On the first entry, both values are zero. On the next entry, they use the previous sum and increment.
For the second iteration with limit 4, the selected values are total 1 and index 1.
The Rust output uses the same selection principle, with separate blocks for its arithmetic overflow checks.
Names, block layouts, and optimization choices can differ across compiler versions and targets. The report records the versions for that reason.

## Keep the comparison bounded

All five inputs keep every addition within the signed 64-bit range. The native drivers accept limits only from -2 through 8.
C uses `int64_t`. Rust uses `i64`, and the build enables `overflow-checks=yes` at both optimization levels.
C signed overflow does not provide Mini-C's checked arithmetic behavior.
Rust's overflow failure also does not reproduce Mini-C's source positions or error text.

The experiment establishes the listed results for these bounded inputs. It does not establish equivalence for arbitrary programs or failures.
Only Mini-C enforces its source-step and call-depth limits. The native paths have the script's external timeout.
The [LLVM study](../../docs/theory-llvm.md) relates these observations to the compiler architecture.
