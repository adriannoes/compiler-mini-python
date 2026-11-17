# Parsing theory and the Python parser

The [parser](../minic/parser.py) constructs an abstract syntax tree (AST), which represents the program's structure.
This study explains its decisions through smaller grammars. The [laboratory](../labs/parsing/grammar.py) computes grammar sets without changing the compiler.
The complete Mini-C grammar remains in the [language contract](language.md#grammar).

## Symbols and predictions

A terminal is one token kind or spelling. A nonterminal names a grammar rule.
A production expands a nonterminal into grammar symbols. An empty production, written as `epsilon`, consumes no tokens.
Lookahead is the next token examined before consumption.

| Set | Meaning |
|---|---|
| Nullable | Nonterminals that can produce the empty sequence |
| FIRST | Terminals that can start a derivation |
| FOLLOW | Terminals that can follow a nonterminal's derivation |

The end marker `$` also belongs to the start symbol's FOLLOW set.
The lab keeps nullability separate, so neither FIRST nor FOLLOW contains `epsilon`.
This convention follows [Cornell's predictive parsing notes](https://www.cs.cornell.edu/courses/cs4120/2023sp/notes/topdown/).

## Compute the expression sets

The start symbol is `E`. The token `id` stands for an identifier.

```text
E      -> T E_tail
E_tail -> + T E_tail | epsilon
T      -> F T_tail
T_tail -> * F T_tail | epsilon
F      -> id | ( E )
```

With Python 3.9 or later, run the lab from the repository root.

```sh
python3 labs/parsing/grammar.py
```

The first section prints these sets and reports zero conflicts.

| Symbol | Nullable | FIRST | FOLLOW |
|---|---|---|---|
| `E` | No | `{(, id}` | `{$, )}` |
| `E_tail` | Yes | `{+}` | `{$, )}` |
| `T` | No | `{(, id}` | `{$, ), +}` |
| `T_tail` | Yes | `{*}` | `{$, ), +}` |
| `F` | No | `{(, id}` | `{$, ), *, +}` |

The algorithm starts with empty sets and repeatedly adds facts until no set changes. This final state is a fixed point.
Finite sets of symbols and monotonic growth guarantee termination, including for cyclic grammars.
The tests reverse rule order and include a cycle with no terminal derivation.

For a production `A -> prefix B suffix`, FIRST of `suffix` contributes to FOLLOW of `B`.
If `suffix` is nullable, FOLLOW of `A` also contributes to FOLLOW of `B`.
For example, `E -> T E_tail` contributes `+` to FOLLOW of `T`.
Because `E_tail` is nullable, `$` and `)` also propagate from FOLLOW of `E`.

## Select a production with one token

LL(1) uses one lookahead token to select a production. Its two letters describe left-to-right input and a leftmost derivation.
The predictive table has one row per nonterminal and one column per lookahead.
Each production enters the columns in FIRST of its body. A nullable body also enters the columns in FOLLOW of its head.

| Table cell | Choice | Reason |
|---|---|---|
| `E`, `id` | `T E_tail` | An identifier can start a term. |
| `T_tail`, `+` | `epsilon` | The term ends before addition. |
| `E_tail`, `+` | `+ T E_tail` | The expression continues with addition. |
| `T`, `*` | Error | Multiplication cannot start a term. |

An empty cell rejects the input at that decision. Competing productions in one cell report a conflict.
The expression grammar has no conflicts, so it is LL(1).
The lab preserves every distinct competing production rather than selecting the first one.

The library API accepts a dictionary whose keys are nonterminals. Other symbols are terminals, and an empty tuple represents `epsilon`.
The lab reserves `$` for the end of input. Grammar names and token spellings are case sensitive.

## Connect the sets to Mini-C

From the repository root, print the AST for the [expression example](../labs/parsing/expression.mc).

```sh
python3 -m minic --ast labs/parsing/expression.mc
```

The addition has `a` on its left and a multiplication on its right. The multiplication's children are `b` and `c`.
Unresolved names remain valid syntax. The resolver reports those names only when a later command requests semantic analysis.

| Decision | Python implementation | Consequence |
|---|---|---|
| Precedence | `binary(minimum)` parses the right operand at `precedence + 1`. | Multiplication groups inside addition. |
| Left associativity | The loop replaces the accumulated left expression. | `a - b - c` groups as `(a - b) - c`. |
| Right-associative assignment | `expression()` collects targets and constructs assignments in reverse order. | `a = b = c` groups as `a = (b = c)`. |
| Unary chains | `unary()` collects operators and constructs nodes in reverse order. | Long chains do not add Python calls for each operator. |
| Shared name prefix | `primary()` consumes a name before inspecting `(` or `[`. | Names, calls, and indices share one initial token. |

The [C++ parser](../../compiler-mini-c/src/parser.cpp) and [Rust parser](../../compiler-mini-rust/src/parser.rs) recursively parse assignment values and unary operands.
Python uses temporary lists for those chains. This costs temporary storage and avoids dependence on Python's call-depth limit for each operator.
Nested parentheses and statements still use recursive calls. Excessive nesting produces the positioned parse error defined in the language contract.

Directly translating `E -> E + T | T` into recursive descent calls `E` again without consuming input.
The expression grammar with tails removes this left recursion. Python instead uses the precedence loop and its accumulated left child.
Changing a grammar's recursion direction alone does not determine the final AST's associativity.

## Resolve the dangling else

The second lab grammar models conditional statements. The symbol `other` stands for one complete simple statement.

```text
S -> if ( id ) S O | other
O -> else S | epsilon
```

The lab reports `conflict [O, else]: else S | epsilon`.
The token `else` belongs to FIRST of the nonempty alternative and FOLLOW of nullable `O`.
Factoring the shared prefix therefore does not remove this conflict.

For `if(a) if(b) return 1; else return 2;`, two attachments satisfy the reduced grammar.
Mini-C selects the nearest unmatched `if`. Python's inner `statement()` consumes `else` before the outer call considers it.
Braces can end the inner statement first and attach `else` to the outer conditional.
The lab test connects the computed conflict to both AST shapes in the real parser.

## Read a bottom-up trace

A bottom-up parser combines recognized phrases into larger grammar symbols.
A shift consumes a token and pushes it onto a stack. A reduction replaces a production's right side with its head.
Reductions reconstruct a rightmost derivation in reverse order.

This grammar accepts the same expression subset but retains left recursion.

```text
E -> E + T | T
T -> T * F | F
F -> id | ( E )
```

The table shows the stack before each action. Its rightmost symbol is the top.

| Stack | Remaining input | Action |
|---|---|---|
| empty | `id + id * id $` | Shift `id`. |
| `id` | `+ id * id $` | Reduce `F -> id`. |
| `F` | `+ id * id $` | Reduce `T -> F`. |
| `T` | `+ id * id $` | Reduce `E -> T`. |
| `E` | `+ id * id $` | Shift `+`. |
| `E +` | `id * id $` | Shift `id`. |
| `E + id` | `* id $` | Reduce `F -> id`. |
| `E + F` | `* id $` | Reduce `T -> F`. |
| `E + T` | `* id $` | Shift `*`. |
| `E + T *` | `id $` | Shift `id`. |
| `E + T * id` | `$` | Reduce `F -> id`. |
| `E + T * F` | `$` | Reduce `T -> T * F`. |
| `E + T` | `$` | Reduce `E -> E + T`. |
| `E` | `$` | Accept. |

Multiplication completes before the final addition, matching Python's AST for the study example.
A full LR parser stores states and consults action tables. This trace omits state numbers and does not implement another parser.
LR(1) items add lookahead to their grammar progress. LALR merges states with the same LR(0) core and combines their lookaheads.
That merge reduces the state count but can introduce conflicts. [Cornell's LR notes](https://www.cs.cornell.edu/courses/cs4120/2023sp/notes/lr/) explain those constructions.

A shift/reduce conflict offers both actions for one state and lookahead. A reduce/reduce conflict offers two reductions.
Two parse trees for one complete input establish ambiguity. A table conflict alone does not prove ambiguity.
Manual recursive descent keeps Mini-C's syntax decisions and diagnostics in ordinary Python, with no parser-generator dependency.
Its maintenance cost is explicit: changes require updates to the grammar decisions and their tests.

## Test the study

From the repository root, run the lab and parser tests.

```sh
PYTHONPATH=tests python3 -m unittest test_parsing_lab test_parser
```

The tests cover nullable cycles, FIRST/FOLLOW propagation, rule-order independence, conflicting table entries, and Mini-C's nearest-if rule.
The [C++ study](../../compiler-mini-c/docs/theory-parsing.md) provides a longer comparison of parser generators and LR variants.
