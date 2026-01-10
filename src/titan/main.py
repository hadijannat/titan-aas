"""Main entry point for Titan-AAS CLI.

This module provides the main entry point for the CLI application.

Usage:
    python -m titan --help
    titan --help  # If installed via pip/uv
"""

from titan.cli import main

if __name__ == "__main__":
    main()
