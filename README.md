# Mini-C in Python

This project uses Python to read programs written in Mini-C.
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
The parser accepts unknown names and mixed types. Name resolution and type analysis belong to a later phase.
Array syntax also belongs to a later phase. Deeply nested syntax can reach the Python recursion limit.

The command scans the whole file before it parses any tokens. A lexical error therefore takes priority over an earlier syntax error.
On a syntax error, the command writes the first diagnostic to standard error, leaves standard output empty, and exits with status 1.

## Tests

From the repository root, run the tests with the Python standard library.

```sh
python3 -m unittest discover -s tests
```

The command tests compare the exit status and the bytes on both output streams.
The [expected token listings and syntax trees](tests/fixtures) come from the C++ compiler.
