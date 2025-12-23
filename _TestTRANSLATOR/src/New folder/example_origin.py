"""
SERVICE_NAME: ExampleService

This script demonstrates a simple origin that calculates square roots of
numbers and prints the total.  It contains imports, a helper function and
some main logic.  The convert_script will extract these components and
assemble a microservice class for reuse.
"""

import math
import multiprocessing as mp
import json


def _helper(value: int) -> float:
    """Return the square root of ``value`` using the math module."""
    return math.sqrt(value)


def main() -> None:
    """Compute the sum of square roots for numbers 0 through 4 and print it."""
    total = 0.0
    for i in range(5):
        total += _helper(i)
    print("Sum of square roots:", total)


if __name__ == "__main__":
    main()