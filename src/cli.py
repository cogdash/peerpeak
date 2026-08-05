"""CLI entry point for PeerPeak."""

import subprocess
import sys


def main():
    """Run the FastAPI application."""
    # Pass through any additional arguments to fastapi run
    args = ["fastapi", "run", "src/main.py"] + sys.argv[1:]
    subprocess.run(args, check=True)


if __name__ == "__main__":
    main()
