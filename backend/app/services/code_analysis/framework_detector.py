"""Technology / framework detection from manifest files and directory structure."""

from __future__ import annotations

import json
import logging
import re
from pathlib import PurePosixPath

logger = logging.getLogger("continuum.code_analysis.framework_detector")

# ── NPM dependency → technology rules ───────────────────────────────────────

_NPM_RULES: list[tuple[str, str, str]] = [
    # (package name or pattern, technology name, category)
    ("react", "React", "frontend"),
    ("react-dom", "React", "frontend"),
    ("next", "Next.js", "frontend"),
    ("vue", "Vue.js", "frontend"),
    ("nuxt", "Nuxt.js", "frontend"),
    ("@angular/core", "Angular", "frontend"),
    ("svelte", "Svelte", "frontend"),
    ("@sveltejs/kit", "SvelteKit", "frontend"),
    ("solid-js", "Solid.js", "frontend"),
    ("preact", "Preact", "frontend"),
    ("remix", "Remix", "frontend"),
    ("@remix-run/react", "Remix", "frontend"),
    ("gatsby", "Gatsby", "frontend"),
    ("astro", "Astro", "frontend"),
    ("vite", "Vite", "frontend"),
    ("webpack", "Webpack", "frontend"),
    ("esbuild", "esbuild", "frontend"),
    ("rollup", "Rollup", "frontend"),
    ("parcel", "Parcel", "frontend"),
    ("tailwindcss", "Tailwind CSS", "frontend"),
    ("bootstrap", "Bootstrap", "frontend"),
    ("@mui/material", "Material UI", "frontend"),
    ("@chakra-ui/react", "Chakra UI", "frontend"),
    ("styled-components", "styled-components", "frontend"),
    ("emotion", "Emotion", "frontend"),
    ("@emotion/react", "Emotion", "frontend"),
    ("redux", "Redux", "frontend"),
    ("zustand", "Zustand", "frontend"),
    ("mobx", "MobX", "frontend"),
    ("recoil", "Recoil", "frontend"),
    ("jotai", "Jotai", "frontend"),
    ("express", "Express.js", "backend"),
    ("fastify", "Fastify", "backend"),
    ("koa", "Koa", "backend"),
    ("hapi", "Hapi", "backend"),
    ("@nestjs/core", "NestJS", "backend"),
    ("@nestjs/common", "NestJS", "backend"),
    ("@trpc/server", "tRPC", "backend"),
    ("socket.io", "Socket.IO", "backend"),
    ("graphql", "GraphQL", "backend"),
    ("apollo-server", "Apollo Server", "backend"),
    ("prisma", "Prisma", "database"),
    ("@prisma/client", "Prisma", "database"),
    ("typeorm", "TypeORM", "database"),
    ("sequelize", "Sequelize", "database"),
    ("knex", "Knex.js", "database"),
    ("drizzle-orm", "Drizzle ORM", "database"),
    ("mongoose", "Mongoose", "database"),
    ("mongodb", "MongoDB", "database"),
    ("pg", "PostgreSQL", "database"),
    ("mysql2", "MySQL", "database"),
    ("redis", "Redis", "database"),
    ("ioredis", "Redis", "database"),
    ("jest", "Jest", "testing"),
    ("mocha", "Mocha", "testing"),
    ("vitest", "Vitest", "testing"),
    ("cypress", "Cypress", "testing"),
    ("playwright", "Playwright", "testing"),
    ("@testing-library/react", "React Testing Library", "testing"),
    ("storybook", "Storybook", "testing"),
    ("@storybook/react", "Storybook", "testing"),
    ("typescript", "TypeScript", "other"),
    ("electron", "Electron", "frontend"),
    ("react-native", "React Native", "frontend"),
    ("expo", "Expo", "frontend"),
    ("three", "Three.js", "frontend"),
    ("d3", "D3.js", "frontend"),
    ("chart.js", "Chart.js", "frontend"),
    ("langchain", "LangChain", "ai_ml"),
    ("openai", "OpenAI SDK", "ai_ml"),
    ("@google/generative-ai", "Google AI SDK", "ai_ml"),
]

