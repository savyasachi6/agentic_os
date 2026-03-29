import math
import ast
import operator
from typing import Any, Dict
from .base_tool import BaseTool
from core.tool_registry import registry

# Safe operators for literal expression evaluation
_ALLOWED_OPERATORS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.BitXor: operator.xor,
    ast.USub: operator.neg, ast.Mod: operator.mod
}

class ScientificCalculatorTool(BaseTool):
    """
    Evaluates mathematical expressions safely using Python's math module.
    """
    name = "scientific_calculator"
    description = "Evaluate scientific expressions with trig, logs, powers, roots. Examples: 'log10(100) * sin(90)', 'sqrt(16) + 4^2'. Supports pi and e."
    
    parameters_schema = {
        "expression": {
            "type": "string",
            "description": "The mathematical expression to evaluate (e.g. '2 + 2', 'sin(pi/2)'). Use standard Python math functions."
        },
        "precision": {
            "type": "integer",
            "description": "Number of decimal places to return. Default is 8."
        },
        "angle_unit": {
            "type": "string",
            "description": "Whether trigonometric functions should expect 'rad' (radians) or 'deg' (degrees). Default is 'rad'."
        }
    }

    def _eval(self, node):
        if isinstance(node, ast.Num): # <number>
            return node.n
        elif isinstance(node, ast.BinOp): # <left> <operator> <right>
            return _ALLOWED_OPERATORS[type(node.op)](self._eval(node.left), self._eval(node.right))
        elif isinstance(node, ast.UnaryOp): # <operator> <operand> e.g., -1
            return _ALLOWED_OPERATORS[type(node.op)](self._eval(node.operand))
        elif isinstance(node, ast.Call): # <function>(<args>)
            func_name = node.func.id
            if func_name not in self.safe_math_funcs:
                raise ValueError(f"Unsupported math function: {func_name}")
            args = [self._eval(arg) for arg in node.args]
            return self.safe_math_funcs[func_name](*args)
        elif isinstance(node, ast.Name): # <variable> e.g., pi
            if node.id in self.safe_math_vars:
                return self.safe_math_vars[node.id]
            raise ValueError(f"Unknown variable: {node.id}")
        else:
            raise TypeError(f"Unsupported expression node: {type(node)}")

    async def run(self, **kwargs) -> Any:
        expression = kwargs.get("expression", "")
        precision = kwargs.get("precision", 8)
        angle_unit = kwargs.get("angle_unit", "rad").lower()

        if not expression:
            return "Error: No expression provided."

        # Replace standard '^' with python '**'
        expression = expression.replace('^', '**')

        self.safe_math_vars = {
            "pi": math.pi,
            "e": math.e
        }
        
        self.safe_math_funcs = {
            "abs": abs,
            "round": round,
            "sqrt": math.sqrt,
            "log": math.log,
            "log10": math.log10,
            "exp": math.exp,
            "pow": math.pow,
            "ceil": math.ceil,
            "floor": math.floor,
        }

        # Apply angle conversions if degrees are requested
        if angle_unit == "deg":
            self.safe_math_funcs.update({
                "sin": lambda x: math.sin(math.radians(x)),
                "cos": lambda x: math.cos(math.radians(x)),
                "tan": lambda x: math.tan(math.radians(x)),
                "asin": lambda x: math.degrees(math.asin(x)),
                "acos": lambda x: math.degrees(math.acos(x)),
                "atan": lambda x: math.degrees(math.atan(x))
            })
        else:
            self.safe_math_funcs.update({
                "sin": math.sin, "cos": math.cos, "tan": math.tan,
                "asin": math.asin, "acos": math.acos, "atan": math.atan
            })

        try:
            tree = ast.parse(expression, mode='eval')
            result = self._eval(tree.body)
            # Format to precision
            return round(float(result), precision)
        except ZeroDivisionError:
            return "Error: Division by zero."
        except Exception as e:
            return f"Error evaluating expression '{expression}': {str(e)}"

class UnitConverterTool(BaseTool):
    """
    Converts between common scientific units (Length, Mass, Temperature, etc.)
    """
    name = "unit_converter"
    description = "Convert between units like meters to feet, celsius to fahrenheit, kg to lbs. Example: '100 celsius to fahrenheit', '5 km to miles'."
    
    parameters_schema = {
        "value": {
            "type": "number",
            "description": "The numeric value to convert."
        },
        "from_unit": {
            "type": "string",
            "description": "The source unit (e.g. 'celsius', 'meters', 'kg')."
        },
        "to_unit": {
            "type": "string",
            "description": "The target unit (e.g. 'fahrenheit', 'feet', 'lbs')."
        }
    }

    async def run(self, **kwargs) -> Any:
        v = kwargs.get("value", 0)
        f = kwargs.get("from_unit", "").lower().strip()
        t = kwargs.get("to_unit", "").lower().strip()

        # Simple conversion map for demo/scientific purposes
        conversions = {
            ("celsius", "fahrenheit"): lambda x: (x * 9/5) + 32,
            ("fahrenheit", "celsius"): lambda x: (x - 32) * 5/9,
            ("meters", "feet"): lambda x: x * 3.28084,
            ("feet", "meters"): lambda x: x / 3.28084,
            ("km", "miles"): lambda x: x * 0.621371,
            ("miles", "km"): lambda x: x / 0.621371,
            ("kg", "lbs"): lambda x: x * 2.20462,
            ("lbs", "kg"): lambda x: x / 2.20462,
        }

        func = conversions.get((f, t))
        if func:
            res = func(v)
            return round(res, 4)
        
        return f"Error: No conversion found from '{f}' to '{t}'."

# Instantiate and register both tools
calc = ScientificCalculatorTool()
registry.register(
    name=calc.name,
    func=calc.run,
    description=calc.description,
    schema={"parameters": calc.parameters_schema}
)

converter = UnitConverterTool()
registry.register(
    name=converter.name,
    func=converter.run,
    description=converter.description,
    schema={"parameters": converter.parameters_schema}
)
