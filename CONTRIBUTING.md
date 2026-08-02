# Contributing to PyBase

Thank you for your interest in contributing to PyBase.

PyBase is an educational relational database engine built from scratch in Python. The goal of the project is to implement real database internals while keeping the codebase clean, well documented, and easy to understand.

## Before You Start

Before opening a pull request, please:

- Check existing issues to avoid duplicate work.
- Open an issue for large features or architectural changes before implementing them.
- Keep pull requests focused on a single change whenever possible.

## Development Setup

Clone the repository:

```bash
git clone https://github.com/JOSIAHTHEPROGRAMMER/pybase.git
cd pybase
```

Install dependencies:

```bash
pip install PyQt6 matplotlib pytest pytest-cov pytest-qt
```

Run the test suite:

```bash
pytest tests/ -v -s
```

Launch the CLI:

```bash
python cli.py
```

Launch the GUI:

```bash
python -m gui.main
```

## Code Style

Please follow these guidelines when contributing:

- Follow existing project structure and naming conventions.
- Keep functions focused on a single responsibility.
- Write clear, descriptive variable names.
- Avoid unnecessary abstractions.
- Prefer readability over clever code.
- Add comments only when they explain *why*, not *what*.
- Preserve the existing architecture whenever possible.

## Testing

All new functionality should include appropriate tests.

Before submitting a pull request:

- Ensure all existing tests pass.
- Add tests for new features.
- Update existing tests if behavior changes.

## Documentation

If your contribution changes behavior or introduces new functionality, update the relevant documentation, including:

- README.md
- SQL examples
- Architecture documentation
- Inline comments where appropriate

## Pull Requests

When submitting a pull request:

- Provide a clear description of the change.
- Explain the motivation behind it.
- Reference any related issues.
- Keep commits focused and meaningful.

## Reporting Bugs

When reporting a bug, please include:

- Python version
- Operating system
- Steps to reproduce
- Expected behavior
- Actual behavior
- Relevant error messages or stack traces

## Feature Requests

Feature requests are welcome. Please explain:

- The problem being solved.
- The proposed solution.
- Why it would improve PyBase.

## Questions

If you are unsure about an implementation or design decision, open an issue before beginning work. Discussion is encouraged, especially for changes affecting the storage engine, SQL parser, query execution, transactions, or indexing.

Thank you for helping improve PyBase.
