# Mini-C in Python

This project uses Python to analyze and execute programs written in Mini-C.
A lexer separates source text into units called tokens.
It recognizes 35 token kinds, including keywords, identifiers, decimal integers, operators, delimiters, and the end of input.

From the repository root, list the tokens in the example with Python 3.9 or later.

```sh
python3 -m minic --tokens examples/hello.mc
```

Each row shows the starting line, byte column, token kind, and original text.
The comment and blank line put the first token, `INT "int"`, at line 3, column 1.
The final newline puts `EOF`, the end of input, at line 6, column 1.
The lexer keeps integer digits as text, so `007` keeps both leading zeroes.

A lexical error stops the scan. The command prints the path and position on standard error and exits with status 1.
Standard output stays empty on failure.

## Token boundaries

Run these commands from the repository root to see all 35 token kinds.

```sh
python3 -m minic --tokens examples/lexer.mc
python3 -m minic --tokens examples/arrays.mc
```

In the first example, `-1` produces a `MINUS` token and an `INTEGER` token.
In the second, `values[4]` produces four tokens, including a token for each bracket.

The scanner reads a complete name before it looks up a keyword.
For example, `while` is a keyword and `while2` is an identifier.
For operators, the scanner tries the longest supported spelling first.
The input `===` gives `==` followed by `=`.
In `=/**/=`, the comment separates the two `=` tokens.
A single `&` or `|` reports an error at that byte.

## Read a syntax tree

The parser groups the tokens of a scalar Mini-C program into an abstract syntax tree (AST).
From the repository root, print the tree for the example.

```sh
python3 -m minic --ast examples/hello.mc
```

```text
Program
  Function "main" @3:5
    Type INT @3:1
    Block @3:12
      Return @4:3
        Integer "0" @4:10
```

Indentation shows which node contains each child. The position on a function points to its name.
The position on a binary expression points to its operator.
The parser keeps the original digits in integer nodes, including leading zeroes.

Compare three decisions in the example trees.

| Input | What to look for with `--ast` |
|-------|------------------------------|
| [Expressions](examples/expressions.mc) | In `left = right = value`, the outer assignment contains a second assignment as its value. |
| [Calls](examples/calls.mc) | The second argument in `add(1, add(2, 3))` is a call with two arguments of its own. |
| [Control flow](examples/control_flow.mc) | The `Else` appears under the inner `If`. If a block encloses the inner `if` and ends before `else`, the outer `if` owns the `else`. |

The [parser](minic/parser.py) uses one method for each grammar rule and a table for binary operator precedence.
In `a + b * c`, it parses the product as the right operand of the sum.
In `a - b - c`, the second minus has the same precedence as the first.
The parser builds the left subtraction first. The C++ parser uses a method per precedence level.
Rust looks up precedence in a function. Python reads it from a table.

A block accepts declarations and statements. A type keyword starts a declaration.
After `if (condition)`, the parser expects one statement. Braces allow declarations inside that statement.
The parser accepts unknown names and mixed types. The next two commands analyze names and types.
Array syntax also belongs to a later phase. Deeply nested syntax can reach the Python recursion limit.

The command scans the whole file before it parses any tokens. A lexical error therefore takes priority over an earlier syntax error.
On a syntax error, the command writes the first diagnostic to standard error, leaves standard output empty, and exits with status 1.

## Resolve names and check types

A scope is the part of a program where a declaration is visible.
From the repository root, print the declarations and name uses in the example.

```sh
python3 -m minic --resolve examples/scopes.mc
```

Compare these two reads in the output.

```text
  Read "value" scope=#2 @7:13 -> Symbol #4 @6:9
  Read "value" scope=#1 @9:10 -> Symbol #2 @3:7
```

Inside the block, `value` selects the declaration on line 6. After the block, the same name selects the declaration on line 3.
The [resolver](minic/resolver.py) registers all functions before it visits their bodies. This lets `main` call `later` before its definition.
A local variable becomes visible before its initializer. In `int x = x;`, the read refers to the new variable.
Static analysis accepts the read. Execution determines whether the variable has a value.

The type checker uses each binding to find the declared type. C++ indexes bindings by node address. Rust assigns a node identifier.
Python uses the AST object as a dictionary key. Nodes from separate trees can share a source position and still refer to different declarations.

