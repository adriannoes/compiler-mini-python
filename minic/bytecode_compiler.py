"""Compile a checked syntax tree into scalar Mini-C bytecode."""

from dataclasses import replace
from typing import Iterator, Optional, Union

from . import ast
from .bytecode import (
    BINARY_OPS, BytecodeFunction, BytecodeProgram, Constant, Instruction, IntegerConstant, Local, Op,
)
from .lexer import Token, TokenKind as Kind
from .type_checker import Type, TypeAnalysis, check_types


_Node = Union[ast.Stmt, ast.Expr]
_LocalDeclaration = Union[ast.Variable, ast.Parameter]


class _Compiler:
    def __init__(self, source: ast.Function, analysis: TypeAnalysis, functions: dict[ast.Function, int]):
        self.analysis = analysis
        self.functions = functions
        self.slots: dict[_LocalDeclaration, int] = {}
        self.function = BytecodeFunction(source.token, Type(source.return_type.text), len(source.parameters))
        for parameter in source.parameters:
            self.add_local(parameter)

    def add_local(self, declaration: _LocalDeclaration) -> int:
        slot = len(self.function.locals)
        self.slots[declaration] = slot
        self.function.locals.append(Local(declaration.token, Type(declaration.type_token.text)))
        return slot

    def slot(self, name: ast.Name) -> int:
        declaration = self.analysis.resolution.bindings[name].symbol.declaration
        assert isinstance(declaration, (ast.Parameter, ast.Variable))
        return self.slots[declaration]

    def emit(self, op: Op, token: Token, operand: Optional[int] = None) -> int:
        offset = len(self.function.code)
        self.function.code.append(Instruction(op, token, operand))
        return offset

    def patch_jump(self, offset: int) -> None:
        code = self.function.code
        code[offset] = replace(code[offset], operand=len(code))

    def constant(self, value: Constant, token: Token) -> None:
        index = len(self.function.constants)
        self.function.constants.append(value)
        self.emit(Op.LOAD_CONSTANT, token, index)

    def statement(self, stmt: ast.Stmt) -> Iterator[_Node]:
        token = stmt.token
        if isinstance(stmt, ast.Block):
            yield from stmt.statements
        elif isinstance(stmt, ast.Variable):
            slot = self.add_local(stmt)
            self.emit(Op.RESET_LOCAL, token, slot)
            if stmt.initializer is not None:
                yield stmt.initializer
                self.emit(Op.STORE_LOCAL, token, slot)
                self.emit(Op.POP, token)
        elif isinstance(stmt, ast.ExpressionStmt):
            yield stmt.value
            if self.analysis.types[stmt.value] is not Type.VOID:
                self.emit(Op.POP, token)
        elif isinstance(stmt, ast.Return):
            if stmt.value is None:
                self.emit(Op.RETURN_VOID, token)
            else:
                yield stmt.value
                self.emit(Op.RETURN, token)
        elif isinstance(stmt, ast.If):
            yield stmt.condition
            alternate = self.emit(Op.JUMP_IF_FALSE, token)
            yield stmt.then_branch
            if stmt.else_branch is None:
                self.patch_jump(alternate)
            else:
                end = self.emit(Op.JUMP, token)
                self.patch_jump(alternate)
                yield stmt.else_branch
                self.patch_jump(end)
        elif isinstance(stmt, ast.While):
            start = len(self.function.code)
            yield stmt.condition
            end = self.emit(Op.JUMP_IF_FALSE, token)
            yield stmt.body
            self.emit(Op.JUMP, token, start)
            self.patch_jump(end)
        elif not isinstance(stmt, ast.Empty):
            raise TypeError(f"Unknown statement: {type(stmt).__name__}.")

    def expression(self, expr: ast.Expr) -> Iterator[ast.Expr]:
        token = expr.token
        if isinstance(expr, ast.Literal):
            if token.kind is Kind.INTEGER:
                self.constant(IntegerConstant(token.text), token)
            else:
                self.constant(token.kind is Kind.TRUE, token)
        elif isinstance(expr, ast.Name):
            self.emit(Op.LOAD_LOCAL, token, self.slot(expr))
        elif isinstance(expr, ast.Assign):
            yield expr.value
            self.emit(Op.STORE_LOCAL, token, self.slot(expr.target))
        elif isinstance(expr, ast.Call):
            yield from expr.arguments
            function = self.analysis.resolution.bindings[expr].symbol.declaration
            assert isinstance(function, ast.Function)
            self.emit(Op.CALL, token, self.functions[function])
        elif isinstance(expr, ast.Unary):
            operand = expr.operand
            if token.kind is Kind.MINUS and isinstance(operand, ast.Literal) and operand.token.kind is Kind.INTEGER:
                self.emit(Op.STEP, operand.token)
                self.constant(IntegerConstant(operand.token.text, negative=True), token)
            else:
                yield operand
                self.emit(Op.NEGATE if token.kind is Kind.MINUS else Op.NOT, token)
        elif isinstance(expr, ast.Binary):
            yield expr.left
            if token.kind in (Kind.OR_OR, Kind.AND_AND):
                skip_value = token.kind is Kind.OR_OR
                skip = self.emit(Op.JUMP_IF_TRUE if skip_value else Op.JUMP_IF_FALSE, token)
                yield expr.right
                end = self.emit(Op.JUMP, token)
                self.patch_jump(skip)
                self.constant(skip_value, token)
                self.patch_jump(end)
            else:
                yield expr.right
                self.emit(BINARY_OPS[token.kind], token)
        else:
            raise TypeError(f"Unknown expression: {type(expr).__name__}.")

    def visit(self, node: _Node) -> Iterator[_Node]:
        self.emit(Op.STEP, node.token)
        if isinstance(node, ast.Expr):
            return self.expression(node)
        return self.statement(node)

    def compile_body(self, body: ast.Block) -> BytecodeFunction:
        # Resume the parent after each child emits its instructions.
        pending = [self.visit(body)]
        while pending:
            child = next(pending[-1], None)
            if child is None:
                pending.pop()
            else:
                pending.append(self.visit(child))
        end = Op.RETURN_VOID if self.function.result is Type.VOID else Op.UNREACHABLE
        self.emit(end, body.token)
        return self.function


def compile_bytecode(program: ast.Program) -> BytecodeProgram:
    analysis = check_types(program)
    functions = {function: index for index, function in enumerate(program.functions)}
    return BytecodeProgram(tuple(
        _Compiler(function, analysis, functions).compile_body(function.body)
        for function in program.functions
    ))