# ── Python dependency → technology rules ────────────────────────────────────

_PYTHON_RULES: list[tuple[str, str, str]] = [
    ("fastapi", "FastAPI", "backend"),
    ("django", "Django", "backend"),
    ("flask", "Flask", "backend"),
    ("starlette", "Starlette", "backend"),
    ("tornado", "Tornado", "backend"),
    ("aiohttp", "aiohttp", "backend"),
    ("sanic", "Sanic", "backend"),
    ("litestar", "Litestar", "backend"),
    ("uvicorn", "Uvicorn", "infrastructure"),
    ("gunicorn", "Gunicorn", "infrastructure"),
    ("celery", "Celery", "infrastructure"),
    ("dramatiq", "Dramatiq", "infrastructure"),
    ("sqlalchemy", "SQLAlchemy", "database"),
    ("alembic", "Alembic", "database"),
    ("psycopg2", "PostgreSQL", "database"),
    ("psycopg", "PostgreSQL", "database"),
    ("asyncpg", "PostgreSQL", "database"),
    ("pymongo", "MongoDB", "database"),
    ("motor", "MongoDB", "database"),
    ("redis", "Redis", "database"),
    ("mysqlclient", "MySQL", "database"),
    ("tortoise-orm", "Tortoise ORM", "database"),
    ("peewee", "Peewee", "database"),
    ("pydantic", "Pydantic", "backend"),
    ("pytest", "pytest", "testing"),
    ("unittest", "unittest", "testing"),
    ("hypothesis", "Hypothesis", "testing"),
    ("torch", "PyTorch", "ai_ml"),
    ("pytorch", "PyTorch", "ai_ml"),
    ("tensorflow", "TensorFlow", "ai_ml"),
    ("keras", "Keras", "ai_ml"),
    ("scikit-learn", "scikit-learn", "ai_ml"),
    ("sklearn", "scikit-learn", "ai_ml"),
    ("transformers", "Hugging Face Transformers", "ai_ml"),
    ("langchain", "LangChain", "ai_ml"),
    ("langchain-core", "LangChain", "ai_ml"),
    ("openai", "OpenAI SDK", "ai_ml"),
    ("google-generativeai", "Google AI SDK", "ai_ml"),
    ("pandas", "pandas", "ai_ml"),
    ("numpy", "NumPy", "ai_ml"),
    ("scipy", "SciPy", "ai_ml"),
    ("matplotlib", "Matplotlib", "ai_ml"),
    ("plotly", "Plotly", "ai_ml"),
    ("streamlit", "Streamlit", "frontend"),
    ("gradio", "Gradio", "frontend"),
    ("dash", "Dash", "frontend"),
    ("jinja2", "Jinja2", "frontend"),
    ("requests", "Requests", "other"),
    ("httpx", "HTTPX", "other"),
    ("boto3", "AWS SDK", "infrastructure"),
    ("google-cloud-storage", "Google Cloud", "infrastructure"),
    ("docker", "Docker SDK", "infrastructure"),
]


def _parse_npm_deps(
    pkg: dict, evidence_path: str
) -> list[dict]:
    """Extract technology detections from a parsed package.json."""
    results: list[dict] = []
    seen: set[str] = set()

    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        deps = pkg.get(section, {})
        if not isinstance(deps, dict):
            continue
        for pkg_name, version in deps.items():
            for rule_pkg, tech, cat in _NPM_RULES:
                if pkg_name == rule_pkg and tech not in seen:
                    seen.add(tech)
                    results.append({
                        "technology": tech,
                        "category": cat,
                        "version": str(version) if version else None,
                        "confidence": "high",
                        "detection_method": f"package.json {section}",
                        "evidence_paths": [evidence_path],
                    })
    return results


