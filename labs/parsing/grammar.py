"""Compute grammar sets and expose competing predictive productions."""

from dataclasses import dataclass


Production = tuple[str, ...]
Grammar = dict[str, tuple[Production, ...]]

EXPRESSION: Grammar = {
    "E": (("T", "E_tail"),),
    "E_tail": (("+", "T", "E_tail"), ()),
    "T": (("F", "T_tail"),),
    "T_tail": (("*", "F", "T_tail"), ()),
    "F": (("id",), ("(", "E", ")")),
}
DANGLING_ELSE: Grammar = {
    "S": (("if", "(", "id", ")", "S", "O"), ("other",)),
    "O": (("else", "S"), ()),
}


@dataclass(frozen=True)
class Analysis:
    nullable: frozenset[str]
    first: dict[str, frozenset[str]]
    follow: dict[str, frozenset[str]]
    table: dict[tuple[str, str], tuple[Production, ...]]

    @property
    def conflicts(self) -> dict[tuple[str, str], tuple[Production, ...]]:
        return {cell: choices for cell, choices in self.table.items() if len(choices) > 1}


def _first_sequence(sequence: Production, first: dict[str, set[str]], nullable: set[str]) -> set[str]:
    result: set[str] = set()
    for symbol in sequence:
        result.update(first[symbol] if symbol in first else {symbol})
        if symbol not in nullable:
            break
    return result


def analyze(grammar: Grammar, start: str) -> Analysis:
    """Treat dictionary keys as nonterminals and empty tuples as epsilon."""
    if start not in grammar:
        raise ValueError("The start symbol must have a production.")
    if "$" in grammar or any("$" in body for bodies in grammar.values() for body in bodies):
        raise ValueError("The dollar sign is reserved for the end of input.")

    nullable: set[str] = set()
    while True:
        expanded = nullable | {
            head for head, bodies in grammar.items()
            if any(all(symbol in nullable for symbol in body) for body in bodies)
        }
        if expanded == nullable:
            break
        nullable = expanded

    first: dict[str, set[str]] = {head: set() for head in grammar}
    changed = True
    while changed:
        changed = False
        for head, bodies in grammar.items():
            before = len(first[head])
            for body in bodies:
                first[head].update(_first_sequence(body, first, nullable))
            changed |= len(first[head]) != before

    follow: dict[str, set[str]] = {head: set() for head in grammar}
    follow[start].add("$")
    changed = True
    while changed:
        changed = False
        for head, bodies in grammar.items():
            for body in bodies:
                trailer = follow[head].copy()
                for symbol in reversed(body):
                    if symbol not in grammar:
                        trailer = {symbol}
                        continue
                    before = len(follow[symbol])
                    follow[symbol].update(trailer)
                    changed |= len(follow[symbol]) != before
                    trailer = trailer | first[symbol] if symbol in nullable else first[symbol].copy()

    table: dict[tuple[str, str], tuple[Production, ...]] = {}
    for head, bodies in grammar.items():
        for body in bodies:
            lookaheads = _first_sequence(body, first, nullable)
            if all(symbol in nullable for symbol in body):
                lookaheads.update(follow[head])
            for lookahead in sorted(lookaheads):
                cell = (head, lookahead)
                choices = table.get(cell, ())
                if body not in choices:
                    table[cell] = (*choices, body)
    return Analysis(frozenset(nullable),
                    {head: frozenset(values) for head, values in first.items()},
                    {head: frozenset(values) for head, values in follow.items()}, table)


def format_analysis(name: str, result: Analysis) -> str:
    def symbols(values):
        return "{" + ", ".join(sorted(values)) + "}"

    lines = [name, "nullable: " + symbols(result.nullable)]
    for head in result.first:
        lines.append(f"{head}: FIRST={symbols(result.first[head])} FOLLOW={symbols(result.follow[head])}")
    for (head, lookahead), bodies in sorted(result.conflicts.items()):
        choices = " | ".join(" ".join(body) if body else "epsilon" for body in bodies)
        lines.append(f"conflict [{head}, {lookahead}]: {choices}")
    lines.append(f"conflicts: {len(result.conflicts)}")
    return "\n".join(lines)


def main() -> None:
    for name, grammar, start in (("Expressions", EXPRESSION, "E"), ("Dangling else", DANGLING_ELSE, "S")):
        print(format_analysis(name, analyze(grammar, start)))


if __name__ == "__main__":
    main()