From the repository root, try a valid program and an invalid initializer.

```sh
python3 -m minic --check examples/types.mc
python3 -m minic --check examples/type_error.mc
```

The first command exits with status 0 and prints nothing. The second exits with status 1 and writes this diagnostic to standard error.

```text
examples/type_error.mc:3:16: error: Expected type bool. Received int.
```

Mini-C keeps `int` and `bool` distinct. The [type checker](minic/type_checker.py) represents each Mini-C type with a separate enum member.
The checker resolves every name and checks all function signatures before it checks any body.
It checks unreachable statements, including statements after a return.
A non-void function must guarantee a return. An `if` guarantees a return when both branches do. A loop alone gives no such guarantee.

## Execute a scalar program

From the repository root, run the factorial example.

```sh
python3 -m minic --run examples/factorial.mc
```

The [interpreter](minic/interpreter.py) checks every function before it calls `main` without arguments.
The command prints `720` and exits with status 0. A boolean result prints as `true` or `false`.
A `void` result leaves standard output empty.

In `n * factorial(n - 1)`, the multiplication waits for the inner call.
Each call has a frame with its own parameters and local values.
The Python interpreter keeps a stack of unfinished AST visits. A visit resumes when its child supplies a result.
C++ and Rust use recursive host calls for this walk. The Python stack lets Mini-C enforce its own call depth during execution.

The interpreter uses the resolved declaration to select a local slot. Each execution of a declaration clears that slot before the initializer runs.
In [runtime_error.mc](examples/runtime_error.mc), the initializer reads the variable it just declared.
The command exits with status 1 and writes this diagnostic to standard error.

```text
examples/runtime_error.mc:3:15: error: The variable "value" has no value.
```

The [arithmetic functions](minic/runtime.py) keep integers within the signed 64-bit range.
Mini-C division truncates toward zero, so `-7 / 2` gives `-3` and `-7 % 2` gives `-1`.
Execution converts a literal only when it reaches that literal.
In [short_circuit.mc](examples/short_circuit.mc), `true || (1 / 0 == 0)` skips the division and its possible error.

The defaults allow 1,000,000 source steps and 128 active calls, including the entry call.
Each executed statement or expression costs one step. Skipped operands cost no steps.
The interpreter evaluates arguments left to right before it tests the call depth.
The library accepts another entry name and custom limits through `interpret(program, entry, limits)` and `ExecutionLimits(max_steps, max_call_depth)`.

## Read the bytecode

Bytecode is a sequence of instructions for a virtual machine. From the repository root, compile the example and print its instructions.

```sh
python3 -m minic --bytecode examples/hello.mc
```

```text
bytecode
function 0 "main" int parameters=0 @3:5
  constant 0 int "0"
  0 STEP @3:12
  1 STEP @4:3
  2 STEP @4:10
  3 LOAD_CONSTANT 0 @4:10
  4 RETURN @4:3
  5 UNREACHABLE @3:12
end
```

The three `STEP` instructions mark the block, the return statement, and the literal. Each carries its source position.
`LOAD_CONSTANT 0` pushes the first constant onto the operand stack. `RETURN` takes that value off the stack and returns it to the caller.
`UNREACHABLE` marks the end of a non-void function. The type checker requires every path to return before that point.

The compiler checks the whole program before it emits instructions. Compilation accepts functions without a `main` and preserves the digits of integer literals.
A program such as [runtime_error.mc](examples/runtime_error.mc) produces a listing. The read of an uninitialized variable fails only during execution.

From the repository root, inspect a conditional jump.

```sh
python3 -m minic --bytecode examples/short_circuit.mc
```

At offset 23, `JUMP_IF_TRUE 35` consumes the left operand of `||`. When that operand is true, the jump skips `DIVIDE` at offset 30.
At offset 35, `LOAD_CONSTANT 8` supplies the result, `true`. Jump targets count instructions from zero within each function.

C++ looks up a symbol by declaration address. C++ and Rust use the symbol identifier to select a numbered slot.
The [Python compiler](minic/bytecode_compiler.py) uses the declaration object itself as the slot table key.
Two variables with the same name in different scopes get separate slots. Parameters take the first slots in declaration order.
Each call identifies its function by source order, so the compiler can emit a call before it compiles the callee.

