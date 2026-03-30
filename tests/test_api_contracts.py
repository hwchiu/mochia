"""
API contract tests: verify that callers and callees agree on function signatures.

This catches the class of bug where a service function's return signature is
changed (e.g. analyze_all 6-tuple → 5-tuple) but a caller (e.g. worker.py) is
not updated to match.

Root-cause post-mortem (PR #36 / PR #38):
- analyze_all() was changed from 6-tuple to 5-tuple (mindmap removed)
- app/routers/analysis.py was updated correctly
- worker.py was NOT updated → ValueError in production
- mypy missed it because CI ran `mypy app/` — worker.py is at root level
- test_worker.py missed it because it mocked analyze_all's return value directly,
  decoupling the test from the real signature

These tests use AST/source inspection to enforce callers match the declared
return type, providing a safety net independent of mock-level unit tests.
"""

import ast
from pathlib import Path
from typing import get_type_hints

import pytest

_ROOT = Path(__file__).parent.parent


# ── helpers ───────────────────────────────────────────────────────────────────


def _count_tuple_elements(annotation: type) -> int | None:
    """Return the number of elements in a fixed-length tuple annotation, or None."""
    args = getattr(annotation, "__args__", None)
    if args is None:
        return None
    # tuple[X, Y, Z] → 3 elements
    # tuple[X, ...] → variable length, return None
    if len(args) == 2 and args[-1] is type(Ellipsis):
        return None
    return len(args)


def _find_unpack_counts(source: str, func_name: str) -> list[tuple[int, int]]:
    """
    Parse `source` and return (line_no, var_count) for every line that does:
        a, b, c = func_name(...)
    """
    tree = ast.parse(source)
    results: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        # RHS must be a Call to func_name
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        called = (
            func.id
            if isinstance(func, ast.Name)
            else (func.attr if isinstance(func, ast.Attribute) else None)
        )
        if called != func_name:
            continue
        # LHS must be a Tuple unpack
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Tuple):
            continue
        var_count = len(node.targets[0].elts)
        results.append((node.lineno, var_count))
    return results


# ── analyze_all contract ──────────────────────────────────────────────────────


class TestAnalyzeAllContract:
    """
    Every file that calls analyze_all() must unpack exactly as many variables
    as analyze_all() declares in its return-type annotation.

    If analyze_all's signature changes, update the annotation and ALL callers —
    this test will catch any missed callers at CI time.
    """

    def _expected_arity(self) -> int:
        from app.services.analyzer import analyze_all

        hints = get_type_hints(analyze_all)
        ret = hints.get("return")
        assert ret is not None, "analyze_all must have a return type annotation"
        count = _count_tuple_elements(ret)
        assert count is not None, "analyze_all return type must be a fixed-length tuple"
        return count

    def test_analyze_all_return_annotation_is_fixed_tuple(self) -> None:
        """analyze_all must declare a fixed-length tuple return type (not variadic)."""
        arity = self._expected_arity()
        assert arity > 0, "analyze_all must return at least one value"

    @pytest.mark.parametrize(
        "path",
        [
            _ROOT / "worker.py",
            _ROOT / "app" / "routers" / "analysis.py",
        ],
    )
    def test_callers_unpack_correct_number_of_values(self, path: Path) -> None:
        """Every tuple-unpack of analyze_all() must match the declared return arity."""
        expected = self._expected_arity()
        source = path.read_text()
        unpacks = _find_unpack_counts(source, "analyze_all")

        # The file might not call analyze_all at all — that's fine
        if not unpacks:
            pytest.skip(f"{path.name} does not call analyze_all()")

        for line_no, count in unpacks:
            assert count == expected, (
                f"{path.name}:{line_no} unpacks {count} values from analyze_all() "
                f"but the function declares {expected} return values.\n"
                f"Update the unpack to match analyze_all's return type annotation."
            )
