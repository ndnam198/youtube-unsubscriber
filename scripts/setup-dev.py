#!/usr/bin/env python3
"""
Development environment setup script for YouTube Unsubscriber.
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd, description, check=True):
    """Run a command and handle errors."""
    print(f"\n🔧 {description}...")
    try:
        result = subprocess.run(
            cmd, shell=True, check=check, capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"✅ {description} completed successfully")
        else:
            print(f"⚠️ {description} completed with warnings")

        if result.stdout:
            print(result.stdout)
        if result.stderr and result.returncode != 0:
            print("STDERR:", result.stderr)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False


def main():
    """Setup development environment."""
    project_root = Path(__file__).parent.parent

    print("🚀 YouTube Unsubscriber Development Setup")
    print("=" * 50)

    # Change to project root
    import os

    os.chdir(project_root)

    # Check Python version
    print("\n🐍 Checking Python version...")
    result = subprocess.run(
        "uv run python --version", shell=True, capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"✅ {result.stdout.strip()}")
    else:
        print("❌ Failed to get Python version")
        return False

    # Install dev dependencies
    success = True
    success &= run_command("uv sync --dev", "Installing development dependencies")

    # Install pre-commit hooks
    success &= run_command("uv run pre-commit install", "Installing pre-commit hooks")

    # Test configuration files
    success &= run_command(
        "uv run black --config=.black --check src/", "Testing Black configuration"
    )

    success &= run_command(
        "uv run pylint --rcfile=.pylintrc --version", "Testing Pylint configuration"
    )

    # Run initial formatting
    success &= run_command(
        "uv run black --config=.black src/", "Running initial code formatting"
    )

    if success:
        print("\n🎉 Development environment setup complete!")
        print("\n📋 Available commands:")
        print("  python scripts/lint.py format    - Format code")
        print("  python scripts/lint.py check     - Check formatting")
        print("  python scripts/lint.py lint      - Run linting")
        print("  python scripts/lint.py all       - Run all checks")
        print("  uv run pre-commit run --all-files - Run pre-commit on all files")
        print("\n💡 Pre-commit hooks will automatically run on git commit!")
    else:
        print("\n❌ Some setup steps failed. Please check the errors above.")
        return False

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
