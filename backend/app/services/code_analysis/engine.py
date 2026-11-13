"""Pure analysis functions. They only inspect captured text; repository code is never run."""
from __future__ import annotations

import posixpath
from collections import Counter, defaultdict
from pathlib import PurePosixPath

from app.services.code_analysis.framework_detector import detect_technologies
from app.services.code_analysis.language_detector import EXTENSION_MAP, detect_languages
from app.services.code_analysis.parser import SUPPORTED, parse_source

MANIFESTS = {"package.json", "requirements.txt", "pyproject.toml", "pipfile", "cargo.toml", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "composer.json"}
SKIP_DIRS = {"node_modules", "vendor", "dist", "build", "coverage", ".git", "__pycache__", "target", "generated"}


def analyze_files(files: list[dict], contents: dict[str, str], github_languages: dict[str, int] | None = None) -> dict:
    tree, symbols, imports, routes, entry_points, errors = [], [], [], [], [], []
    dirs: set[str] = set()
    stats: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    excluded = lambda p: bool(SKIP_DIRS.intersection(PurePosixPath(p).parts[:-1]))
    category_counts = Counter()
    for f in files:
        path = f["path"].strip("/")
        if not path:
            continue
        parts = PurePosixPath(path).parts
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))
        content = contents.get(path)
        ext = (f.get("extension") or PurePosixPath(path).suffix).lower()
        language = EXTENSION_MAP.get(ext)
        avail = content is not None
        category = "documentation" if ext in {".md", ".mdx", ".rst"} else "configuration" if PurePosixPath(path).name.lower() in MANIFESTS or PurePosixPath(path).name.lower().startswith(("dockerfile", ".env.example")) else "source" if language else "other"
        category_counts[category] += 1
        tree.append({"node_id": path, "parent_id": "/".join(parts[:-1]) or None, "name": parts[-1], "path": path, "node_type": "file", "extension": ext, "size": int(f.get("size") or (len(content.encode()) if content else 0)), "language": language, "content_available": avail, "analysis_status": "parsed" if avail and ext in SUPPORTED else "available_unparsed" if avail else (f.get("analysis_status") or "skipped")})
        for i in range(1, len(parts)):
            d = "/".join(parts[:i])
            if not any(n["node_id"] == d for n in tree):
                tree.append({"node_id": d, "parent_id": "/".join(parts[:i-1]) or None, "name": parts[i-1], "path": d, "node_type": "directory", "extension": "", "size": 0, "language": None, "content_available": False, "analysis_status": "directory"})
        if language and not excluded(path):
            stats[language][0] += 1
            stats[language][1] += int(f.get("size") or (len(content.encode()) if content else 0))
        if not avail or excluded(path) or ext not in SUPPORTED:
            continue
        parsed = parse_source(path, content)
        errors.extend({"path": path, **e} for e in parsed["errors"])
        symbols.extend({"file_path": path, "language": language or "Unknown", **s} for s in parsed["symbols"])
        routes.extend({"file_path": path, **r} for r in parsed["routes"])
        imports.extend({"source_file": path, **imp} for imp in parsed["imports"])
        base = PurePosixPath(path).name.lower()
        if base in {"main.py", "app.py", "__main__.py", "index.js", "index.ts", "main.js", "main.ts", "main.tsx", "index.tsx"}:
            entry_points.append({"file_path": path, "runtime_or_framework": language, "detection_method": "conventional_filename", "confidence": "medium", "evidence": [f"filename: {base}"]})
        if any(s["name"] == "main" and s["type"] == "function" for s in parsed["symbols"]) and ext == ".py":
            entry_points.append({"file_path": path, "runtime_or_framework": "Python", "detection_method": "parsed_main_function", "confidence": "medium", "evidence": ["parsed function main"]})
    content_paths = set(contents)
    config_names = {"docker-compose.yml", "docker-compose.yaml", "dockerfile", "terraform.tf", "application.properties", "settings.py", "config.py", "tsconfig.json"}
    manifest_contents = {p: c for p, c in contents.items() if PurePosixPath(p).name.lower() in MANIFESTS or PurePosixPath(p).name.lower() in config_names or PurePosixPath(p).name.lower().startswith(".env") or PurePosixPath(p).suffix.lower() in {".yaml", ".yml", ".toml", ".ini", ".tf"}}
    technologies = detect_technologies(files, manifest_contents)
    source_tech = {
        "fastapi": ("FastAPI", "backend"), "django": ("Django", "backend"), "flask": ("Flask", "backend"),
        "react": ("React", "frontend"), "react-dom": ("React", "frontend"), "next": ("Next.js", "frontend"),
        "vue": ("Vue.js", "frontend"), "@angular/core": ("Angular", "frontend"), "express": ("Express.js", "backend"), "org.springframework": ("Spring Boot", "backend"), "spring": ("Spring Boot", "backend"),
        "@nestjs/common": ("NestJS", "backend"), "torch": ("PyTorch", "ai_ml"), "tensorflow": ("TensorFlow", "ai_ml"),
        "sklearn": ("Scikit-learn", "ai_ml"), "langchain": ("LangChain", "ai_ml"), "langgraph": ("LangGraph", "ai_ml"),
    }
    technology_names = {item["technology"] for item in technologies}
    for imp in imports:
        module = imp["module"].lower()
        key = "org.springframework" if module.startswith("org.springframework") else module.split(".", 1)[0]
        if key in source_tech and source_tech[key][0] not in technology_names:
            technology, category = source_tech[key]
            technology_names.add(technology)
            technologies.append({"technology": technology, "category": category, "version": None, "confidence": "medium", "detection_method": "parsed_import", "evidence_paths": [imp["source_file"]]})
    graph = []
    paths = {f["path"] for f in files}
    by_dir: dict[str, list[str]] = defaultdict(list)
    for path in paths:
        by_dir[str(PurePosixPath(path).parent)].append(path)
    for imp in imports:
        spec = imp["module"]
        resolved = None
        source = imp["source_file"]
        if spec.startswith("."):
            target = posixpath.normpath(posixpath.join(posixpath.dirname(source), spec))
            for candidate in (target, *(target + e for e in (".py", ".js", ".jsx", ".ts", ".tsx", ".mjs")), *(target + "/index" + e for e in (".js", ".jsx", ".ts", ".tsx")), target + "/__init__.py"):
                if candidate in paths:
                    resolved = candidate
                    break
        elif spec:
            # Python dotted imports can resolve against an exact module path.
            target = spec.replace(".", "/")
            for candidate in (target + ".py", target + "/__init__.py"):
                if candidate in paths:
                    resolved = candidate
                    break
        graph.append({"source_module": source, "target_module": resolved or spec, "relationship_type": "import", "source_file": source, "target_file": resolved, "line_number": imp["line"], "imported_symbols": imp["symbols"], "resolution_status": "resolved" if resolved else "unresolved"})
    # Architecture groups are only emitted when code/import evidence exists.
    groups: dict[str, list[str]] = defaultdict(list)
    for path in paths:
        parent = str(PurePosixPath(path).parent)
        if parent not in {"", "."} and path in contents and PurePosixPath(path).suffix.lower() in SUPPORTED:
            groups[parent].append(path)
    components = []
    for name, members in groups.items():
        edges = [e for e in graph if e["source_file"] in members or e["target_file"] in members]
        if not members or not (any(symbol["file_path"] in members for symbol in symbols) or edges):
            continue
        evidence = [f"parsed source files: {len(members)}"] + ([f"observed imports: {len(edges)}"] if edges else [])
        components.append({"component_name": name, "category": "observed_module_group", "file_paths": sorted(members)[:100], "connected_components": sorted({e["target_file"] or e["target_module"] for e in edges})[:50], "evidence": evidence, "confidence": "medium" if edges else "low", "inference_explanation": "Grouped by source path; imports are reported only when parsed."})
    detected = detect_languages([f for f in files if f["path"] in content_paths], github_languages=github_languages)
    unknown = sum(1 for f in files if EXTENSION_MAP.get((f.get("extension") or PurePosixPath(f["path"]).suffix).lower()) is None)
    return {"tree": tree, "directories": len(dirs), "files": len(files), "analysed_files": sum(1 for p in content_paths if p in paths), "skipped_files": sum(1 for f in files if f["path"] not in content_paths), "unknown_file_count": unknown, "category_counts": dict(category_counts), "languages": detected, "technologies": technologies, "symbols": symbols, "imports": graph, "routes": routes, "entry_points": entry_points, "components": components, "errors": errors}