## Execute the bytecode

From the repository root, run the factorial example on both engines.

```sh
python3 -m minic --run examples/factorial.mc
python3 -m minic --run-vm examples/factorial.mc
```

Both commands print `720`. The interpreter visits syntax tree nodes. The [virtual machine](minic/vm.py) reads one bytecode instruction at a time.
The program counter holds the offset of the next instruction in the current function.

In `n * factorial(n - 1)`, the caller pushes `n` onto its operand stack and computes the argument above it.
`CALL` moves the argument into the new frame's first local slot. The caller keeps `n` on its stack.
`RETURN` gives the caller the factorial of `n - 1`. The caller resumes at `MULTIPLY`.
A void return resumes the caller with its stack unchanged.

The C++ and Rust VMs keep operands in one shared stack and record its base offset in each frame.
Python allocates one operand list per frame. This costs one list per active call and keeps each caller's pending operands in its own frame.
All three VMs use an explicit stack of frames for recursion.

Only `STEP` consumes a source step. Calls share the step budget, and skipped instructions consume no steps.
Both Python engines use the same checked arithmetic and report errors at the source position of the operation.
The library can execute the same bytecode several times with different entry functions or limits through `execute_bytecode(program, entry, limits)`.
Each execution starts with fresh frames and a fresh step budget.

## Optimize the bytecode

From the repository root, compare the two listings for [optimization.mc](examples/optimization.mc). Then execute the optimized program.

```sh
python3 -m minic --bytecode examples/optimization.mc
python3 -m minic --bytecode-opt examples/optimization.mc
python3 -m minic --run-vm-opt examples/optimization.mc
```

The first listing has 69 instructions. The optimized listing has 36, and the VM prints `24` with either version.

| Source expression | Change in the optimized listing |
|---|---|
| `(2 + 3) * 4` | The optimizer computes `20` at compile time. Instruction 8 loads constant 13, which holds that result. |
| `if (1 < 2)` | The condition always selects the first branch. The optimizer removes the other branch, including its division by zero. |
| `(6 * 7);` | The program discards the product. The optimizer removes the calculation and keeps the four source steps at offsets 28 through 31. |

During constant folding, the [optimizer](minic/bytecode_optimizer.py) evaluates an operation when it knows all the operands.
It uses the same signed 64-bit arithmetic as the VM.
If an operation fails during folding, the optimizer retains it. For example, a reachable `1 / 0;` still fails at the division, even if the program discards its result.
A local read can also fail. In `x * 0`, execution still reads `x` and reports an error if it has no value.

The optimizer tracks known operands within a basic block, a sequence of instructions with one entry and no internal branches.
Calls, local reads, and stores clear this information. After deleting instructions, the optimizer updates jump targets to their new offsets.
It repeats the rewrites until the listing is stable. Each reachable `STEP` keeps its position so both VM modes count the same source steps.

The C++ optimizer copies the program, and Rust clones it. In Python, `optimize_bytecode(program)` copies each function's mutable lists and shares immutable records.
This lets you inspect the original and optimized listings side by side.

## Tests

From the repository root, run the tests with the Python standard library.

```sh
python3 -m unittest discover -s tests
```

The command tests compare the exit status and the bytes on both output streams.
The [expected token listings, syntax trees, name bindings, and bytecode listings](tests/fixtures) come from the C++ compiler.

With both reference executables available, compare the three implementations from the repository root.

```sh
python3 scripts/compare_cli.py run examples/factorial.mc examples/runtime_error.mc
python3 scripts/compare_cli.py bytecode examples/short_circuit.mc examples/type_error.mc
python3 scripts/compare_cli.py run-vm examples/factorial.mc examples/runtime_error.mc
python3 scripts/compare_cli.py bytecode-opt examples/optimization.mc
python3 scripts/compare_cli.py run-vm-opt examples/optimization.mc examples/runtime_error.mc
```

The script runs each command on the same input and compares the exit status, standard output, and standard error.
It looks for `../compiler-mini-c/build/minic` and `../compiler-mini-rust/target/debug/compiler-mini-rust`.
If the executables are elsewhere, pass their paths with `--cpp` and `--rust`.
