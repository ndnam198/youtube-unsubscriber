#!/usr/bin/env python3
"""
Development tools runner for YouTube Unsubscriber.
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"\n🔧 {description}...")
    try:
        result = subprocess.run(
            cmd, shell=True, check=True, capture_output=True, text=True
        )
        print(f"✅ {description} completed successfully")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False


def main():
    """Run development tools."""
    project_root = Path(__file__).parent.parent

    print("🚀 YouTube Unsubscriber Development Tools")
    print("=" * 50)

    # Change to project root

    os.chdir(project_root)

    # Available commands
    commands = {
        "format": ("uv run black --config=.black src/", "Format code with Black"),
        "check": ("uv run black --config=.black --check src/", "Check code formatting"),
        "all": None,  # Special case
    }

    if len(sys.argv) < 2:
        print("Available commands:")
        for cmd, value in commands.items():
            if cmd != "all" and value is not None:
                _, desc = value
                print(f"  {cmd:<12} - {desc}")
        print("  all          - Run format only")
        return

    command = sys.argv[1]

    if command == "all":
        # Run format only
        success = run_command(commands["format"][0], commands["format"][1])

        if success:
            print("\n🎉 All checks passed!")
        else:
            print("\n❌ Some checks failed!")
            sys.exit(1)

    elif command in commands:
        cmd, desc = commands[command]
        success = run_command(cmd, desc)
        if not success:
            sys.exit(1)
    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
