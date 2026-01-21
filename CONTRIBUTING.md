# Contributing to DupliCleaner

Thank you for your interest in contributing to DupliCleaner! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Submitting Changes](#submitting-changes)
- [Style Guidelines](#style-guidelines)
- [Testing](#testing)
- [Documentation](#documentation)

## Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

## Getting Started

### Finding Something to Work On

- Check the [Issues](https://github.com/xrmech/duplicleaner/issues) page for open tasks
- Look for issues labeled `good first issue` for beginner-friendly tasks
- Look for issues labeled `help wanted` for tasks where we need assistance
- Feel free to ask questions on any issue before starting work

### Reporting Bugs

Before reporting a bug:
1. Search existing issues to avoid duplicates
2. Try to reproduce the bug with the latest version
3. Collect relevant information (OS version, Python version, error messages)

When reporting:
- Use the bug report template
- Include steps to reproduce
- Include expected vs actual behavior
- Attach logs if available (Settings > Logging > Export Logs)

### Requesting Features

- Use the feature request template
- Describe the use case and problem being solved
- Consider how it fits with existing features
- Be open to discussion about implementation approaches

## Development Setup

### Prerequisites

- Windows 10 or later
- Python 3.11 or later
- Git
- NVIDIA GPU (optional, for AI features)

### Setting Up the Development Environment

```bash
# Clone the repository
git clone https://github.com/xrmech/duplicleaner.git
cd duplicleaner

# Create a virtual environment
python -m venv venv
venv\Scripts\activate

# Install development dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Verify setup by running tests
pytest
```

### Project Structure

```
duplicleaner/
├── src/duplicleaner/    # Main source code
│   ├── core/            # Core functionality (scanner, hasher, etc.)
│   ├── ai/              # AI/ML modules (faces, scenes, etc.)
│   ├── db/              # Database layer
│   ├── ui/              # User interface
│   └── utils/           # Utilities and helpers
├── tests/               # Test files (mirrors src structure)
├── docs/                # Documentation
└── resources/           # Static assets
```

## Making Changes

### Branching Strategy

- `main` - Stable release branch
- `develop` - Integration branch for features
- `feature/*` - Feature branches
- `bugfix/*` - Bug fix branches
- `hotfix/*` - Urgent fixes for production

### Creating a Branch

```bash
# Update your local develop branch
git checkout develop
git pull origin develop

# Create a feature branch
git checkout -b feature/your-feature-name
```

### Commit Messages

Follow conventional commit format:

```
type(scope): short description

Longer description if needed.

Fixes #123
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation changes
- `style` - Code style changes (formatting, etc.)
- `refactor` - Code refactoring
- `test` - Adding or updating tests
- `chore` - Maintenance tasks

**Examples:**
```
feat(scanner): add support for symbolic link following
fix(hasher): handle files larger than 4GB correctly
docs(readme): update installation instructions
test(comparator): add tests for near-duplicate detection
```

### Keep Changes Focused

- One feature or fix per pull request
- Keep PRs reasonably sized (under 500 lines if possible)
- Split large features into multiple PRs when sensible

## Submitting Changes

### Before Submitting

1. **Run tests**: `pytest`
2. **Check types**: `mypy src/`
3. **Check linting**: `ruff check src/`
4. **Format code**: `black src/ tests/`
5. **Update documentation** if needed

### Pull Request Process

1. Push your branch to your fork
2. Open a pull request against `develop`
3. Fill out the PR template completely
4. Wait for CI checks to pass
5. Request review from maintainers
6. Address any feedback
7. Once approved, a maintainer will merge

### PR Title Format

Follow the same format as commit messages:
```
feat(scanner): add UNC path validation
```

## Style Guidelines

### Python Style

- Follow [PEP 8](https://pep8.org/)
- Use [Black](https://black.readthedocs.io/) for formatting (line length: 100)
- Use [Ruff](https://docs.astral.sh/ruff/) for linting
- Use type hints for all public functions

### Code Example

```python
from pathlib import Path
from typing import Optional

def compute_file_hash(
    file_path: Path,
    algorithm: str = "sha256",
    chunk_size: int = 65536,
) -> Optional[str]:
    """
    Compute the hash of a file.

    Args:
        file_path: Path to the file to hash.
        algorithm: Hash algorithm to use (default: sha256).
        chunk_size: Size of chunks to read (default: 64KB).

    Returns:
        Hexadecimal hash string, or None if file cannot be read.

    Raises:
        ValueError: If algorithm is not supported.
    """
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise ValueError(f"Unsupported algorithm: {algorithm}")

    try:
        hasher = hashlib.new(algorithm)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError:
        return None
```

### Documentation Style

- Use Google-style docstrings
- Document all public classes, methods, and functions
- Keep docstrings up to date with code changes
- Include examples for complex functionality

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_hasher.py

# Run specific test function
pytest tests/test_hasher.py::test_sha256_hash

# Run with coverage
pytest --cov=duplicleaner --cov-report=html
```

### Writing Tests

- Place tests in `tests/` mirroring the source structure
- Name test files `test_*.py`
- Name test functions `test_*`
- Use pytest fixtures for common setup
- Aim for high coverage on core modules

### Test Example

```python
import pytest
from pathlib import Path
from duplicleaner.core.hasher import compute_file_hash

class TestComputeFileHash:
    """Tests for the compute_file_hash function."""

    def test_sha256_hash(self, tmp_path: Path) -> None:
        """Test SHA-256 hash computation."""
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"

        # Act
        result = compute_file_hash(test_file, algorithm="sha256")

        # Assert
        assert result == expected

    def test_nonexistent_file_returns_none(self, tmp_path: Path) -> None:
        """Test that nonexistent files return None."""
        result = compute_file_hash(tmp_path / "nonexistent.txt")
        assert result is None

    def test_invalid_algorithm_raises(self, tmp_path: Path) -> None:
        """Test that invalid algorithms raise ValueError."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        with pytest.raises(ValueError, match="Unsupported algorithm"):
            compute_file_hash(test_file, algorithm="invalid")
```

## Documentation

### Updating Documentation

- Update `docs/*.md` when changing features
- Keep the README current
- Add docstrings for new code
- Update CHANGELOG.md for notable changes

### Documentation Rule

**Documentation must match implementation.** When code changes deviate from documentation, update the docs immediately. Never leave documentation out of sync with reality.

## Questions?

If you have questions about contributing:

1. Check existing documentation
2. Search closed issues and PRs
3. Open a new issue with the `question` label

Thank you for contributing to DupliCleaner!

---

*XRMech Solutions LLC*
