"""Language detection from file extensions and GitHub API data."""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import PurePosixPath

logger = logging.getLogger("continuum.code_analysis.language_detector")

# ── Extension → Language mapping (25+ languages) ────────────────────────────

EXTENSION_MAP: dict[str, str] = {
    ".py": "Python",
    ".pyi": "Python",
    ".pyx": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JSX",
    ".ts": "TypeScript",
    ".tsx": "TSX",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cxx": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".hxx": "C++",
    ".cs": "C#",
    ".php": "PHP",
    ".rb": "Ruby",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".swift": "Swift",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "SCSS",
    ".less": "Less",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".fish": "Shell",
    ".ps1": "PowerShell",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".jsonc": "JSON",
    ".md": "Markdown",
    ".mdx": "Markdown",
    ".rst": "reStructuredText",
    ".xml": "XML",
    ".toml": "TOML",
    ".ini": "INI",
    ".cfg": "INI",
    ".r": "R",
    ".R": "R",
    ".scala": "Scala",
    ".dart": "Dart",
    ".lua": "Lua",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hrl": "Erlang",
    ".hs": "Haskell",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".tf": "HCL",
    ".hcl": "HCL",
    ".proto": "Protocol Buffers",
    ".graphql": "GraphQL",
    ".gql": "GraphQL",
    ".sol": "Solidity",
    ".zig": "Zig",
    ".nim": "Nim",
    ".groovy": "Groovy",
    ".gradle": "Groovy",
    ".m": "Objective-C",
    ".mm": "Objective-C++",
    ".pl": "Perl",
    ".pm": "Perl",
}

# Directories to exclude (vendor/generated/build artefacts)
_EXCLUDED_DIRS = frozenset({
    "vendor", "node_modules", "dist", "build", ".build", "out",
    "generated", "__generated__", ".generated",
    "coverage", ".venv", "venv", "env",
    ".git", ".svn", ".hg",
    "__pycache__", ".tox", ".mypy_cache",
    "bower_components", "jspm_packages",
    "target",  # Maven/Cargo
    "bin", "obj",  # .NET
})


def _is_excluded(path: str) -> bool:
    """Return True when the file lives under an excluded directory."""
    parts = PurePosixPath(path).parts
    return any(p.lower() in _EXCLUDED_DIRS for p in parts[:-1])


def detect_languages(
    files: list[dict],
    *,
    github_languages: dict[str, int] | None = None,
) -> dict[str, list[dict]]:
    """Detect languages in a file list and optionally from GitHub API data.

    Parameters
    ----------
    files:
        Each dict has ``path``, ``extension``, and ``size`` (bytes).
    github_languages:
        Optional mapping of language name → byte count from the GitHub
        Languages API.

    Returns
    -------
    dict with keys ``"extension"`` and (if github_languages given) ``"github"``,
    each a sorted list of ``{language, file_count, total_bytes, percentage,
    detection_source, is_primary}`` dicts.
    """
    # ── Extension-based detection ────────────────────────────────────────
    lang_bytes: dict[str, int] = defaultdict(int)
    lang_count: dict[str, int] = defaultdict(int)

    for f in files:
        path: str = f.get("path", "")
        ext: str = f.get("extension", "").lower()
        size: int = f.get("size", 0)

        if _is_excluded(path):
            continue

        lang = EXTENSION_MAP.get(ext)
        if lang is None:
            continue

        lang_bytes[lang] += size
        lang_count[lang] += 1

    total_bytes = sum(lang_bytes.values()) or 1
    ext_results: list[dict] = []
    for lang in sorted(lang_bytes, key=lambda l: lang_bytes[l], reverse=True):
        ext_results.append({
            "language": lang,
            "file_count": lang_count[lang],
            "total_bytes": lang_bytes[lang],
            "percentage": round(lang_bytes[lang] / total_bytes * 100, 2),
            "detection_source": "extension",
            "is_primary": False,
        })

    if ext_results:
        ext_results[0]["is_primary"] = True

    result: dict[str, list[dict]] = {"extension": ext_results}

    # ── GitHub-based detection ───────────────────────────────────────────
    if github_languages:
        gh_total = sum(github_languages.values()) or 1
        gh_results: list[dict] = []
        for lang, byte_count in sorted(
            github_languages.items(), key=lambda kv: kv[1], reverse=True
        ):
            gh_results.append({
                "language": lang,
                "file_count": 0,  # GitHub API doesn't provide file counts
                "total_bytes": byte_count,
                "percentage": round(byte_count / gh_total * 100, 2),
                "detection_source": "github",
                "is_primary": False,
            })
        if gh_results:
            gh_results[0]["is_primary"] = True
        result["github"] = gh_results

    return result


def primary_language(detection_result: dict[str, list[dict]]) -> str | None:
    """Return the primary language name from a detection result, or None."""
    for source in ("extension", "github"):
        entries = detection_result.get(source, [])
        for entry in entries:
            if entry.get("is_primary"):
                return entry["language"]
    return None
