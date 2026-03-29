"""
Static analysis tests for JavaScript / HTML integrity.

Catches two classes of bugs before they reach production:

1. HTML on* event handlers calling JS functions that don't exist
   (e.g. the seekTo() vs seekMainPlayer() incident)

2. JS getElementById() calls referencing HTML element IDs that don't exist
   (e.g. btn-scan missing from the template)
"""

import re
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
_JS_DIR = _ROOT / "static" / "js"
_TMPL_DIR = _ROOT / "templates"

# JS keywords that look like function calls in regex but aren't user-defined
_JS_KEYWORDS = frozenset(
    {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "return",
        "typeof",
        "instanceof",
        "new",
        "delete",
        "void",
        "throw",
        "await",
        "yield",
    }
)

# Browser/runtime globals not defined in our JS files
_BROWSER_GLOBALS = frozenset(
    {
        "alert",
        "confirm",
        "prompt",
        "console",
        "setTimeout",
        "clearTimeout",
        "setInterval",
        "clearInterval",
        "fetch",
        "encodeURIComponent",
        "decodeURIComponent",
        "parseInt",
        "parseFloat",
        "isNaN",
        "Boolean",
        "String",
        "Number",
        "Object",
        "Array",
        "JSON",
        "Math",
        "Date",
        "Error",
    }
)

# IDs that are created dynamically at runtime (innerHTML / createElement),
# so they won't appear as id="..." literals in the HTML templates.
# Add a comment explaining WHY each one is dynamic.
_DYNAMIC_IDS = frozenset(
    {
        # renderPagination() / jumpToPage() build the pager row with innerHTML
        "page-jump-input",
        # loadStats() populates #sidebar-status with these spans via innerHTML
        "sb-stat-total",
        "sb-stat-pending",
        "sb-stat-queued",
        "sb-stat-processing",
        "sb-stat-completed",
        "sb-stat-failed",
        "sb-stat-due",
        # _ensureAriaAnnouncer() creates the element itself if absent
        "aria-announcer",
    }
)


# ── helpers ───────────────────────────────────────────────────────────────────


def _defined_js_functions() -> set[str]:
    """Return all function names defined in static/js/*.js and in <script>
    blocks inside HTML templates."""
    defined: set[str] = set()

    sources: list[str] = []
    for p in _JS_DIR.glob("*.js"):
        sources.append(p.read_text(encoding="utf-8"))
    for p in _TMPL_DIR.glob("*.html"):
        # extract inline <script> blocks
        for block in re.findall(
            r"<script[^>]*>(.*?)</script>", p.read_text(encoding="utf-8"), re.DOTALL
        ):
            sources.append(block)

    for src in sources:
        # function foo(  /  async function foo(
        defined |= set(re.findall(r"\bfunction\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(", src))
        # const/let/var foo = (async)? function|arrow
        defined |= set(
            re.findall(
                r"\b(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s+)?(?:function\b|\()",
                src,
            )
        )
        # window.foo = ...
        defined |= set(re.findall(r"\bwindow\.([A-Za-z_$][A-Za-z0-9_$]*)\s*=", src))

    return defined


def _html_handler_calls() -> dict[str, list[str]]:
    """Return {fn_name: [template_filenames]} for every function call found
    in an inline on* event attribute across all HTML templates."""
    calls: dict[str, list[str]] = {}
    pattern = re.compile(r'\bon\w+="([A-Za-z_$][A-Za-z0-9_$]*)\s*\(', re.IGNORECASE)
    for p in _TMPL_DIR.glob("*.html"):
        for fn in pattern.findall(p.read_text(encoding="utf-8")):
            if fn in _JS_KEYWORDS:
                continue
            calls.setdefault(fn, []).append(p.name)
    return calls


