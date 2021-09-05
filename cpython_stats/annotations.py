# © Copyright 2021 Łukasz Langa.  Licensed under Apache License, Version 2.0.

from __future__ import annotations
from typing import *

import ast
from functools import singledispatch
import typing


def sanitize(o: object) -> None:
    new_anns = {k: maybe_clean_annotation(v) for k, v in o.__annotations__.items()}
    o.__annotations__ = new_anns


@singledispatch
def maybe_clean_annotation(o: object) -> Any:
    return o


@maybe_clean_annotation.register
def _mc_str(s: str) -> str:
    a = ast.parse(s, mode="single", feature_version=(3, 9))
    a = clean_annotation(a)
    return ast.unparse(a)


@singledispatch
def clean_annotation(o: object) -> ast.AST:
    raise TypeError(type(o))


@clean_annotation.register
def _c_ast(a: ast.AST) -> ast.AST:
    return a


@clean_annotation.register
def _c_interactive(interactive: ast.Interactive) -> ast.AST:
    interactive.body = [
        cast(ast.stmt, clean_annotation(expr)) for expr in interactive.body
    ]
    return interactive


@clean_annotation.register
def _c_expr(expr: ast.Expr) -> ast.AST:
    expr.value = cast(ast.expr, clean_annotation(expr.value))
    return expr


@clean_annotation.register
def _c_binop(binop: ast.BinOp) -> ast.AST:
    binop.left = cast(ast.expr, clean_annotation(binop.left))
    binop.right = cast(ast.expr, clean_annotation(binop.right))
    if isinstance(binop.op, ast.BitOr):
        result = ast.Subscript()
        result.value = ast.Name(id="Union", ctx=ast.Load())
        result.slice = ast.Tuple(
            elts=[binop.left, binop.right],
            ctx=ast.Load(),
        )
        result.ctx = ast.Load()
        return result

    binop.op = cast(ast.operator, clean_annotation(binop.op))
    return binop


@clean_annotation.register
def _c_subscript(sub: ast.Subscript) -> ast.AST:
    sub.value = cast(ast.expr, clean_annotation(sub.value))
    sub.slice = cast(ast.expr, clean_annotation(sub.slice))
    return sub


@clean_annotation.register
def _c_tuple(tup: ast.Tuple) -> ast.AST:
    tup.elts = [cast(ast.expr, clean_annotation(elt)) for elt in tup.elts]
    return tup


_eval_type_orig = typing._eval_type  # type: ignore


def _eval_type_patched(t, globalns, localns, recursive_guard=frozenset()):
    if isinstance(t, ForwardRef) and not t.__forward_evaluated__:
        farg = maybe_clean_annotation(t.__forward_arg__)
        t = ForwardRef(farg, is_argument=False)
        return t._evaluate(globalns, localns, recursive_guard)

    return _eval_type_orig(t, globalns, localns, recursive_guard)


def patch_typing() -> None:
    if typing._eval_type is not _eval_type_patched:  # type: ignore
        typing._eval_type = _eval_type_patched  # type: ignore
