import ast
import operator
import re
from dataclasses import dataclass


class FormulaError(ValueError):
    pass


OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

COMPARATORS = {
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}


@dataclass
class FormulaResult:
    value: float
    dependencies: set[str]


class SafeFormulaEngine:
    """Evaluates arithmetic formulas without exposing Python execution."""

    def __init__(self, variables):
        self.variables = {self._key(k): float(v or 0) for k, v in variables.items()}
        self.dependencies = set()

    def evaluate(self, expression):
        if not expression:
            return FormulaResult(0.0, set())
        normalized = self._normalize(expression)
        try:
            tree = ast.parse(normalized, mode="eval")
            value = self._eval(tree.body)
        except ZeroDivisionError as exc:
            raise FormulaError("Formula divides by zero") from exc
        except Exception as exc:
            raise FormulaError("Formula is invalid") from exc
        return FormulaResult(round(float(value), 4), set(self.dependencies))

    def _eval(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](self._eval(node.left), self._eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](self._eval(node.operand))
        if isinstance(node, ast.IfExp):
            return self._eval(node.body) if self._eval(node.test) else self._eval(node.orelse)
        if isinstance(node, ast.Compare):
            left = self._eval(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval(comparator)
                if type(op) not in COMPARATORS or not COMPARATORS[type(op)](left, right):
                    return 0
                left = right
            return 1
        if isinstance(node, ast.Name):
            key = self._key(node.id)
            self.dependencies.add(key)
            if key not in self.variables:
                raise FormulaError(f"Unknown formula variable: {node.id}")
            return self.variables[key]
        raise FormulaError("Only arithmetic formulas are allowed")

    def _normalize(self, expression):
        expression = expression.replace("^", "**")
        expression = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", expression)
        expression = self._normalize_if_then(expression)
        return expression

    def _normalize_if_then(self, expression):
        lines = [line.strip() for line in expression.splitlines() if line.strip()]
        if len(lines) > 1 and all(line.lower().startswith("if ") for line in lines):
            return " + ".join(f"({self._normalize_if_then(line)})" for line in lines)
        match = re.match(r"if\s+(.+?)\s+then\s+(.+?)(?:\s+else\s+(.+))?$", expression, flags=re.IGNORECASE)
        if not match:
            return expression
        condition, then_expr, else_expr = match.groups()
        then_expr = then_expr.split("=", 1)[-1].strip()
        else_expr = (else_expr or "0").split("=", 1)[-1].strip()
        return f"({then_expr}) if ({condition}) else ({else_expr})"

    @staticmethod
    def _key(name):
        return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def calculate_materials(width, height, materials):
    base = {
        "Width": width,
        "W": width,
        "Weight": width,
        "Height": height,
        "H": height,
        "Area": float(width or 0) * float(height or 0),
        "Perimeter": (float(width or 0) * 2) + (float(height or 0) * 2),
    }
    quantities = {}
    visiting = set()
    resolved = {}

    material_map = {SafeFormulaEngine._key(m["material_name"]): m for m in materials}
    material_names = {
        SafeFormulaEngine._key(m["material_name"]): m["material_name"]
        for m in materials
        if m.get("material_name")
    }

    def normalize_material_references(expression):
        """Allow formulas such as 'Glass Panel * 2' by converting known material names to safe variable keys."""
        output = expression or ""
        for key, display_name in sorted(material_names.items(), key=lambda item: len(item[1]), reverse=True):
            if not display_name:
                continue
            output = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(display_name)}(?![A-Za-z0-9_])", key, output, flags=re.IGNORECASE)
        return output

    def resolve(key):
        if key in resolved:
            return resolved[key]
        if key in visiting:
            raise FormulaError("Circular material dependency detected")
        visiting.add(key)
        material = material_map[key]
        pending_materials = {name: 0 for name in material_map if name not in quantities}
        variables = {**base, **pending_materials, **quantities}
        engine = SafeFormulaEngine(variables)
        if material.get("auto_formula") and not material.get("manual_override"):
            formula = normalize_material_references(material.get("formula"))
            result = engine.evaluate(formula)
            for dep in result.dependencies:
                if dep in material_map and dep not in quantities:
                    quantities[dep] = resolve(dep)
            result = SafeFormulaEngine({**base, **quantities}).evaluate(formula)
            qty = result.value
        else:
            qty = float(material.get("quantity") or 0)
        waste = 1 + (float(material.get("waste_percent") or 0) / 100)
        qty = round(qty * waste, 4)
        resolved[key] = qty
        quantities[key] = qty
        visiting.remove(key)
        return qty

    for key in list(material_map):
        resolve(key)

    output = []
    for material in materials:
        key = SafeFormulaEngine._key(material["material_name"])
        item = dict(material)
        item["quantity"] = resolved[key]
        item["total_price"] = round(resolved[key] * float(item.get("unit_price") or 0), 2)
        output.append(item)
    return output
