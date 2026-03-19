import re


class Expression:
    """
    Evaluates SQL WHERE clause conditions against a row.

    Supports:
        Comparison:  =, !=, <>, >, <, >=, <=, IN, BETWEEN, LIKE, IS NULL, IS NOT NULL
        Logical:     AND, OR, NOT
        Arithmetic:  +, -, *, /, % on numeric values
        Bitwise:     &, |, ^, ~, <<, >>

    A condition is a dict with structure:
        Simple:   {"type": "simple", "column": str, "op": str, "value": any}
        IN:       {"type": "in", "column": str, "values": list}
        BETWEEN:  {"type": "between", "column": str, "low": any, "high": any}
        IS NULL:  {"type": "is_null", "column": str, "negated": bool}
        LIKE:     {"type": "like", "column": str, "pattern": str}
        AND/OR:   {"type": "and"/"or", "left": condition, "right": condition}
        NOT:      {"type": "not", "condition": condition}
    """

    COMPARISON_OPS = {"=", "!=", "<>", ">", "<", ">=", "<="}
    ARITHMETIC_OPS = {"+", "-", "*", "/", "%"}
    BITWISE_OPS    = {"&", "|", "^", "~", "<<", ">>"}

    @staticmethod
    def evaluate(condition: dict, row: list, column_index: dict) -> bool:
        """
        Evaluate a condition dict against a single row.
        Returns True if the row satisfies the condition, False otherwise.
        """
        ctype = condition["type"]

        if ctype == "and":
            return (
                Expression.evaluate(condition["left"], row, column_index) and
                Expression.evaluate(condition["right"], row, column_index)
            )

        if ctype == "or":
            return (
                Expression.evaluate(condition["left"], row, column_index) or
                Expression.evaluate(condition["right"], row, column_index)
            )

        if ctype == "not":
            return not Expression.evaluate(condition["condition"], row, column_index)

        col     = condition["column"]
        col_idx = column_index.get(col)

        if col_idx is None:
            raise ValueError(f"Column '{col}' does not exist.")

        cell_value = row[col_idx]

        if ctype == "is_null":
            result = cell_value is None
            return result if not condition.get("negated") else not result

        if ctype == "like":
            if not isinstance(cell_value, str):
                return False
            pattern = Expression._like_to_regex(condition["pattern"])
            return bool(re.fullmatch(pattern, cell_value, re.IGNORECASE))

        if ctype == "in":
            return cell_value in condition["values"]

        if ctype == "between":
            return condition["low"] <= cell_value <= condition["high"]

        if ctype == "simple":
            op    = condition["op"]
            value = condition["value"]

            # Apply arithmetic to cell value if specified
            if "arithmetic" in condition:
                cell_value = Expression._apply_arithmetic(
                    cell_value,
                    condition["arithmetic"]["op"],
                    condition["arithmetic"]["operand"]
                )

            if op in ("=",):
                return cell_value == value
            if op in ("!=", "<>"):
                return cell_value != value
            if op == ">":
                return cell_value > value
            if op == "<":
                return cell_value < value
            if op == ">=":
                return cell_value >= value
            if op == "<=":
                return cell_value <= value

            # Bitwise comparisons
            if op == "&":
                return bool(cell_value & value)
            if op == "|":
                return bool(cell_value | value)
            if op == "^":
                return bool(cell_value ^ value)
            if op == "<<":
                return bool(cell_value << value)
            if op == ">>":
                return bool(cell_value >> value)

        raise ValueError(f"Unknown condition type: {ctype}")

    @staticmethod
    def _apply_arithmetic(value, op: str, operand):
        """
        Apply an arithmetic operator to a cell value before comparison.
        Used for expressions like WHERE salary + 5000 > 100000.
        """
        if op == "+":
            return value + operand
        if op == "-":
            return value - operand
        if op == "*":
            return value * operand
        if op == "/":
            if operand == 0:
                raise ValueError("Division by zero in WHERE clause.")
            return value / operand
        if op == "%":
            if operand == 0:
                raise ValueError("Modulo by zero in WHERE clause.")
            return value % operand
        raise ValueError(f"Unknown arithmetic operator: {op}")

    @staticmethod
    def _like_to_regex(pattern: str) -> str:
        """
        Convert a SQL LIKE pattern to a Python regex pattern.
        SQL wildcards:
            % matches any sequence of characters
            _ matches exactly one character
        All other regex special characters are escaped.
        """
        regex = ""
        for char in pattern:
            if char == "%":
                regex += ".*"
            elif char == "_":
                regex += "."
            else:
                regex += re.escape(char)
        return regex