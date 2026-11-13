"""Bounded, non-executing parsers for Python and Tree-sitter JS/TS sources."""
from __future__ import annotations

import ast
from pathlib import PurePosixPath

try:
    from tree_sitter_language_pack import get_parser
except ImportError:  # Python analysis remains available in minimal installs.
    get_parser = None

PARSER_VERSION = "stage3-v1"
MAX_FILE_BYTES = 512_000
SUPPORTED = {".py": "python", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "tsx"}


def _py(path: str, source: str) -> dict:
    out = {"symbols": [], "imports": [], "exports": [], "routes": [], "errors": []}
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError) as exc:
        out["errors"].append({"message": str(exc)[:300], "line": getattr(exc, "lineno", None)})
        return out
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            out["symbols"].append({"name": node.name, "type": kind, "start": node.lineno, "end": getattr(node, "end_lineno", node.lineno), "parameters": [arg.arg for arg in node.args.args] if kind == "function" else [], "visibility": "private" if node.name.startswith("_") else "public", "extras": {"bases": [ast.unparse(b) for b in node.bases] if kind == "class" else []}})
            if kind == "function":
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr.lower() in {"get", "post", "put", "patch", "delete", "route"} and decorator.args and isinstance(decorator.args[0], ast.Constant) and isinstance(decorator.args[0].value, str):
                        out["routes"].append({"method": decorator.func.attr.upper(), "route": decorator.args[0].value, "handler": node.name, "line": decorator.lineno})
            if node.name.startswith("__") and node.name.endswith("__") and node.name in {"__main__"}:
                out["routes"].append({"method": "MAIN", "route": "__main__", "handler": node.name, "line": node.lineno})
        elif isinstance(node, ast.Import):
            out["imports"].extend({"module": a.name, "symbols": [], "line": node.lineno, "type": "import"} for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mod = "." * node.level + (node.module or "")
            out["imports"].append({"module": mod, "symbols": [a.name for a in node.names], "line": node.lineno, "type": "import"})
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr in {"get", "post", "put", "patch", "delete", "route"}:
                route = next((ast.literal_eval(a) for a in value.args if isinstance(a, (ast.Constant, ast.Str)) and isinstance(getattr(a, "value", None), str)), None)
                if route:
                    name = next((t.id for t in targets if isinstance(t, ast.Name)), "route")
                    out["routes"].append({"method": value.func.attr.upper(), "route": route, "handler": name, "line": node.lineno})
    out["exports"] = [{"name": n.name, "type": "export", "line": n.lineno} for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not n.name.startswith("_")]
    return out


def _ts(path: str, source: str, language: str) -> dict:
    out = {"symbols": [], "imports": [], "exports": [], "routes": [], "errors": []}
    if get_parser is None:
        out["errors"].append({"message": "Tree-sitter grammar package is not installed", "line": None})
        return out
    parser = get_parser(language)
    tree = parser.parse(source.encode("utf-8", errors="replace"))
    root = tree.root_node
    if root.has_error:
        out["errors"].append({"message": "Tree-sitter recovered from syntax errors", "line": None})
    def text(node):
        return source.encode("utf-8", errors="replace")[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
    def visit(node, exported=False):
        is_export = exported or node.type == "export_statement"
        if node.type in {"import_statement", "export_statement"}:
            src = node.child_by_field_name("source")
            if src:
                spec = text(src).strip("'\"` ")
                if node.type == "import_statement":
                    out["imports"].append({"module": spec, "symbols": [], "line": node.start_point.row + 1, "type": "import"})
                else:
                    out["exports"].append({"name": text(node), "type": "re-export" if spec else "export", "line": node.start_point.row + 1, "source": spec or None})
        kinds = {"function_declaration": "function", "function_expression": "function", "method_definition": "method", "class_declaration": "class", "abstract_class_declaration": "class", "interface_declaration": "interface", "type_alias_declaration": "type", "lexical_declaration": "variable"}
        kind = kinds.get(node.type)
        name_node = node.child_by_field_name("name")
        if kind and name_node:
            name = text(name_node)
            params = node.child_by_field_name("parameters")
            out["symbols"].append({"name": name, "type": kind, "start": node.start_point.row + 1, "end": node.end_point.row + 1, "parameters": [text(c) for c in params.named_children] if params else [], "visibility": "public" if is_export or not name.startswith("_") else "private", "extras": {"exported": is_export}})
            if is_export:
                out["exports"].append({"name": name, "type": "export", "line": node.start_point.row + 1})
        for child in node.named_children:
            visit(child, is_export)
    visit(root)
    return out


def parse_source(path: str, content: str) -> dict:
    ext = PurePosixPath(path).suffix.lower()
    if len(content.encode("utf-8", errors="replace")) > MAX_FILE_BYTES:
        return {"symbols": [], "imports": [], "exports": [], "routes": [], "errors": [{"message": "File exceeds parser size limit", "line": None}]}
    try:
        if ext == ".py":
            return _py(path, content)
        language = SUPPORTED.get(ext)
        return _ts(path, content, language) if language else {"symbols": [], "imports": [], "exports": [], "routes": [], "errors": [{"message": "Unsupported parser language", "line": None}]}
    except Exception as exc:
        return {"symbols": [], "imports": [], "exports": [], "routes": [], "errors": [{"message": f"Parser adapter error: {type(exc).__name__}", "line": None}]}
