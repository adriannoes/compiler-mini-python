# Mini-C language

Mini-C programs define functions with scalar parameters and scalar or void results.
Function bodies contain local scalars, fixed arrays, expressions, branches, loops, and returns.
Python 3.9 or later runs the compiler from the repository root.

## Commands and diagnostics

Each command takes one source file. Replace `MODE` in `python3 -m minic MODE file.mc` with a mode below.

| Mode | Successful output |
|---|---|
| `--tokens` | Token kind, original text, line, and byte column |
| `--ast` | Indented syntax tree |
| `--resolve` | Scopes, declarations, and name bindings |
| `--check` | Empty output after successful type analysis |
| `--bytecode` | Original bytecode listing |
| `--bytecode-opt` | Optimized bytecode listing |
| `--run` | Result from the AST interpreter |
| `--run-vm` | Result from the VM |
| `--run-vm-opt` | Result from the VM after optimization |

Use `python3 -m minic --help` to list the modes. The help alias is `-h`.
Execution selects `main`, which must have no parameters. An integer prints as decimal text, and a boolean prints as `true` or `false`.
A void result produces empty output. Success exits with status 0, including when `main` returns a nonzero integer.

Compilation and analysis accept files without `main`. An empty file has no functions and succeeds through bytecode output.
Execution of that file fails at line 1, column 1 because the entry function is missing.

A failure prints one diagnostic on standard error and exits with status 1. Standard output is empty.
Positioned errors use `path:line:column: error: message`. File errors use `path: error: message`.
The command completes lexing before parsing and completes name resolution before type analysis.
It checks all function signatures before their bodies and checks every body before execution.
Static errors therefore take priority over runtime errors in earlier functions.

## Lexical rules

Identifiers use ASCII letters or underscore first, then ASCII letters, digits, or underscores. Names are case sensitive.
Integer tokens contain one or more decimal digits. A minus sign is a separate token, and leading zeroes keep their original spelling.

| Category | Spellings |
|---|---|
| Keywords | `int bool void if else while return true false` |
| Operators | `= + - * / % == != < <= > >= ! && ||` |
| Delimiters | `( ) { } [ ] ; ,` |

The lexer also emits identifier, integer, and EOF kinds, for 35 token kinds in total.
It prefers the longest supported operator spelling. For example, `===` produces `==` followed by `=`.
Space, tab, CR, LF, vertical tab, and form feed separate tokens.
Line comments start with `//`. Block comments start with `/*` and end at the next `*/`.

Lines and columns start at one. A tab consumes one byte column. CR, LF, and CRLF each advance one line.
EOF points immediately after the final byte. Comments update positions while they consume bytes.
The lexer reports an unterminated block comment at its opening delimiter.

## Grammar

The notation uses braces for repetition and brackets for an optional part. Quoted text denotes a Mini-C token.
`IDENTIFIER` and `INTEGER` denote token kinds.

```ebnf
program     = { function } ;
function    = type, IDENTIFIER, "(", [ parameters ], ")", block ;
type        = "int" | "bool" | "void" ;
parameters  = parameter, { ",", parameter } ;
parameter   = type, IDENTIFIER ;
block       = "{", { declaration | statement }, "}" ;
declaration = type, IDENTIFIER, ( "[", INTEGER, "]" | [ "=", expression ] ), ";" ;
statement   = block | ";"
            | "return", [ expression ], ";"
            | "if", "(", expression, ")", statement, [ "else", statement ]
            | "while", "(", expression, ")", statement
            | expression, ";" ;
expression  = logical_or, [ "=", expression ] ;
logical_or  = logical_and, { "||", logical_and } ;
logical_and = equality, { "&&", equality } ;
equality    = comparison, { ( "==" | "!=" ), comparison } ;
comparison  = sum, { ( "<" | "<=" | ">" | ">=" ), sum } ;
sum         = product, { ( "+" | "-" ), product } ;
product     = unary, { ( "*" | "/" | "%" ), unary } ;
unary       = ( "-" | "!" ), unary | primary ;
primary     = INTEGER | "true" | "false"
            | IDENTIFIER, [ "(", [ arguments ], ")" | "[", expression, "]" ]
            | "(", expression, ")" ;
arguments   = expression, { ",", expression } ;
```

The parser requires an assignment target to be a name or indexed name. Parentheses can surround either target.
Assignment groups right to left. All binary operators above it group left to right within their precedence level.
The grammar lists precedence from assignment at the lowest level to unary and primary expressions at the highest level.
An `else` attaches to the nearest unmatched `if`.

The parser accepts declarations directly inside blocks. A declaration inside an `if` or `while` body requires braces.
The grammar permits one index after a bare name. Parameters and function results have scalar types.
An array declaration has a literal length and initializes elements through later assignments.

## Names and types

All function names are visible before the resolver visits any body. This permits forward calls and mutual recursion.
Parameters share the scope of the function's outer block. A nested block adds a scope.
A local becomes visible before its initializer. In `int x = x;`, the initializer refers to the new variable.
Two declarations in one scope cause an error. A declaration in a nested scope can shadow an outer name.

Mini-C has distinct `int`, `bool`, and `void` types. Variables, elements, and parameters use `int` or `bool`.
Conditions require `bool`. Arguments, assignments, initializers, and returned values must match their declared types.

| Operators | Operand types | Result type |
|---|---|---|
| Unary `-` | `int` | `int` |
| Unary `!` | `bool` | `bool` |
| `+ - * / %` | Two integers | `int` |
| `< <= > >=` | Two integers | `bool` |
| `== !=` | Two integers or two booleans | `bool` |
| `&& ||` | Two booleans | `bool` |
| `=` | Target and value have the same scalar type | Assigned type |

