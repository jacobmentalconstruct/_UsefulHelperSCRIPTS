#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
== Generic Python Module/CLI Boilerplate ==

This is a generic template for a Python file that can be:
1.  Imported as a module by other scripts (e.g., `import generic_module`).
2.  Run as a standalone command-line script (e.g., `$ python generic_module.py --input data.txt`).

How to use this template:
1.  Rename this file to match your new tool (e.g., `my_data_processor.py`).
2.  Update this docstring to describe what your tool does.
3.  Fill in the "CORE FUNCTIONALITY" section with your app's logic.
4.  Go to the `main()` function to define your CLI arguments.
5.  In `main()`, add the code to call your core functions using the parsed arguments.
"""

# 1. IMPORTS
# Standard library imports
import sys
import os
import argparse  # For parsing command-line arguments
from tkinter import ttk  # Required for the Dropdown/Combobox

# Third-party imports (if any)
# e.g., import requests

# Local/application imports (if any)
# e.g., from . import my_other_module


# 2. CONSTANTS
# TODO: Define any constants your application needs.
SOME_DEFAULT_SETTING = "default_value"


# 3. CORE FUNCTIONALITY (The "Importable" Module)
#
# These functions make up the "core logic" of your application.
# They can be imported and used by other Python scripts.
# They should be self-contained and not rely on command-line arguments.

def core_logic_function(data: any, setting: str = SOME_DEFAULT_SETTING) -> any:
    """
    TODO: Replace this with your main logic function.
    
    This function should perform the primary task of your module.
    
    Args:
        data (any): The input data to process.
        setting (str, optional): An example of an optional setting.
                                 Defaults to SOME_DEFAULT_SETTING.

    Returns:
        any: The processed data.
    """
    print(f"[Core Logic] Processing data with setting: {setting}")
    
    # --- TODO: Your actual logic goes here ---
    # Example:
    try:
        processed_data = f"Processed data: {str(data).upper()}"
        print("[Core Logic] Processing complete.")
        return processed_data
    except Exception as e:
        print(f"[Core Logic] Error during processing: {e}", file=sys.stderr)
        # Re-raise the exception to be handled by the caller
        raise


def helper_function(value: int) -> str:
    """
    TODO: Add any helper functions your core logic needs.
    
    This is an example of a helper that might be called by
    core_logic_function or also be importable.
    
    Args:
        value (int): An input value.

    Returns:
        str: A formatted string.
    """
    return f"Helper processed value: {value * 2}"


# 4. CLI (Command-Line Interface) LOGIC
#
# This code only runs when the script is executed directly.
# It should handle parsing arguments and calling the core functions.

def main():
    """
    Main function to run the script from the command line.
    
    It parses arguments, calls core functions, and handles CLI-specific
    input/output and error handling.
    """
    
    # --- Argument Parsing ---
    # Set up the argument parser
    # TODO: Update the description to match your tool.
    parser = argparse.ArgumentParser(
        description="A generic CLI tool. TODO: Describe your tool here.",
        epilog="Example: python generic_module.py my_input.txt -o my_output.txt -v"
    )
    
    # --- TODO: Define your arguments ---
    
    # Example of a required positional argument
    parser.add_argument(
        "input_path",  # The name of the argument
        type=str,
        help="TODO: Describe this required input (e.g., path to an input file)."
    )
    
    # Example of an optional argument (e.g., -o or --output)
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,  # Default to None if not provided
        help="TODO: Describe this optional argument (e.g., path to an output file)."
    )
    
    # Example of a "flag" argument (stores True if present)
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",  # This makes it a boolean flag
        help="Enable verbose output."
    )
    
    # Parse the arguments from the command line (e.g., sys.argv)
    args = parser.parse_args()

    # --- Main Application Flow ---
    
    # Use the 'verbose' flag to control print statements
    if args.verbose:
        print("Verbose mode enabled.", file=sys.stderr)
        print(f"Arguments received: {args}", file=sys.stderr)

    try:
        # 1. Load data (CLI-specific task)
        #    TODO: Replace this with your actual data loading
        if args.verbose:
            print(f"Loading data from {args.input_path}...", file=sys.stderr)
        # This is just an example. You'd likely load a file here.
        input_data = f"Content of {args.input_path}" 

        # 2. Call core logic (the "importable" part)
        if args.verbose:
            print("Calling core logic...", file=sys.stderr)
        
        # Here we pass the CLI arguments to the core function
        processed_data = core_logic_function(input_data)
        
        # 3. Handle output (CLI-specific task)
        if args.output:
            # Save to a file
            if args.verbose:
                print(f"Saving processed data to {args.output}...", file=sys.stderr)
            # TODO: Add file-saving logic here
            # with open(args.output, 'w') as f:
            #     f.write(processed_data)
            print(f"Success: Output saved to {args.output}")
        else:
            # Print to standard output
            if args.verbose:
                print("Printing processed data to stdout:", file=sys.stderr)
            print(processed_data)
        
        # Exit with a success code
        sys.exit(0)

    except FileNotFoundError as e:
        print(f"\nError: Input file not found.", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        sys.exit(1) # Exit with a non-zero error code
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


# This "magic" line is the key to the whole pattern:
#
# - If you run `python generic_module.py ...`, Python sets
#   __name__ = "__main__", and the main() function is called.
#
# - If you `import generic_module` in another script, __name__
#   is "generic_module", so this block is SKIPPED.
#
if __name__ == "__main__":
    main()