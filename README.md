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

## Tests

From the repository root, run the tests with the Python standard library.

```sh
python3 -m unittest discover -s tests
```

The command tests compare the exit status and the bytes on both output streams.
The [expected token listings](tests/fixtures) come from the C++ compiler.
