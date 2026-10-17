"""Find the MCP server(s) in a directory tree and resolve what they depend on.

A server is rarely alone at the root: a typical deployment is a
pnpm monorepo whose server lives in `apps/mcp-server`, whose SDK version is
`catalog:` (resolved in `pnpm-workspace.yaml`), and whose auth code lives in a
`workspace:*` package next door. So discovery works in *units*: a directory
with a manifest (`package.json`, `pyproject.toml`, `requirements*.txt`,
`setup.cfg`) whose dependencies or sources involve an MCP SDK. Each unit knows
its declared and resolved SDK versions, its source files, and the workspace
packages it depends on, whose sources are read too (auth and hosting signals
often live there) but are not reviewed as servers.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import PY_PACKAGE, TS_EXT_APPS, TS_V1_PACKAGE, TS_V2_PACKAGES

SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", "out", ".venv", "venv", "env", "__pycache__",
    ".next", ".turbo", "cdk.out", ".terraform", ".terragrunt-cache", "coverage", ".pytest_cache",
    ".mypy_cache", ".tox", "site-packages", ".scaffold",
}
TS_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs")
PY_SUFFIX = ".py"
TEST_MARKERS = re.compile(r"(?:^|[./_-])(?:test|tests|spec|__tests__)(?:[./_-]|$)")
MAX_FILES = 4000


@dataclass
class Dependency:
    name: str
    declared: str           # as written: "^1.29.0", "catalog:", "workspace:*", ">=1.9"
    resolved: str | None    # a concrete or minimum version when one can be read
    source: str             # file it came from

    @property
    def major(self) -> int | None:
        if not self.resolved:
            return None
        match = re.search(r"(\d+)(?:\.\d+)*", self.resolved)
        return int(match.group(1)) if match else None


@dataclass
class Unit:
    path: Path
    language: str                    # typescript | python | mixed
    manifest: str
    name: str = ""
    deps: dict[str, Dependency] = field(default_factory=dict)
    sources: list[Path] = field(default_factory=list)
    test_sources: list[Path] = field(default_factory=list)
    workspace_deps: list[Path] = field(default_factory=list)
    engines_node: str | None = None

    def dep(self, name: str) -> Dependency | None:
        return self.deps.get(name)

    @property
    def mcp_packages(self) -> list[str]:
        names = [TS_V1_PACKAGE, *TS_V2_PACKAGES, TS_EXT_APPS, PY_PACKAGE, "fastmcp"]
        return [n for n in names if n in self.deps]


@dataclass
class Layout:
    root: Path
    units: list[Unit]
    workflows: list[Path]
    hosting_files: dict[str, list[str]]
    addon_files: list[Path]
    node_version: str | None
    repo_root: Path


def walk(root: Path, *, max_depth: int = 8):
    root_depth = len(root.parts)
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
                             or d in (".github",))
        if len(Path(dirpath).parts) - root_depth >= max_depth:
            dirnames[:] = []
        for name in sorted(filenames):
            count += 1
            if count > MAX_FILES * 4:
                return
            yield Path(dirpath) / name


# -- manifests ----------------------------------------------------------------

def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def pnpm_catalogs(workspace_file: Path) -> dict[str, dict[str, str]]:
    """Parse `catalog:` and `catalogs:` from pnpm-workspace.yaml (a small YAML subset)."""
    catalogs: dict[str, dict[str, str]] = {}
    try:
        lines = workspace_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return catalogs
    section: str | None = None
    named: str | None = None
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if indent == 0:
            section = line.rstrip(":") if line.endswith(":") else None
            named = None
            if section == "catalog":
                catalogs.setdefault("default", {})
            continue
        match = re.match(r"""^["']?([^"':]+?)["']?\s*:\s*["']?([^"'#]*?)["']?\s*$""", line)
        if section == "catalog" and match and indent > 0:
            catalogs["default"][match.group(1)] = match.group(2)
        elif section == "catalogs":
            if line.endswith(":") and match is None or (match and not match.group(2)):
                named = line.rstrip(":").strip("\"'")
                catalogs.setdefault(named, {})
            elif match and named:
                catalogs[named][match.group(1)] = match.group(2)
    return catalogs


def _min_version(spec: str) -> str | None:
    match = re.search(r"(\d+(?:\.\d+){0,2})", spec or "")
    return match.group(1) if match else None


def _find_upwards(start: Path, name: str, stop: Path) -> Path | None:
    current = start
    while True:
        candidate = current / name
        if candidate.is_file():
            return candidate
        if current == stop or current.parent == current:
            return None
        current = current.parent


def node_deps(package_json: Path, repo_root: Path) -> tuple[dict[str, Dependency], str, str | None]:
    data = _read_json(package_json)
    deps: dict[str, Dependency] = {}
    workspace = _find_upwards(package_json.parent, "pnpm-workspace.yaml", repo_root)
    catalogs = pnpm_catalogs(workspace) if workspace else {}
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        for name, spec in (data.get(section) or {}).items():
            spec = str(spec)
            resolved: str | None
            source = str(package_json)
            if spec.startswith("catalog:"):
                cat = spec.split(":", 1)[1] or "default"
                value = catalogs.get(cat, {}).get(name)
                resolved = _min_version(value) if value else None
                if value:
                    source = str(workspace)
            elif spec.startswith(("workspace:", "file:", "link:")):
                resolved = None
            else:
                resolved = _min_version(spec)
            deps.setdefault(name, Dependency(name, spec, resolved, source))
    engines = (data.get("engines") or {}).get("node")
    return deps, str(data.get("name") or ""), engines


_PY_REQ = re.compile(r"^\s*([A-Za-z0-9_.\-\[\]]+)\s*((?:[<>=!~]=?|===)\s*[^;#\s,]+(?:\s*,\s*[<>=!~]=?\s*[^;#\s,]+)*)?")


def python_deps(unit_dir: Path) -> tuple[dict[str, Dependency], str]:
    deps: dict[str, Dependency] = {}
    manifest = ""
    for name in ("pyproject.toml", "setup.cfg", "requirements.txt", "requirements-dev.txt",
                 "requirements.in", "Pipfile"):
        path = unit_dir / name
        if not path.is_file():
            continue
        manifest = manifest or name
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        candidates: list[str] = []
        if name == "pyproject.toml":
            candidates = re.findall(r"""["']([A-Za-z0-9_.\-\[\]]+\s*(?:[<>=!~]=?[^"']*)?)["']""", text)
            candidates += [f"{k}{v.strip()}" for k, v in
                           re.findall(r"^\s*([A-Za-z0-9_.\-]+)\s*=\s*\"([^\"]*)\"", text, re.M)
                           if k in (PY_PACKAGE, "fastmcp")]
        else:
            candidates = text.splitlines()
        for line in candidates:
            match = _PY_REQ.match(line)
            if not match:
                continue
            pkg = re.sub(r"\[.*\]", "", match.group(1)).lower()
            if pkg not in (PY_PACKAGE, "fastmcp", "mcp-types", "starlette", "fastapi", "uvicorn",
                           "mangum", "httpx", "httpx2", "pyjwt", "python-jose", "authlib"):
                continue
            spec = (match.group(2) or "").replace(" ", "")
            deps.setdefault(pkg, Dependency(pkg, spec or "*", _min_version(spec), str(path)))
    return deps, manifest


# -- detection -------------------------------------------------------------------

_TS_MCP_IMPORT = re.compile(r"""['"]@modelcontextprotocol/(?:sdk|server|node|express|hono|fastify|ext-apps)""")
_PY_MCP_IMPORT = re.compile(r"^\s*(?:from|import)\s+(?:mcp|fastmcp)\b", re.M)


def _is_test(path: Path, root: Path) -> bool:
    rel = str(path.relative_to(root)).replace(os.sep, "/")
    return bool(TEST_MARKERS.search(rel)) or rel.endswith(".d.ts")


def detect(root: Path) -> Layout:
    root = root.resolve()
    repo_root = root
    for candidate in [root, *root.parents]:
        if (candidate / ".git").exists() or (candidate / "pnpm-workspace.yaml").is_file():
            repo_root = candidate
            break

    manifests: list[Path] = []
    workflows: list[Path] = []
    hosting: dict[str, list[str]] = {}
    addons: list[Path] = []
    all_files: list[Path] = []
    for path in walk(root):
        name = path.name
        rel_parts = path.relative_to(root).parts
        if ".github" in rel_parts:
            if path.suffix in (".yml", ".yaml") and "workflows" in rel_parts:
                workflows.append(path)
            continue
        all_files.append(path)
        if name in ("package.json", "pyproject.toml", "requirements.txt", "setup.cfg", "Pipfile"):
            manifests.append(path)
        if name == "addon.json":
            addons.append(path)
        for kind, patterns in _HOSTING_FILES.items():
            if any(re.fullmatch(p, name) for p in patterns):
                hosting.setdefault(kind, []).append(str(path.relative_to(root)))
        if name.endswith((".tf", ".hcl")) and "aws_lambda_function" in _peek(path):
            hosting.setdefault("lambda-terraform", []).append(str(path.relative_to(root)))
    for wf_root in {repo_root, root}:
        wf_dir = wf_root / ".github" / "workflows"
        if wf_dir.is_dir():
            workflows += [p for p in sorted(wf_dir.iterdir()) if p.suffix in (".yml", ".yaml")]
    workflows = sorted(set(workflows))

    # Each manifest directory is a candidate unit; sources belong to the nearest one.
    unit_dirs = sorted({m.parent for m in manifests}, key=lambda p: len(p.parts), reverse=True)
    if root not in unit_dirs:
        unit_dirs.append(root)
    owner: dict[Path, list[Path]] = {d: [] for d in unit_dirs}
    for path in all_files:
        if path.suffix not in TS_SUFFIXES and path.suffix != PY_SUFFIX:
            continue
        for d in unit_dirs:
            if d == path.parent or d in path.parents:
                owner[d].append(path)
                break

    packages_by_name: dict[str, Path] = {}
    for m in manifests:
        if m.name == "package.json":
            name = _read_json(m).get("name")
            if name:
                packages_by_name[name] = m.parent

    units: list[Unit] = []
    for d in unit_dirs:
        files = owner[d]
        ts_files = [f for f in files if f.suffix in TS_SUFFIXES]
        py_files = [f for f in files if f.suffix == PY_SUFFIX]
        deps: dict[str, Dependency] = {}
        manifest = ""
        name = d.name
        engines = None
        workspace_deps: list[Path] = []
        if (d / "package.json").is_file():
            node, pkg_name, engines = node_deps(d / "package.json", repo_root)
            deps.update(node)
            manifest = "package.json"
            name = pkg_name or name
            for dep in node.values():
                if dep.declared.startswith("workspace:") and dep.name in packages_by_name:
                    workspace_deps.append(packages_by_name[dep.name])
        py, py_manifest = python_deps(d)
        deps.update(py)
        manifest = manifest or py_manifest
        mcp_declared = any(n in deps for n in (TS_V1_PACKAGE, *TS_V2_PACKAGES, PY_PACKAGE, "fastmcp"))
        ts_mcp = [f for f in ts_files if _TS_MCP_IMPORT.search(_peek(f, 200_000))]
        py_mcp = [f for f in py_files if _PY_MCP_IMPORT.search(_peek(f, 200_000))]
        if not mcp_declared and not ts_mcp and not py_mcp:
            continue
        language = "mixed" if (ts_mcp or (TS_V1_PACKAGE in deps)) and (py_mcp or PY_PACKAGE in deps) else \
            "python" if (py_mcp or PY_PACKAGE in deps or "fastmcp" in deps) else "typescript"
        sources = ts_files if language == "typescript" else py_files if language == "python" else files
        unit = Unit(path=d, language=language, manifest=manifest or "(none)", name=name, deps=deps,
                    sources=[f for f in sources if not _is_test(f, d)],
                    test_sources=[f for f in sources if _is_test(f, d)],
                    workspace_deps=sorted(set(workspace_deps)), engines_node=engines)
        units.append(unit)

    node_version = None
    for candidate in (root, repo_root):
        nvmrc = candidate / ".nvmrc"
        if nvmrc.is_file():
            node_version = nvmrc.read_text(encoding="utf-8").strip().lstrip("v")
            break
    units.sort(key=lambda u: str(u.path))
    return Layout(root=root, units=units, workflows=workflows, hosting_files=hosting,
                  addon_files=sorted(addons), node_version=node_version, repo_root=repo_root)


_HOSTING_FILES = {
    "serverless-framework": [r"serverless\.ya?ml"],
    "aws-sam": [r"template\.ya?ml", r"samconfig\.toml"],
    "aws-cdk": [r"cdk\.json"],
    "terragrunt": [r"terragrunt\.hcl"],
    "docker": [r"Dockerfile(\..+)?"],
    "cloudflare-workers": [r"wrangler\.(?:toml|jsonc?)"],
    "vercel": [r"vercel\.json"],
    "fly": [r"fly\.toml"],
    "agentcore": [r"\.bedrock_agentcore\.ya?ml", r"agentcore\.json"],
}


def _peek(path: Path, limit: int = 400_000) -> str:
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return ""


def workspace_sources(unit: Unit) -> list[Path]:
    """Source files of the workspace packages a unit depends on (not reviewed as servers)."""
    out: list[Path] = []
    for pkg in unit.workspace_deps:
        for path in walk(pkg):
            if path.suffix in TS_SUFFIXES and not _is_test(path, pkg):
                out.append(path)
    return out
