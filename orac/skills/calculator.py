"""
Calculator skill for mathematical expression evaluation.

This skill safely evaluates mathematical expressions and returns
both the result and a representation of the expression tree.
"""

from typing import Dict, Any, Union
import sympy as sp


def execute(inputs: Dict[str, Any]) -> Union[str, Dict[str, Any]]:
    """
    Execute the calculator skill.

    Args:
        inputs: Dictionary containing:
            - expression (str): Mathematical expression to evaluate
            - precision (int, optional): Decimal places for result

    Returns:
        Dictionary containing:
            - result (float): The calculated result
            - expression_tree (str): String representation of parsed expression

    Raises:
        ValueError: If expression is invalid or cannot be evaluated
    """
    expression = inputs['expression']
    precision = inputs.get('precision', 2)

    try:
        # Parse and evaluate the expression
        expr = sp.sympify(expression)
        result = float(expr.evalf())

        # Round to specified precision
        result = round(result, precision)

        # Get expression tree representation
        expression_tree = str(expr)

        return {
            'result': result,
            'expression_tree': expression_tree
        }
    except Exception as e:
        raise ValueError(f"Failed to evaluate expression: {str(e)}")


# Optional: Additional validation function
def validate_inputs(inputs: Dict[str, Any]) -> None:
    """
    Optional function to perform additional input validation.

    Raises:
        ValueError: If inputs are invalid
    """
    expression = inputs.get('expression', '')

    # Check for potentially dangerous operations
    forbidden = ['import', 'exec', 'eval', '__', 'open', 'file']
    for term in forbidden:
        if term in expression:
            raise ValueError(f"Expression contains forbidden term: {term}")