def _parse_requirements_txt(content: str, evidence_path: str) -> list[dict]:
    """Extract technologies from requirements.txt content."""
    results: list[dict] = []
    seen: set[str] = set()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Parse: package==1.2.3, package>=1.0, package~=1.0, package
        match = re.match(r"^([A-Za-z0-9_][A-Za-z0-9._-]*)\s*([><=!~]+\s*\S+)?", line)
        if not match:
            continue
        pkg_name = match.group(1).lower().replace("_", "-")
        version = match.group(2).strip() if match.group(2) else None
        for rule_pkg, tech, cat in _PYTHON_RULES:
            if pkg_name == rule_pkg and tech not in seen:
                seen.add(tech)
                results.append({
                    "technology": tech,
                    "category": cat,
                    "version": version,
                    "confidence": "high",
                    "detection_method": "requirements.txt",
                    "evidence_paths": [evidence_path],
                })
    return results


def _parse_pyproject_toml(content: str, evidence_path: str) -> list[dict]:
    """Extract technologies from pyproject.toml content (regex, no toml lib dependency)."""
    results: list[dict] = []
    seen: set[str] = set()
    # Look for dependencies list inside [project] or [tool.poetry.dependencies]
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Match quoted dependency names: "fastapi>=0.100", 'django', {version = "..."}
        matches = re.findall(r'["\']([A-Za-z0-9_][A-Za-z0-9._-]*?)(?:[><=!~\["\'\s])', line)
        for raw in matches:
            pkg_name = raw.lower().replace("_", "-")
            for rule_pkg, tech, cat in _PYTHON_RULES:
                if pkg_name == rule_pkg and tech not in seen:
                    seen.add(tech)
                    # Try extracting version
                    version_match = re.search(
                        rf'{re.escape(raw)}\s*([><=!~]+\s*[\d][^\s"\']*)', line
                    )
                    results.append({
                        "technology": tech,
                        "category": cat,
                        "version": version_match.group(1).strip() if version_match else None,
                        "confidence": "high",
                        "detection_method": "pyproject.toml",
                        "evidence_paths": [evidence_path],
                    })
    return results


def _parse_cargo_toml(content: str, evidence_path: str) -> list[dict]:
    """Extract technologies from Cargo.toml."""
    results: list[dict] = []
    cargo_rules = [
        ("actix-web", "Actix Web", "backend"),
        ("axum", "Axum", "backend"),
        ("rocket", "Rocket", "backend"),
        ("warp", "Warp", "backend"),
        ("tokio", "Tokio", "infrastructure"),
        ("serde", "Serde", "other"),
        ("diesel", "Diesel", "database"),
        ("sqlx", "SQLx", "database"),
        ("sea-orm", "SeaORM", "database"),
        ("reqwest", "Reqwest", "other"),
        ("clap", "Clap", "other"),
        ("tonic", "Tonic (gRPC)", "backend"),
        ("leptos", "Leptos", "frontend"),
        ("yew", "Yew", "frontend"),
        ("tauri", "Tauri", "frontend"),
        ("bevy", "Bevy", "other"),
    ]
    seen: set[str] = set()
    for line in content.splitlines():
        for rule_pkg, tech, cat in cargo_rules:
            if re.search(rf'\b{re.escape(rule_pkg)}\b', line) and tech not in seen:
                seen.add(tech)
                version_match = re.search(r'version\s*=\s*"([^"]+)"', line) or re.search(r'=\s*"([^"]+)"', line)
                results.append({
                    "technology": tech,
                    "category": cat,
                    "version": version_match.group(1) if version_match else None,
                    "confidence": "high",
                    "detection_method": "Cargo.toml",
                    "evidence_paths": [evidence_path],
                })
    return results


