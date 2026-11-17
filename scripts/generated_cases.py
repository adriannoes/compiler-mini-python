"""Generate bounded Mini-C programs with independent expected outcomes."""

from dataclasses import dataclass
from fractions import Fraction
import random
from typing import Optional, Union


DEFAULT_SEED = 20261117
DEFAULT_ROUNDS = 8


@dataclass(frozen=True)
class Diagnostic:
    line: int
    column: int
    message: str


@dataclass(frozen=True)
class Case:
    name: str
    category: str
    source: str
    value: Union[int, bool, None] = None
    error: Optional[Diagnostic] = None


def _error(name: str, category: str, marked_source: str, message: str) -> Case:
    before, after = marked_source.split("^")
    line = before.count("\n") + 1
    column = len(before.rsplit("\n", 1)[-1]) + 1
    return Case(name, category, before + after, error=Diagnostic(line, column, message))


def _fixed_cases() -> list[Case]:
    maximum = 9223372036854775807
    minimum = -9223372036854775808
    cases = [
        Case("signed-minimum", "boundary", f"int main(){{return {minimum};}}\n", minimum),
        Case("signed-maximum", "boundary", f"int main(){{return {maximum};}}\n", maximum),
        Case("minimum-divided-by-two", "boundary", f"int main(){{return {minimum}/2;}}\n", minimum // 2),
        Case("minimum-remainder-two", "boundary", f"int main(){{return {minimum}%2;}}\n", 0),
        Case("maximum-array", "boundary",
             "int main(){int a[1024];a[0]=3;a[1023]=7;return a[0]+a[1023];}\n", 10),
        Case("long-leading-zeroes", "boundary", "int main(){return " + "0" * 5000 + "7;}\n", 7),
        Case("short-circuit-overflow", "short_circuit",
             f"bool main(){{return true || {maximum}+1==0;}}\n", True),
        Case("short-circuit-literal", "short_circuit",
             "bool main(){return false && 9223372036854775808==0;}\n", False),
        Case("short-circuit-uninitialized", "short_circuit",
             "bool main(){bool a[1];return true || a[0];}\n", True),
    ]
    runtime = [
        ("zero-divisor", "int main(){\n  return 1 ^/ 0;\n}\n", "The divisor is zero."),
        ("zero-remainder", "int main(){\n  return 1 ^% 0;\n}\n", "The divisor is zero."),
        ("addition-overflow", f"int main(){{\n  return {maximum} ^+ 1;\n}}\n",
         "Integer arithmetic exceeds the signed 64-bit range."),
        ("negation-overflow", f"int main(){{\n  return ^-({minimum});\n}}\n",
         "Integer arithmetic exceeds the signed 64-bit range."),
        ("division-overflow", f"int main(){{\n  return {minimum} ^/ -1;\n}}\n",
         "Integer arithmetic exceeds the signed 64-bit range."),
        ("remainder-overflow", f"int main(){{\n  return {minimum} ^% -1;\n}}\n",
         "Integer arithmetic exceeds the signed 64-bit range."),
        ("literal-overflow", "int main(){\n  return ^9223372036854775808;\n}\n",
         "The integer literal is outside the signed 64-bit range."),
        ("local-without-value", 'int main(){int x;\n  return ^x;\n}\n',
         'The variable "x" has no value.'),
        ("element-without-value", 'int main(){int a[2];a[0]=1;\n  return ^a[1];\n}\n',
         'The array element "a[1]" has no value.'),
        ("negative-index-before-rhs", 'int main(){int a[1];\n  ^a[-1]=1/0;return 0;\n}\n',
         'The array index -1 is outside "a" with length 1.'),
        ("upper-index-before-rhs", 'int main(){int a[1];\n  ^a[1]=1/0;return 0;\n}\n',
         'The array index 1 is outside "a" with length 1.'),
        ("loop-clears-array", 'int main(){int i=0;while(i<2){int a[1];if(i==0)a[0]=3;i=i+1;\n  ^a[0];}return 0;}\n',
         'The array element "a[0]" has no value.'),
    ]
    static = [
        ("bool-is-not-int", "bool main(){\n  return true ^+ 1;\n}\n", "Expected type int. Received bool."),
        ("unresolved-after-return", 'int main(){return 1;\n  ^missing;\n}\n', 'Undeclared name "missing".'),
        ("static-error-in-skipped-branch", 'bool main(){\n  return true || (true ^+ 1)==0;\n}\n',
         "Expected type int. Received bool."),
        ("zero-array-length", "int main(){int a[^0];return 0;}\n", "Array length must be from 1 through 1024."),
        ("large-array-length", "int main(){int a[^1025];return 0;}\n", "Array length must be from 1 through 1024."),
        ("boolean-index", "int main(){int a[1];return a[^true];}\n", "Expected type int. Received bool."),
        ("argument-count", 'int id(int x){return x;}\nint main(){return ^id();}\n',
         'Function "id" expects 1 argument. Received 0.'),
        ("lexical-before-runtime", 'int main(){return 1/0;}\n^@\n', 'Unexpected character "@".'),
        ("missing-semicolon", 'int main(){return 1^}\n', 'Expected ";" after return value. Received RIGHT_BRACE.'),
    ]
    cases.extend(_error(name, "runtime_error", source, message) for name, source, message in runtime)
    cases.extend(_error(name, "static_error", source, message) for name, source, message in static)
    return cases


def generate_cases(seed: int = DEFAULT_SEED, rounds: int = DEFAULT_ROUNDS) -> list[Case]:
    """Return reproducible cases without changing Python's global random state."""
    if type(seed) is not int or type(rounds) is not int or rounds <= 0:
        raise ValueError("Use an integer seed and a positive integer round count.")
    rng = random.Random(seed)
    cases = []
    for number in range(rounds):
        a, b, c, d = (rng.randint(-50, 50) for _ in range(4))
        divisor = rng.choice(tuple(range(-9, 0)) + tuple(range(1, 10)))
        quotient = int(Fraction(a, divisor))
        limit, factor = rng.randint(-2, 8), rng.randint(-5, 5)
        size, base, stride = rng.randint(1, 8), rng.randint(-20, 20), rng.randint(-5, 5)
        depth, increment = rng.randint(1, 9), rng.randint(1, 5)
        flag = bool(rng.randrange(2))
        spelling = "true" if flag else "false"
        n = max(limit, 0)
        programs = [
            ("arithmetic", f"int main(){{return ({a})*({b})+(({c})-({d}));}}\n", a * b + c - d),
            ("division", f"int main(){{return ({a})/({divisor});}}\n", quotient),
            ("remainder", f"int main(){{return ({a})%({divisor});}}\n", a - divisor * quotient),
            ("assignment", f"int main(){{int x={a};int y={b};return (x=x+{increment})+(y=x*{factor})+x+y;}}\n",
             2 * (a + increment) * (1 + factor)),
            ("argument_order", f"int pair(int a,int b){{return a*100+b;}}\nint main(){{int x={base};"
             f"return pair(x=x+{increment},x=x+{increment})+x;}}\n",
             (base + increment) * 100 + 2 * (base + 2 * increment)),
            ("short_circuit", f"bool main(){{int x={base};bool y=true || (x=99)>0;"
             f"return y && x=={base} && !(false && 1/0==0);}}\n", True),
            ("loop", f"int main(){{int i=0;int total={base};while(i<{limit}){{total=total+i*{factor};i=i+1;}}"
             "return total;}\n", base + factor * n * (n - 1) // 2),
            ("array", f"int main(){{int a[{size}];int i=0;while(i<{size}){{a[i]={base}+i*{stride};i=i+1;}}"
             f"return a[0]+a[{size - 1}];}}\n", 2 * base + (size - 1) * stride),
            ("saved_index", f"int main(){{int a[2];int i=0;a[0]={a};a[1]={b};"
             f"a[i]=(i=1)+{increment};return a[0]*100+a[1]+i;}}\n", (1 + increment) * 100 + b + 1),
            ("recursion", f"int sum(int n){{if(n==0)return {base};return n+sum(n-1);}}\n"
             f"int main(){{return sum({depth});}}\n", base + depth * (depth + 1) // 2),
            ("boolean_array", f"bool main(){{bool a[2];a[0]={spelling};a[1]=!a[0];"
             "return (a[0] && a[1]) || (!a[0] && a[1]);}\n", not flag),
            ("void_call", f"void use(int n){{int copy=n;return;}}\nvoid main(){{use({a});}}\n", None),
        ]
        cases.extend(Case(f"{category}-{number:03d}", category, source, value) for category, source, value in programs)
    return cases + _fixed_cases()