A non-void function must guarantee a return. A return statement guarantees one, and an `if` guarantees one when both branches do.
A block guarantees a return when one of its statements does. A loop alone provides no guarantee, even with a constant true condition.
Type analysis checks statements after returns too.

Arrays contain from 1 through 1024 elements. The type checker checks the length at its literal position.
An indexed use requires an array declaration and an integer index. Its type is the scalar element type.
An entire array cannot supply a scalar value, parameter, or function result.
Static analysis allows uninitialized reads and out-of-bounds integer indices. Execution determines whether the program reaches those reads or indices.

## Execution

Integers use the signed 64-bit range, from `-9223372036854775808` through `9223372036854775807`.
Literal conversion occurs when execution reaches the literal. Unary minus on a literal also accepts the signed minimum, including parentheses around the literal.
Overflow and a zero divisor produce runtime errors.

Division truncates toward zero. Thus `-7 / 2` is `-3`, and `-7 % 2` is `-1`.
The remainder satisfies `a = (a / b) * b + (a % b)`.
Both division and remainder require a representable quotient, so the signed minimum divided or reduced modulo `-1` fails.

Operands and call arguments evaluate left to right. Logical `&&` skips the right operand when the left is false.
Logical `||` skips it when the left is true. A return exits the current function immediately.

Every executed declaration clears its storage before evaluating its initializer. Recursive calls keep separate values, and parameters receive copies of scalar arguments.
Array elements start without values. Reads report the selected missing element, even when another element has a value.
An indexed assignment checks and saves its index before evaluating the right operand. It writes through that saved index and returns the assigned value.
Bounds and missing-element errors point to the array name at the access.

`ExecutionLimits` defaults to 1,000,000 source steps and 128 active calls, including the entry call.
Both limits must be positive Python integers. A boolean or invalid limit raises `ValueError` when constructing the limits.
A statement or expression costs one source step. An indexed assignment also charges the target access and its index expression.
Storage allocation adds no per-element steps. Arguments finish before a call-depth check.
All calls share one step budget. Exhaustion reports the next source step that execution attempts.

From the repository root, use the library to select an entry and limits.

```python
from pathlib import Path
from minic.bytecode_compiler import compile_bytecode
from minic.lexer import lex
from minic.parser import parse
from minic.runtime import ExecutionLimits
from minic.vm import execute_bytecode

tree = parse(lex(Path("examples/factorial.mc").read_bytes()))
code = compile_bytecode(tree)
print(execute_bytecode(code, "main", ExecutionLimits(1000, 16)))
```

This example prints `720`. The interpreter accepts the same entry and limits through `interpret(tree, entry, limits)`.
The parser reports excessive syntax nesting as a positioned parse error. Execution limits apply after parsing and static analysis.

## Bytecode

A constant pool stores literals used by instructions. A local slot stores one declaration's runtime data.
A call frame holds one active function's execution state.

Each function owns its instruction sequence, constant pool, and local metadata. Parameters take the first local slots.
Jumps use absolute instruction offsets within a function. Calls use function indices in source order.
The table describes operand consumption and production, with the top at the right.

| Instruction | Effect |
|---|---|
| `STEP` | Charge one source step at the instruction's position. |
| `LOAD_CONSTANT n` | Convert constant `n` and push its value. |
| `LOAD_LOCAL n` | Push the initialized scalar in slot `n`. |
| `STORE_LOCAL n` | Copy the top value to scalar slot `n` and keep the value on the stack. |
| `RESET_LOCAL n` | Clear the scalar or allocate empty array storage for slot `n`. |
| `CHECK_INDEX n` | Check the top index against array slot `n` and keep it. |
| `LOAD_ELEMENT n` | Consume an index and push the initialized element from array slot `n`. |
| `STORE_ELEMENT n` | Consume an index and value, write array slot `n`, and push the value. |
| `POP` | Discard the top value. |
| `NEGATE`, `NOT` | Consume one operand and push its arithmetic or logical negation. |
| `ADD`, `SUBTRACT`, `MULTIPLY`, `DIVIDE`, `REMAINDER` | Consume two integers and push the checked arithmetic result. |
| `EQUAL`, `NOT_EQUAL`, `LESS`, `LESS_EQUAL`, `GREATER`, `GREATER_EQUAL` | Consume two operands and push the comparison result. |
| `JUMP n` | Continue at instruction `n`. |
| `JUMP_IF_FALSE n`, `JUMP_IF_TRUE n` | Consume a boolean and jump when it matches the selected condition. |
| `CALL n` | Consume the arguments of function `n` and enter its frame. |
| `RETURN` | Consume the result and give it to the caller. |
| `RETURN_VOID` | Resume the caller without an operand result. |
| `UNREACHABLE` | Report invalid bytecode if execution reaches this instruction. |

For a binary operation, the VM pops the right operand before the left operand.
A value return pushes its result onto the caller's stack. Returning from the entry finishes execution.
Compiler-produced cycles contain source steps. The VM guards executed operands, indices, and stack access with `InvalidBytecode` errors.

The VM and optimizer first apply [static bytecode verification](stack-analysis.md).
It checks instruction shapes, indices, function signatures, and operand types across structural paths.
Each reachable cycle within a function must contain a `STEP`. Paths that meet must supply identical operand-type sequences.
Failures name the function and instruction. Array bounds, missing values, literal range, and arithmetic errors remain runtime checks.

Optimization folds successful constant operations, simplifies known branches, and removes unreachable instructions.
It keeps reachable source steps and operations that can fail or change state. Failed arithmetic remains available for execution.
Original constant text remains in the pool, and computed integers use canonical decimal digits with a separate sign.
All named functions remain available as entries.

The [implementation map](architecture.md) identifies the modules for these rules. The [roadmap](roadmap.md) supplies examples and reference files for each stage.