def _parse_go_mod(content: str, evidence_path: str) -> list[dict]:
    """Extract technologies from go.mod."""
    results: list[dict] = []
    go_rules = [
        ("github.com/gin-gonic/gin", "Gin", "backend"),
        ("github.com/gofiber/fiber", "Fiber", "backend"),
        ("github.com/labstack/echo", "Echo", "backend"),
        ("github.com/gorilla/mux", "Gorilla Mux", "backend"),
        ("github.com/go-chi/chi", "Chi", "backend"),
        ("gorm.io/gorm", "GORM", "database"),
        ("github.com/jmoiron/sqlx", "sqlx", "database"),
        ("github.com/lib/pq", "PostgreSQL", "database"),
        ("go.mongodb.org/mongo-driver", "MongoDB", "database"),
        ("github.com/redis/go-redis", "Redis", "database"),
        ("github.com/go-redis/redis", "Redis", "database"),
        ("google.golang.org/grpc", "gRPC", "backend"),
        ("github.com/99designs/gqlgen", "gqlgen (GraphQL)", "backend"),
        ("github.com/stretchr/testify", "Testify", "testing"),
    ]
    seen: set[str] = set()
    for line in content.splitlines():
        for rule_mod, tech, cat in go_rules:
            if rule_mod in line and tech not in seen:
                seen.add(tech)
                version_match = re.search(r'v(\d+\.\d+\.\d+)', line)
                results.append({
                    "technology": tech,
                    "category": cat,
                    "version": version_match.group(0) if version_match else None,
                    "confidence": "high",
                    "detection_method": "go.mod",
                    "evidence_paths": [evidence_path],
                })
    return results


def _parse_pom_xml(content: str, evidence_path: str) -> list[dict]:
    """Extract technologies from pom.xml (Maven)."""
    results: list[dict] = []
    java_rules = [
        ("spring-boot", "Spring Boot", "backend"),
        ("spring-web", "Spring Web", "backend"),
        ("spring-data", "Spring Data", "database"),
        ("spring-security", "Spring Security", "backend"),
        ("quarkus", "Quarkus", "backend"),
        ("micronaut", "Micronaut", "backend"),
        ("hibernate", "Hibernate", "database"),
        ("mybatis", "MyBatis", "database"),
        ("junit", "JUnit", "testing"),
        ("mockito", "Mockito", "testing"),
        ("lombok", "Lombok", "other"),
        ("jackson", "Jackson", "other"),
        ("kafka", "Apache Kafka", "infrastructure"),
    ]
    seen: set[str] = set()
    for rule_art, tech, cat in java_rules:
        if rule_art in content.lower() and tech not in seen:
            seen.add(tech)
            results.append({
                "technology": tech,
                "category": cat,
                "version": None,
                "confidence": "high",
                "detection_method": "pom.xml",
                "evidence_paths": [evidence_path],
            })
    return results


def _parse_build_gradle(content: str, evidence_path: str) -> list[dict]:
    """Extract technologies from build.gradle."""
    results: list[dict] = []
    # Reuse same java rules
    java_rules = [
        ("spring-boot", "Spring Boot", "backend"),
        ("spring-web", "Spring Web", "backend"),
        ("spring-data", "Spring Data", "database"),
        ("spring-security", "Spring Security", "backend"),
        ("quarkus", "Quarkus", "backend"),
        ("micronaut", "Micronaut", "backend"),
        ("hibernate", "Hibernate", "database"),
        ("mybatis", "MyBatis", "database"),
        ("junit", "JUnit", "testing"),
        ("mockito", "Mockito", "testing"),
        ("lombok", "Lombok", "other"),
        ("jackson", "Jackson", "other"),
        ("kafka", "Apache Kafka", "infrastructure"),
        ("kotlin", "Kotlin", "other"),
        ("ktor", "Ktor", "backend"),
    ]
    seen: set[str] = set()
    for rule_art, tech, cat in java_rules:
        if rule_art in content.lower() and tech not in seen:
            seen.add(tech)
            results.append({
                "technology": tech,
                "category": cat,
                "version": None,
                "confidence": "high",
                "detection_method": "build.gradle",
                "evidence_paths": [evidence_path],
            })
    return results


