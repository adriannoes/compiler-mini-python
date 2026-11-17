import unittest
from dataclasses import replace

from minic.bytecode import Op
from minic.bytecode_compiler import compile_bytecode
from minic.bytecode_optimizer import optimize_bytecode
from minic.interpreter import interpret
from minic.lexer import lex
from minic.parser import parse
from minic.runtime import BoolValue, ExecutionError, ExecutionLimits, IntValue
from minic.vm import InvalidBytecode, execute_bytecode


def executions(source):
    tree = parse(lex(source.encode("ascii")))
    code = compile_bytecode(tree)
    return ((interpret, tree), (execute_bytecode, code), (execute_bytecode, optimize_bytecode(code)))


def outcome(engine, program, limits):
    try:
        return engine(program, limits=limits)
    except ExecutionError as error:
        return error.line, error.column, str(error)


class ArrayRuntimeTests(unittest.TestCase):
    def test_indices_and_rhs_calls_keep_the_original_target(self):
        for body, expected in (
            ("int a[2]; int i=0; a[i]=(a[i=1]=5); return a[0]*10+a[1]+i;", IntValue(56)),
            ("int a[2]; int i=0; a[id(i=1)]=id(i=0); return a[1]+i;", IntValue(0)),
            ("int a[2]; int x=a[0]=a[1]=7; return x+a[0]+a[1];", IntValue(21)),
            ("int a[1024]; a[0]=3; a[1023]=7; return a[0]+a[1023];", IntValue(10)),
            ("int a[1]; a[0]=3; {bool a[1]; a[0]=false;} {int a=1;} return a[0];", IntValue(3)),
        ):
            for engine, program in executions("int id(int n){return n;} int main(){" + body + "}"):
                with self.subTest(body=body, engine=engine.__name__):
                    self.assertEqual(engine(program), expected)
        for engine, program in executions("bool main(){bool a[1]; a[0]=false; return (a[0]=true)==a[0];}"):
            self.assertEqual(engine(program), BoolValue(True))

    def test_bounds_errors_precede_rhs_errors_and_use_the_array_name_position(self):
        for index in ("-1", "1", "9223372036854775807", "-9223372036854775808"):
            source = "int main(){int a[1];\n  a[" + index + "]=1/0; return 0;}"
            for engine, program in executions(source):
                with self.subTest(index=index, engine=engine.__name__):
                    self.assertEqual(outcome(engine, program, ExecutionLimits()),
                                     (2, 3, f'The array index {index} is outside "a" with length 1.'))

    def test_elements_are_independent_and_declarations_clear_storage_in_loops(self):
        for source in (
            "int main(){int a[2]; a[0]=1;\n  return a[1];}",
            "int main(){int i=0; while(i<2){int a[2]; if(i==0)a[1]=1; i=i+1;\n  return a[0];} return 0;}",
            "int main(){int i=0; while(i<2){int a[1]; if(i==0)a[0]=1; i=i+1;\n  a[0];} return 0;}",
        ):
            for engine, program in executions(source):
                with self.subTest(source=source, engine=engine.__name__):
                    error = outcome(engine, program, ExecutionLimits())
                    self.assertEqual(error[0], 2)
                    self.assertIn("has no value.", error[2])

    def test_calls_keep_private_arrays_and_repeated_execution_starts_fresh(self):
        source = ("int sum(int n){int a[2]; a[0]=n; if(n==0)return a[0];"
                  "a[1]=sum(n-1); return a[0]+a[1];} int main(){return sum(10);}")
        for engine, program in executions(source):
            for _ in range(2):
                self.assertEqual(engine(program), IntValue(55))

    def test_limits_agree_at_each_array_access_boundary(self):
        for source in (
            "int main(){int a[1]; a[0]=7; return a[0];}",
            "int main(){int a[1]; return a[0];}",
            "int main(){int a[1]; a[-1]=1/0; return 0;}",
            "int main(){int a[2]; int i=0; a[i]=(i=1); return a[0];}",
            "int f(int n){int a[1]; a[0]=n; if(n==0)return a[0]; a[0]=a[0]+f(n-1); return a[0];}"
            "int main(){return f(3);}",
            "void f(){} int main(){int a[1]; f(); a[0]=1; return a[0];}",
            "int main(){int i=0; while(i<2){int a[1]; if(i==0)a[0]=2; i=i+1; a[0];} return 0;}",
            "bool main(){bool a[1]; false && a[0]; a[0]=true; return a[0] || a[-1];}",
        ):
            engines = executions(source)
            for steps in range(1, 81):
                for depth in (1, 2, 4):
                    with self.subTest(source=source, steps=steps, depth=depth):
                        limits = ExecutionLimits(steps, depth)
                        outcomes = [outcome(engine, program, limits) for engine, program in engines]
                        self.assertEqual(outcomes[0], outcomes[1])
                        self.assertEqual(outcomes[0], outcomes[2])

    def test_vm_rejects_invalid_array_metadata_and_scalar_array_access(self):
        for invalid in ("length", "slot", "scalar"):
            code = executions("int main(){int a[1]; a[0]=7; return a[0];}")[1][1]
            function = code.functions[0]
            if invalid == "length":
                function.locals[0] = replace(function.locals[0], length=1025)
            else:
                offset = next(i for i, ins in enumerate(function.code) if ins.op is Op.CHECK_INDEX)
                instruction = function.code[offset]
                function.code[offset] = (replace(instruction, operand=99) if invalid == "slot"
                                         else replace(instruction, op=Op.LOAD_LOCAL))
            with self.subTest(invalid=invalid), self.assertRaises(InvalidBytecode):
                execute_bytecode(code)
