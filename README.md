# Mini-C in Python

This project uses Python to read programs written in Mini-C.
Phase 1 provides a lexer. A lexer separates source text into units called tokens.
It recognizes `int`, `return`, identifiers, decimal integers, parentheses, braces, and semicolons.

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

From the repository root, run the tests with the Python standard library.

```sh
python3 -m unittest discover -s tests
```

The command tests compare the exit status and the bytes on both output streams.
[Expected token listing](tests/fixtures/hello.tokens).