def _html_defined_ids() -> set[str]:
    """Return all id="..." values present in HTML templates."""
    ids: set[str] = set()
    for p in _TMPL_DIR.glob("*.html"):
        ids |= set(re.findall(r'\bid=["\']([^"\']+)["\']', p.read_text(encoding="utf-8")))
    return ids


def _js_get_element_by_id_calls() -> dict[str, list[str]]:
    """Return {id_value: [js_filenames]} for every simple-string-literal
    getElementById() call in static/js/*.js files."""
    calls: dict[str, list[str]] = {}
    pattern = re.compile(r'getElementById\(["\']([^"\']+)["\']\)')
    for p in _JS_DIR.glob("*.js"):
        for id_val in pattern.findall(p.read_text(encoding="utf-8")):
            calls.setdefault(id_val, []).append(p.name)
    return calls


def _js_template_handler_calls() -> dict[str, list[str]]:
    """Extract function names from on* event handlers that are embedded inside
    JS template-literal strings (e.g. onclick="seekTo(${sec})").

    These are injected into the DOM at runtime so static HTML scanning won't
    catch them, but the called function still needs to be defined.
    """
    calls: dict[str, list[str]] = {}
    # Match onclick="funcName(" inside JS source (single or double quotes, backtick strings)
    pattern = re.compile(r'\bon\w+=["\'\`]([A-Za-z_$][A-Za-z0-9_$]*)\s*\(', re.IGNORECASE)
    for p in _JS_DIR.glob("*.js"):
        for fn in pattern.findall(p.read_text(encoding="utf-8")):
            if fn in _JS_KEYWORDS:
                continue
            calls.setdefault(fn, []).append(p.name)
    return calls


# ── tests ─────────────────────────────────────────────────────────────────────


def test_js_template_handlers_reference_defined_functions():
    """Functions called in on* attributes inside JS template-literal strings
    must be defined in a JS file.

    This test would have caught the seekTo() / seekMainPlayer() incident where
    the onclick was generated dynamically by renderTranscript() in detail.js.
    """
    defined = _defined_js_functions()
    template_calls = _js_template_handler_calls()

    missing = {
        fn: sorted(set(files))
        for fn, files in template_calls.items()
        if fn not in defined and fn not in _BROWSER_GLOBALS
    }

    assert not missing, (
        "JS template strings contain on* handlers calling undefined functions:\n"
        + "\n".join(f"  {fn}()  (in: {', '.join(files)})" for fn, files in sorted(missing.items()))
    )

    """Every function called in an HTML on* attribute must be defined in a
    JS file (or in an inline <script> block of a template).

    This test would have caught the seekTo() / seekMainPlayer() incident.
    """
    defined = _defined_js_functions()
    handler_calls = _html_handler_calls()

    missing = {
        fn: sorted(set(files))
        for fn, files in handler_calls.items()
        if fn not in defined and fn not in _BROWSER_GLOBALS
    }

    assert not missing, (
        "HTML on* event handlers call functions NOT defined in any JS file:\n"
        + "\n".join(
            f"  {fn}()  (referenced in: {', '.join(files)})"
            for fn, files in sorted(missing.items())
        )
    )


def test_js_getElementById_references_exist_in_html():
    """Every simple-string getElementById('id') call in static JS must
    correspond to an id="..." attribute in at least one HTML template,
    or be listed in _DYNAMIC_IDS (created at runtime).

    This test would have caught the missing btn-scan element incident.
    """
    html_ids = _html_defined_ids()
    js_calls = _js_get_element_by_id_calls()

    missing = {
        id_val: sorted(set(files))
        for id_val, files in js_calls.items()
        if id_val not in html_ids and id_val not in _DYNAMIC_IDS
    }

    assert not missing, (
        "JS getElementById() calls reference IDs not found in any HTML template\n"
        "(add to _DYNAMIC_IDS if the element is created at runtime):\n"
        + "\n".join(
            f"  #{id_val}  (in: {', '.join(files)})" for id_val, files in sorted(missing.items())
        )
    )
