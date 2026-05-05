from typing import Any, Dict


class MissingSignal(Exception):
    pass


class InvalidExpression(Exception):
    pass


def _get_path(context: Dict[str, Any], path: str) -> Any:
    parts = path.split(".")
    cur: Any = context
    for part in parts:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise MissingSignal(path)
    return cur


def _resolve_value(value: Any, context: Dict[str, Any]) -> Any:
    if isinstance(value, dict) and "var" in value:
        return _get_path(context, value["var"])
    return value


def eval_expr(expr: Any, context: Dict[str, Any]) -> bool:
    if expr is None:
        return True
    if isinstance(expr, bool):
        return expr
    if isinstance(expr, (int, float, str)):
        raise InvalidExpression("expression must be AST object, boolean, or null")
    if not isinstance(expr, dict):
        raise InvalidExpression("expression must be AST object")

    op = expr.get("op")
    if op == "and":
        args = expr.get("args", [])
        if not isinstance(args, list):
            raise InvalidExpression("'and' operator requires list args")
        return all(eval_expr(arg, context) for arg in args)
    if op == "or":
        args = expr.get("args", [])
        if not isinstance(args, list):
            raise InvalidExpression("'or' operator requires list args")
        return any(eval_expr(arg, context) for arg in args)
    if op == "not":
        return not eval_expr(expr.get("arg"), context)
    if op in {"contains", "has_substr"}:
        left = _resolve_value(expr.get("left"), context)
        right = _resolve_value(expr.get("right"), context)
        if isinstance(left, str):
            return str(right) in left
        if isinstance(left, (list, tuple, set)):
            return right in left
        raise InvalidExpression("'contains' operator requires string or sequence left operand")

    left = _resolve_value(expr.get("left"), context)
    right = _resolve_value(expr.get("right"), context)

    try:
        if op == "eq":
            return left == right
        if op == "neq":
            return left != right
        if op == "gt":
            return left > right
        if op == "gte":
            return left >= right
        if op == "lt":
            return left < right
        if op == "lte":
            return left <= right
        if op == "in":
            return left in right
    except TypeError as exc:
        raise InvalidExpression(str(exc)) from exc

    raise InvalidExpression(f"unknown operator: {op}")