def _parse_composer_json(content: str, evidence_path: str) -> list[dict]:
    """Extract technologies from composer.json (PHP)."""
    results: list[dict] = []
    php_rules = [
        ("laravel/framework", "Laravel", "backend"),
        ("symfony/", "Symfony", "backend"),
        ("slim/slim", "Slim", "backend"),
        ("doctrine/orm", "Doctrine ORM", "database"),
        ("phpunit/phpunit", "PHPUnit", "testing"),
        ("guzzlehttp/guzzle", "Guzzle", "other"),
        ("livewire/livewire", "Livewire", "frontend"),
    ]
    seen: set[str] = set()
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return results

    for section in ("require", "require-dev"):
        deps = data.get(section, {})
        if not isinstance(deps, dict):
            continue
        for pkg_name, version in deps.items():
            for rule_pkg, tech, cat in php_rules:
                if (pkg_name == rule_pkg or pkg_name.startswith(rule_pkg)) and tech not in seen:
                    seen.add(tech)
                    results.append({
                        "technology": tech,
                        "category": cat,
                        "version": str(version) if version else None,
                        "confidence": "high",
                        "detection_method": "composer.json",
                        "evidence_paths": [evidence_path],
                    })
    return results


def _detect_infra_from_files(files: list[dict]) -> list[dict]:
    """Detect Docker, K8s, Terraform, CI from file paths."""
    results: list[dict] = []
    seen: set[str] = set()

    for f in files:
        path = f.get("path", "")
        name = PurePosixPath(path).name.lower()
        parts = set(PurePosixPath(path).parts)

        # Docker
        if name in ("dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml") and "Docker" not in seen:
            seen.add("Docker")
            results.append({
                "technology": "Docker",
                "category": "infrastructure",
                "version": None,
                "confidence": "high",
                "detection_method": "file_presence",
                "evidence_paths": [path],
            })

        # Kubernetes
        if (name.endswith(".yaml") or name.endswith(".yml")) and any(
            kw in path.lower() for kw in ("k8s", "kubernetes", "deployment", "service.yaml", "service.yml")
        ) and "Kubernetes" not in seen:
            seen.add("Kubernetes")
            results.append({
                "technology": "Kubernetes",
                "category": "infrastructure",
                "version": None,
                "confidence": "medium",
                "detection_method": "file_path_pattern",
                "evidence_paths": [path],
            })

        # GitHub Actions
        if ".github" in parts and "workflows" in parts and (name.endswith(".yml") or name.endswith(".yaml")) and "GitHub Actions" not in seen:
            seen.add("GitHub Actions")
            results.append({
                "technology": "GitHub Actions",
                "category": "infrastructure",
                "version": None,
                "confidence": "high",
                "detection_method": "file_presence",
                "evidence_paths": [path],
            })

        # Terraform
        if path.endswith(".tf") and "Terraform" not in seen:
            seen.add("Terraform")
            results.append({
                "technology": "Terraform",
                "category": "infrastructure",
                "version": None,
                "confidence": "high",
                "detection_method": "file_presence",
                "evidence_paths": [path],
            })

        # GitLab CI
        if name == ".gitlab-ci.yml" and "GitLab CI" not in seen:
            seen.add("GitLab CI")
            results.append({
                "technology": "GitLab CI",
                "category": "infrastructure",
                "version": None,
                "confidence": "high",
                "detection_method": "file_presence",
                "evidence_paths": [path],
            })

        # Vercel
        if name == "vercel.json" and "Vercel" not in seen:
            seen.add("Vercel")
            results.append({
                "technology": "Vercel",
                "category": "infrastructure",
                "version": None,
                "confidence": "high",
                "detection_method": "file_presence",
                "evidence_paths": [path],
            })

        # Netlify
        if name == "netlify.toml" and "Netlify" not in seen:
            seen.add("Netlify")
            results.append({
                "technology": "Netlify",
                "category": "infrastructure",
                "version": None,
                "confidence": "high",
                "detection_method": "file_presence",
                "evidence_paths": [path],
            })

    return results


