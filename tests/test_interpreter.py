import unittest

from minic.interpreter import interpret
from minic.lexer import lex
from minic.parser import parse
from minic.resolver import AnalysisError
from minic.runtime import VOID, BoolValue, ExecutionError, ExecutionLimits, IntValue


def run(source, **kwargs):
    return interpret(parse(lex(source.encode("ascii"))), **kwargs)


class InterpreterTests(unittest.TestCase):
    def test_static_analysis_precedes_entry_selection_and_execution(self):
        for source, expected in [
            ('void other() { missing; }', 'Undeclared name "missing".'),
            ('int main(int p) {return 1;} int bad() {return true;}', "Expected type int. Received bool."),
            ('int main() {return 1/0;} int bad() {return true;}', "Expected type int. Received bool."),
        ]:
            with self.subTest(source=source):
                with self.assertRaises(AnalysisError) as caught:
                    run(source)
                self.assertEqual(str(caught.exception), expected)
        self.assertEqual(run("bool ready() {return true;}", entry="ready"), BoolValue(True))

    def test_entry_errors_have_source_positions(self):
        for source, line, column, message in [
            ("", 1, 1, 'The entry function "main" does not exist.'),
            ("\nint main(int n) {return n;}", 2, 5, 'The entry function "main" must not have parameters.'),
        ]:
            with self.subTest(source=source):
                with self.assertRaises(ExecutionError) as caught:
                    run(source)
                error = caught.exception
                self.assertEqual((error.line, error.column, str(error)), (line, column, message))

    def test_assignment_targets_and_arguments_use_the_resolved_declaration(self):
        source = """
            int main() {
              int x = 0;
              int r = pair(x = x + 1, x = x + 1);
              { int x = r; x = 0; }
              return r * 10 + x;
            }
            int pair(int a, int b) { int n = a * 10 + b; a = 9; return n; }
        """
        self.assertEqual(run(source), IntValue(122))
        self.assertEqual(run("int main(){int a; int b; int c=a=b=3; return a+b+c;}"), IntValue(9))

    def test_reentering_a_declaration_clears_its_slot(self):
        for source, column in [
            ("int main(){int x=1; {int x=\nx;} return x;}", 1),
            ("int main(){int i=0; while(i<2){int x; if(i==0)x=0; i=i+1;\n  x;} return 1;}", 3),
        ]:
            with self.subTest(source=source):
                with self.assertRaises(ExecutionError) as caught:
                    run(source)
                error = caught.exception
                self.assertEqual((error.line, error.column, str(error)), (2, column, 'The variable "x" has no value.'))

    def test_branch_selection_and_short_circuit_preserve_side_effects(self):
        self.assertEqual(run("int main(){ int x=0; false && ((x=1)==1); true || (1/0==0);"
                             "if(false) x=99; while(false) x=99; return x;}"), IntValue(0))
        self.assertEqual(run("bool main(){bool x=false; true && (x=true); false || (x=!x); return x;}"),
                         BoolValue(False))
        self.assertEqual(run("int main(){int x=0; return (x=1) + (x=x+1);}"), IntValue(3))
        self.assertEqual(run("bool main(){ return true || 999999999999999999999999 == 0;}"), BoolValue(True))

    def test_return_exits_only_the_current_call(self):
        self.assertIs(run("void main(){while(true) {if(true) return;} 1/0;}"), VOID)
        self.assertIs(run("void main(){}"), VOID)
        self.assertEqual(run("void stop(){return;} int main(){stop(); return 0;}"), IntValue(0))
        self.assertEqual(run("int main(){while(true) {return 0;} return 1/0;}"), IntValue(0))

    def test_errors_point_to_the_first_evaluated_operation(self):
        for expression, column, message in [
            ("-0009223372036854775809", 1, "The integer literal is outside the signed 64-bit range."),
            ("(9223372036854775808)", 2, "The integer literal is outside the signed 64-bit range."),
            ("-(-9223372036854775808)", 1, "Integer arithmetic exceeds the signed 64-bit range."),
            ("(1 / 0) + 9223372036854775808", 4, "The divisor is zero."),
        ]:
            with self.subTest(expression=expression):
                with self.assertRaises(ExecutionError) as caught:
                    run("int main(){return\n" + expression + ";}")
                error = caught.exception
                self.assertEqual((error.line, error.column, str(error)), (2, column, message))

    def test_recursive_frames_keep_independent_local_values(self):
        self.assertEqual(run("int main(){return sum(3);}"
                             "int sum(int n){int x=n*10; if(n==0)return 0; return sum(n-1)+x;}"), IntValue(60))
        self.assertEqual(run("bool even(int n){if(n==0)return true; return odd(n-1);}"
                             "bool odd(int n){if(n==0)return false; return even(n-1);}"
                             "bool main(){return even(10) && odd(9);}"), BoolValue(True))

    def test_call_arguments_finish_before_the_depth_check(self):
        for arg, column, message in [("1/0", 4, "The divisor is zero."),
                                     ("1", 1, "The call depth limit was reached.")]:
            with self.subTest(arg=arg):
                with self.assertRaises(ExecutionError) as caught:
                    run("int f(int x){return x;} int main(){return\nf(" + arg + ");}",
                        limits=ExecutionLimits(100, 1))
                error = caught.exception
                self.assertEqual((error.line, error.column, str(error)), (2, column, message))

    def test_steps_charge_only_executed_source_nodes(self):
        for source, steps, column, value in [
            ("int main(){return 42;}", 3, 19, IntValue(42)),
            ("int main(){return -(9223372036854775808);}", 4, 21, IntValue(-(1 << 63))),
            ("int main(){int x; return x=42;}", 5, 28, IntValue(42)),
            ("bool main(){return true || 1/0==0;}", 4, 20, BoolValue(True)),
        ]:
            with self.subTest(source=source):
                self.assertEqual(run(source, limits=ExecutionLimits(steps, 1)), value)
                with self.assertRaises(ExecutionError) as caught:
                    run(source, limits=ExecutionLimits(steps - 1, 1))
                self.assertEqual(caught.exception.column, column)
                self.assertEqual(str(caught.exception), "The execution step limit was reached.")

    def test_long_expressions_and_deep_calls_use_the_mini_c_limits(self):
        self.assertEqual(run("int main(){return " + "1+" * 1500 + "1;}"), IntValue(1501))
        source = ("int main(){return count(1200);}"
                  "int count(int n){if(n==0)return 0; return 1+count(n-1);}")
        self.assertEqual(run(source, limits=ExecutionLimits(50_000, 1202)), IntValue(1200))
        with self.assertRaises(ExecutionError) as caught:
            run(source)
        self.assertEqual(str(caught.exception), "The call depth limit was reached.")

    def test_invalid_limits_are_rejected(self):
        for steps, depth in [(0, 1), (1, 0), (-2, 1), (True, 1)]:
            with self.subTest(steps=steps, depth=depth):
                with self.assertRaises(ValueError) as caught:
                    ExecutionLimits(steps, depth)
                self.assertEqual(str(caught.exception), "Execution limits must be greater than zero.")
