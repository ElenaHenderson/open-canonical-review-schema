# Contributing to OCRS

Thank you for your interest in contributing to the Open Canonical Review Schema (OCRS)! This document provides guidelines for contributing.

## Contributor License Agreement

Before your contribution can be accepted, you must consent to our [Contributor License Agreement (CLA)](CLA.md). This ensures that Valency Systems Inc. can use and distribute your contributions under the project's Apache License 2.0.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Set up the development environment:

```bash
uv sync
uv run prek install  # Install pre-commit hooks
```

## Development Workflow

### Running Tests

```bash
uv run pytest -q
```

### Linting and Formatting

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
uv run ruff check .      # Check for issues
uv run ruff check --fix . # Auto-fix issues
uv run ruff format .     # Format code
```

### Pre-commit Hooks

Run hooks manually on all files:

```bash
uv run prek run --all-files
```

## Making Changes

### Code Style

- Follow PEP 8 conventions
- Use type hints for function signatures
- Keep functions focused and well-documented
- Add tests for new functionality

### Schema Changes

When modifying the JSON schema (`src/ocrs/schemas/canonical-review.schema.json`):

1. Ensure backwards compatibility when possible
2. Update the version number if making breaking changes
3. Add tests that exercise the new schema elements
4. Update mappers if they need to handle new fields

### Adding a New Mapper

To add support for a new source format:

1. Create a new file in `src/ocrs/mappers/` (e.g., `newformat.py`)
2. Implement `from_newformat(payload, keep_raw=False)` and `to_newformat(canonical)`
3. Register the mapper in `src/ocrs/registry.py`
4. Add tests in `tests/test_roundtrip.py`

### AI Reviewer Mappers

An AI reviewer mapper belongs in OCRS only if the reviewer's output format is public, as
OpenAIReview's is.

A mapper takes the reviewer's output, the review envelope that `map_with_record` built from its
keyword arguments, and the paper's blocks (or `None`). It fills the envelope through a
`Recorder` and returns `finish(...)`, both from `ocrs.mappers.ai`. Add it and its version to
`_FROM_WITH_RECORD` and `_MAPPER_VERSIONS` in `src/ocrs/registry.py`, and its tests to
`tests/test_ai_mappers.py`. See `src/ocrs/mappers/openaireview.py` for a complete mapper.

The mapper copies the reviewer's text and never rewrites or invents it. `Recorder.copy` copies
a value, `Recorder.lookup` maps it through a table and records a coercion when the value is
not in it, and `Recorder.evidence_link` copies a quote and, given the paper, records where it
was found. `finish` keeps whatever the mapper did not read in `extensions.<name>`, validates
the review, and records the gaps.

## Submitting Changes

1. Create a feature branch from `main`
2. Make your changes with clear commit messages
3. Ensure all tests pass and linting is clean
4. Push to your fork and open a pull request

### Pull Request Guidelines

- Provide a clear description of the changes
- Reference any related issues
- Ensure CI checks pass
- Be responsive to review feedback

## Reporting Issues

When reporting bugs:

- Include Python version and OS
- Provide a minimal reproducible example
- Include the full error traceback

For feature requests:

- Explain the use case
- Describe the expected behavior
- Consider how it fits with existing functionality

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

## Questions?

Open an issue for questions about contributing or the project architecture.