def _detect_databases_from_content(file_contents: dict[str, str]) -> list[dict]:
    """Detect database technologies from configuration files."""
    results: list[dict] = []
    seen: set[str] = set()

    db_patterns: list[tuple[str, str, list[re.Pattern[str]]]] = [
        ("PostgreSQL", "database", [
            re.compile(r'postgres(?:ql)?(?:\+psycopg)?://', re.I),
            re.compile(r'DATABASE_URL.*postgres', re.I),
            re.compile(r'POSTGRES_', re.I),
        ]),
        ("MySQL", "database", [
            re.compile(r'mysql://', re.I),
            re.compile(r'MYSQL_', re.I),
        ]),
        ("SQLite", "database", [
            re.compile(r'sqlite(?:3)?://', re.I),
            re.compile(r'\.db["\']', re.I),
        ]),
        ("MongoDB", "database", [
            re.compile(r'mongodb(?:\+srv)?://', re.I),
            re.compile(r'MONGO_', re.I),
        ]),
        ("Redis", "database", [
            re.compile(r'redis://', re.I),
            re.compile(r'REDIS_URL', re.I),
            re.compile(r'REDIS_HOST', re.I),
        ]),
    ]

    for path, content in file_contents.items():
        for tech, cat, patterns in db_patterns:
            if tech in seen:
                continue
            for pat in patterns:
                if pat.search(content):
                    seen.add(tech)
                    results.append({
                        "technology": tech,
                        "category": cat,
                        "version": None,
                        "confidence": "medium",
                        "detection_method": "config_pattern",
                        "evidence_paths": [path],
                    })
                    break

    return results


# ── Manifest file router ────────────────────────────────────────────────────

_MANIFEST_PARSERS: dict[str, object] = {
    "package.json": "_npm",
    "requirements.txt": "_requirements",
    "pyproject.toml": "_pyproject",
    "cargo.toml": "_cargo",
    "go.mod": "_go",
    "pom.xml": "_pom",
    "build.gradle": "_gradle",
    "composer.json": "_composer",
    "pipfile": "_requirements",  # close enough
}


def detect_technologies(
    files: list[dict],
    file_contents: dict[str, str],
) -> list[dict]:
    """Detect technologies from manifest files, file structure, and configs.

    Parameters
    ----------
    files:
        List of ``{path, extension}`` dicts for every file in the snapshot.
    file_contents:
        Maps ``path → content`` for manifest / configuration files.

    Returns
    -------
    List of ``{technology, category, version, confidence, detection_method,
    evidence_paths}`` dicts, deduplicated by technology name.
    """
    all_results: list[dict] = []
    seen: set[str] = set()

    def _merge(items: list[dict]) -> None:
        for item in items:
            tech = item["technology"]
            if tech not in seen:
                seen.add(tech)
                all_results.append(item)
            else:
                # Merge evidence paths
                for existing in all_results:
                    if existing["technology"] == tech:
                        for p in item.get("evidence_paths", []):
                            if p not in existing["evidence_paths"]:
                                existing["evidence_paths"].append(p)
                        break

    # Parse manifest files
    for path, content in file_contents.items():
        name = PurePosixPath(path).name.lower()

        try:
            if name == "package.json":
                data = json.loads(content)
                _merge(_parse_npm_deps(data, path))
            elif name == "requirements.txt":
                _merge(_parse_requirements_txt(content, path))
            elif name == "pyproject.toml":
                _merge(_parse_pyproject_toml(content, path))
            elif name == "cargo.toml":
                _merge(_parse_cargo_toml(content, path))
            elif name == "go.mod":
                _merge(_parse_go_mod(content, path))
            elif name == "pom.xml":
                _merge(_parse_pom_xml(content, path))
            elif name in ("build.gradle", "build.gradle.kts"):
                _merge(_parse_build_gradle(content, path))
            elif name == "composer.json":
                _merge(_parse_composer_json(content, path))
            elif name == "pipfile":
                _merge(_parse_requirements_txt(content, path))
        except Exception:
            logger.debug("Failed to parse manifest %s", path, exc_info=True)

    # Infrastructure detection from file paths
    _merge(_detect_infra_from_files(files))

    # Database detection from file contents
    _merge(_detect_databases_from_content(file_contents))

    return all_results
