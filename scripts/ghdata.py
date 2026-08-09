"""Shared GitHub data access and tech detection.

gen_cards.py and gen_readme.py describe the same repositories, so the repo
list, the file scan, the tech catalog, and the language tally live here and are
imported by both. Stdlib only.

Coverage notes:

- Every owned, non-fork repo created on/after REPO_CUTOFF counts, private ones
  included. Detection yields *labels only* (LangGraph, Go, React...) and a
  language byte tally; no private repo name, description, or file content ever
  reaches a generated artifact.
- Manifests are found anywhere in the tree, not just at the root, because most
  repos here keep them nested (backend/pyproject.toml, frontend/package.json,
  code/requirements.txt).
- Repos that declare no manifest at all (the paper repos: a README plus code)
  fall back to scanning the README, with ambiguous tokens suppressed so English
  prose cannot mint a skill.

Reading private repos requires a token with `repo` scope; a workflow's default
GITHUB_TOKEN only sees this repository, so the repo listing falls back to the
public-only endpoint when the private listing is refused.
"""

import base64
import collections
import json
import os
import re
import urllib.error
import urllib.request
from typing import NamedTuple

USER = "Vijay190899"
TOKEN = os.environ.get("GITHUB_TOKEN", "")

# Only repos created on/after this date count, so old notebook-era work does
# not resurface stale tech. Shared by both generators.
REPO_CUTOFF = "2025-01-01"

# Most manifests sit at the root or one level down; the cap bounds API calls on
# repos with thousands of files without losing the ones that matter.
MAX_MANIFESTS_PER_REPO = 12


class Tech(NamedTuple):
    """One detectable skill.

    tokens   : substrings searched in manifests (word-boundary prefixed)
    color    : swatch on the frameworks card
    category : Stack section it joins when auto-grown into the README
    badge    : shields.io image URL, or "" when the label is card-only
    in_card  : whether it competes for a slot on the frameworks card
    """

    tokens: tuple[str, ...]
    color: str
    category: str
    badge: str
    in_card: bool = True


def _badge(slug: str, logo: str = "", logo_color: str = "white") -> str:
    """shields.io URL. `slug` is already "Label-HEXCOLOR" in shields' own
    grammar, so an underscore is a space and a double dash is a literal dash."""
    url = f"https://img.shields.io/badge/{slug}?style=for-the-badge"
    if logo:
        url += f"&logo={logo}&logoColor={logo_color}"
    return url


# Catalog order is the tie-break order everywhere: it puts the agentic stack
# ahead of supporting libraries when two techs appear in the same number of
# repos, and fixes badge order within a Stack category.
#
# in_card=False marks tooling that is near-uniform across repos (pytest, ruff,
# CI, git): worth a badge, but it would crowd out signal on the card.
TECH: dict[str, Tech] = {
    # --- AI and agents --------------------------------------------------------
    "LangGraph": Tech(("langgraph",), "#4db6ac", "AI and agents",
                      _badge("LangGraph-1C3C3C", "langgraph")),
    "CrewAI": Tech(("crewai",), "#ff5a50", "AI and agents",
                   _badge("CrewAI-FF5A50", "crewai")),
    "LangChain": Tech(("langchain",), "#86efac", "AI and agents",
                      _badge("LangChain-1C3C3C", "langchain")),
    "MCP": Tech(("modelcontextprotocol", "mcp"), "#ffa657", "AI and agents",
                _badge("MCP-000000", "modelcontextprotocol")),
    "OpenAI": Tech(("openai",), "#74aa9c", "AI and agents",
                   _badge("OpenAI-412991", "openai")),
    "Anthropic": Tech(("anthropic", "claude"), "#d4a27f", "AI and agents",
                      _badge("Anthropic-191919", "anthropic")),
    "Hugging Face": Tech(("huggingface", "transformers", "datasets"), "#ffd21e",
                         "AI and agents",
                         _badge("Hugging_Face-FFD21E", "huggingface", "black")),
    "PyTorch": Tech(("pytorch", "torch"), "#ee4c2c", "AI and agents",
                    _badge("PyTorch-EE4C2C", "pytorch")),
    "vLLM": Tech(("vllm",), "#3b82f6", "AI and agents", _badge("vLLM-000000")),
    "Ollama": Tech(("ollama",), "#c9d1d9", "AI and agents",
                   _badge("Ollama-000000", "ollama")),
    "Groq": Tech(("groq",), "#f55036", "AI and agents", _badge("Groq-F55036", "groq")),
    "Langfuse": Tech(("langfuse",), "#bc8cff", "AI and agents",
                     _badge("Langfuse-000000")),
    "Ragas": Tech(("ragas",), "#6e56cf", "AI and agents", _badge("Ragas-6E56CF")),

    # --- Backend and data -----------------------------------------------------
    # Python is language-detected, not manifest-detected, so it carries no
    # tokens; it stays under "AI and agents" to match the curated baseline.
    "Python": Tech((), "#3572a5", "AI and agents",
                   _badge("Python-3776AB", "python"), in_card=False),
    "FastAPI": Tech(("fastapi",), "#009688", "Backend and data",
                    _badge("FastAPI-009688", "fastapi")),
    "Pydantic": Tech(("pydantic",), "#e92063", "Backend and data",
                     _badge("Pydantic-E92063", "pydantic")),
    "Go": Tech(("github.com/gin-gonic", "github.com/labstack"), "#00add8",
               "Backend and data", _badge("Go-00ADD8", "go"), in_card=False),
    "PostgreSQL": Tech(("postgres", "psycopg", "pgvector", "plpgsql"), "#4169e1",
                       "Backend and data", _badge("PostgreSQL-4169E1", "postgresql")),
    "Redis": Tech(("redis",), "#ff4438", "Backend and data",
                  _badge("Redis-FF4438", "redis")),
    "SQLite": Tech(("sqlite", "aiosqlite"), "#003b57", "Backend and data",
                   _badge("SQLite-003B57", "sqlite")),
    "Qdrant": Tech(("qdrant",), "#dc244c", "Backend and data",
                   _badge("Qdrant-DC244C", "qdrant")),
    "Chroma": Tech(("chromadb", "chroma"), "#ff6f61", "Backend and data",
                   _badge("Chroma-FF6F61")),
    "Neo4j": Tech(("neo4j",), "#4581c3", "Backend and data",
                  _badge("Neo4j-4581C3", "neo4j")),
    "NumPy": Tech(("numpy",), "#013243", "Backend and data",
                  _badge("NumPy-013243", "numpy")),
    "Pandas": Tech(("pandas",), "#150458", "Backend and data",
                   _badge("Pandas-150458", "pandas")),
    "scikit-learn": Tech(("scikit-learn", "sklearn"), "#f7931e", "Backend and data",
                         _badge("scikit--learn-F7931E", "scikitlearn")),
    "Matplotlib": Tech(("matplotlib",), "#11557c", "Backend and data",
                       _badge("Matplotlib-11557C")),
    "Jupyter": Tech(("jupyter", "ipykernel"), "#f37626", "Backend and data",
                    _badge("Jupyter-F37626", "jupyter")),
    "Streamlit": Tech(("streamlit",), "#ff4b4b", "Backend and data",
                      _badge("Streamlit-FF4B4B", "streamlit")),

    # --- Web and interfaces ---------------------------------------------------
    "TypeScript": Tech(("typescript",), "#3178c6", "Web and interfaces",
                       _badge("TypeScript-3178C6", "typescript"), in_card=False),
    "JavaScript": Tech((), "#f1e05a", "Web and interfaces",
                       _badge("JavaScript-F7DF1E", "javascript", "black"),
                       in_card=False),
    "React": Tech(("react",), "#61dafb", "Web and interfaces",
                  _badge("React-149ECA", "react")),
    # A bare "next" token also matches NEXTAUTH_SECRET and similar env keys, so
    # this one insists on a dependency entry or an npm script.
    "Next.js": Tech((r're:"next"\s*:\s*"|\bnext (dev|build|start)\b',), "#c9d1d9",
                    "Web and interfaces", _badge("Next.js-000000", "nextdotjs")),
    "Tailwind": Tech(("tailwindcss",), "#38bdf8", "Web and interfaces",
                     _badge("Tailwind_CSS-06B6D4", "tailwindcss")),
    "Vite": Tech(("vite",), "#a855f7", "Web and interfaces",
                 _badge("Vite-646CFF", "vite")),
    "Node.js": Tech(("express", "fastify", "hono"), "#5fa04e", "Web and interfaces",
                    _badge("Node.js-5FA04E", "nodedotjs")),
    "Cloudflare": Tech(("wrangler", "cloudflare"), "#f38020", "Web and interfaces",
                       _badge("Cloudflare-F38020", "cloudflare")),

    # --- Cloud and operations -------------------------------------------------
    # Docker, GitHub Actions, uv: proven by a file's existence, never by a token.
    "Docker": Tech((), "#2496ed", "Cloud and operations",
                   _badge("Docker-2496ED", "docker")),
    "Kubernetes": Tech(("kubernetes", "kubectl"), "#326ce5", "Cloud and operations",
                       _badge("Kubernetes-326CE5", "kubernetes")),
    "Helm": Tech(("helm",), "#0f1689", "Cloud and operations",
                 _badge("Helm-0F1689", "helm")),
    "Terraform": Tech(("terraform",), "#844fba", "Cloud and operations",
                      _badge("Terraform-844FBA", "terraform")),
    "AWS": Tech(("boto3", "aws-", "amazonaws"), "#ff9900", "Cloud and operations",
                _badge("AWS-232F3E", "amazonwebservices")),
    "Google Cloud": Tech(("google-cloud",), "#4285f4", "Cloud and operations",
                         _badge("Google_Cloud-4285F4", "googlecloud")),
    "GitHub Actions": Tech((), "#2088ff", "Cloud and operations",
                           _badge("GitHub_Actions-2088FF", "githubactions"),
                           in_card=False),
    "Linux": Tech((), "#fcc624", "Cloud and operations",
                  _badge("Linux-FCC624", "linux", "black"), in_card=False),
    "Git": Tech((), "#f05032", "Cloud and operations",
                _badge("Git-F05032", "git"), in_card=False),

    # --- Tooling and quality --------------------------------------------------
    "uv": Tech((), "#de5fe9", "Tooling and quality",
               _badge("uv-DE5FE9", "uv"), in_card=False),
    "Ruff": Tech(("ruff",), "#d7ff64", "Tooling and quality",
                 _badge("Ruff-D7FF64", "ruff", "black"), in_card=False),
    "Pytest": Tech(("pytest",), "#0a9edc", "Tooling and quality",
                   _badge("Pytest-0A9EDC", "pytest"), in_card=False),
    "Vitest": Tech(("vitest",), "#6da13a", "Tooling and quality",
                   _badge("Vitest-6E9F18", "vitest"), in_card=False),
    "Playwright": Tech(("playwright",), "#2ead33", "Tooling and quality",
                       _badge("Playwright-2EAD33", "playwright"), in_card=False),
    "Pre-commit": Tech(("pre-commit",), "#fab040", "Tooling and quality",
                       _badge("Pre--commit-FAB040", "precommit", "black"),
                       in_card=False),
    "LaTeX": Tech(("latex",), "#008080", "Tooling and quality",
                  _badge("LaTeX-008080", "latex"), in_card=False),
}

PRIORITY = {label: i for i, label in enumerate(TECH)}

# Tokens that are ordinary English words. Trusted inside a dependency manifest,
# ignored when falling back to a README, where "models react to..." or "the next
# step" would otherwise register as a framework.
AMBIGUOUS = {"react", "next", "datasets", "helm", "vite", "claude"}

# Files worth downloading, matched on basename. requirements*.txt is handled
# separately by pattern.
MANIFEST_NAMES = {
    "pyproject.toml", "setup.py", "setup.cfg", "environment.yml", "pipfile",
    "package.json", "go.mod", "cargo.toml", "gemfile", "pom.xml",
    "build.gradle", "wrangler.toml", "docker-compose.yml", "docker-compose.yaml",
    "compose.yaml", "compose.yml",
}

# Path shapes that prove a tech without downloading anything.
PATH_SIGNALS: tuple[tuple[str, str], ...] = (
    (r"(^|/)dockerfile(\.|$)", "Docker"),
    (r"(^|/)docker-compose\.ya?ml$|(^|/)compose\.ya?ml$", "Docker"),
    (r"\.tf$|\.tfvars$", "Terraform"),
    (r"^\.github/workflows/.+\.ya?ml$", "GitHub Actions"),
    (r"\.ipynb$", "Jupyter"),
    (r"(^|/)chart\.yaml$|(^|/)helm/", "Helm"),
    (r"(^|/)(k8s|kubernetes)/", "Kubernetes"),
    (r"(^|/)wrangler\.(toml|jsonc?)$", "Cloudflare"),
    (r"\.tex$", "LaTeX"),
    (r"(^|/)tsconfig(\..+)?\.json$", "TypeScript"),
    (r"(^|/)tailwind\.config\.", "Tailwind"),
    (r"(^|/)next\.config\.", "Next.js"),
    (r"(^|/)vite\.config\.", "Vite"),
    (r"(^|/)playwright\.config\.", "Playwright"),
    (r"(^|/)vitest\.config\.", "Vitest"),
    (r"(^|/)\.pre-commit-config\.ya?ml$", "Pre-commit"),
    (r"(^|/)uv\.lock$", "uv"),
    (r"(^|/)ruff\.toml$", "Ruff"),
    (r"(^|/)go\.mod$", "Go"),
)

# GitHub language name -> Stack label, for languages that earn a badge on byte
# share alone. Languages absent here still appear on the languages card.
LANGUAGE_LABEL = {
    "Python": "Python",
    "TypeScript": "TypeScript",
    "JavaScript": "JavaScript",
    "Go": "Go",
    "TeX": "LaTeX",
    "Jupyter Notebook": "Jupyter",
    "PLpgSQL": "PostgreSQL",
    "HCL": "Terraform",
}

# Generated or incidental files GitHub reports as languages. Excluding them
# keeps the languages card about work actually written by hand.
LANGUAGE_NOISE = {"BibTeX Style", "Roff", "Batchfile", "Makefile", "Dockerfile"}

# Swatches for the languages card, GitHub Linguist colors where one exists.
LANGUAGE_COLOR = {
    "Python": "#3572a5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a",
    "Go": "#00add8", "TeX": "#3d6117", "CSS": "#663399", "HTML": "#e34c26",
    "Jupyter Notebook": "#da5b0b", "Shell": "#89e051", "PLpgSQL": "#336790",
    "HCL": "#844fba", "PowerShell": "#012456", "Rust": "#dea584",
    "Java": "#b07219", "C++": "#f34b7d", "Ruby": "#701516", "SCSS": "#c6538c",
}
LANGUAGE_FALLBACK = "#8b949e"


# --- HTTP ---------------------------------------------------------------------


def http_get(url: str, token: str = TOKEN) -> str:
    headers = {"User-Agent": USER}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/vnd.github+json"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as response:
        return response.read().decode()


def api(path: str):
    return json.loads(http_get(f"https://api.github.com{path}"))


def api_or(path: str, default):
    """API result, or `default` when the call fails (missing file, no access)."""
    try:
        return api(path)
    except Exception:
        return default


# --- repositories -------------------------------------------------------------


def owned_repos() -> list[dict]:
    """Owned, non-fork repos created on/after REPO_CUTOFF, newest first.

    Prefers /user/repos, which includes private repos when the token carries
    `repo` scope. A workflow's default GITHUB_TOKEN cannot use that endpoint, so
    the public-only listing is the fallback and the run still succeeds.
    """
    repos: list[dict] = []
    try:
        for page in range(1, 6):
            batch = api(f"/user/repos?affiliation=owner&per_page=100&page={page}")
            repos.extend(batch)
            if len(batch) < 100:
                break
    except urllib.error.HTTPError:
        repos = api(f"/users/{USER}/repos?per_page=100&type=owner")

    kept = [
        r for r in repos
        if not r.get("fork")
        and r["created_at"][:10] >= REPO_CUTOFF
        # The profile repo is excluded from its own statistics: its README
        # lists every badge, so scanning it would feed the generated Stack
        # straight back into detection and each run would confirm itself.
        and r["name"] != USER
    ]
    kept.sort(key=lambda r: r["created_at"], reverse=True)
    return kept


def repo_paths(repo: dict) -> list[str]:
    """Every file path in the repo's default branch, in one call."""
    branch = repo.get("default_branch") or "main"
    tree = api_or(f"/repos/{repo['full_name']}/git/trees/{branch}?recursive=1", {})
    return [e["path"] for e in tree.get("tree", []) if e.get("type") == "blob"]


def repo_file(full_name: str, path: str) -> str:
    """A file's text, or "" when it is missing, binary, or too large to inline."""
    payload = api_or(f"/repos/{full_name}/contents/{path}", None)
    if not isinstance(payload, dict) or "content" not in payload:
        return ""
    try:
        return base64.b64decode(payload["content"]).decode(errors="ignore")
    except Exception:
        return ""


def _is_manifest(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].lower()
    return name in MANIFEST_NAMES or re.fullmatch(r"requirements.*\.txt", name) is not None


def detect_tech(repo: dict) -> set[str]:
    """Labels evidenced by a repo's file layout, manifests, and (if it declares
    no dependencies anywhere) its README."""
    paths = repo_paths(repo)
    found: set[str] = set()

    for pattern, label in PATH_SIGNALS:
        if any(re.search(pattern, p, re.IGNORECASE) for p in paths):
            found.add(label)

    # Shallowest manifests first: a root pyproject.toml describes the project,
    # one buried under examples/ usually does not.
    manifests = sorted(
        (p for p in paths if _is_manifest(p)), key=lambda p: (p.count("/"), p)
    )[:MAX_MANIFESTS_PER_REPO]
    blob = "\n".join(repo_file(repo["full_name"], p) for p in manifests).lower()

    if blob:
        found |= _match_tokens(blob, allow_ambiguous=True)
    else:
        # Paper repos: a README and code, no dependency file to read.
        readme = api_or(f"/repos/{repo['full_name']}/readme", None)
        if isinstance(readme, dict) and "content" in readme:
            text = base64.b64decode(readme["content"]).decode(errors="ignore").lower()
            found |= _match_tokens(text, allow_ambiguous=False)

    for topic in repo.get("topics", []) or []:
        found |= _match_tokens(topic.lower(), allow_ambiguous=False)

    return found


def _match_tokens(text: str, allow_ambiguous: bool) -> set[str]:
    """Labels whose tokens appear in `text` (already lowercased).

    A token is a literal matched on a word boundary, unless it is written
    "re:<pattern>", in which case the pattern is used as-is. Raw patterns are
    already precise, so they are never treated as ambiguous.
    """
    found = set()
    for label, tech in TECH.items():
        for token in tech.tokens:
            if token.startswith("re:"):
                pattern = token[3:]
            elif not allow_ambiguous and token in AMBIGUOUS:
                continue
            else:
                pattern = rf"\b{re.escape(token)}"
            if re.search(pattern, text):
                found.add(label)
                break
    return found


# --- languages ----------------------------------------------------------------


def language_bytes(repos: list[dict]) -> dict[str, int]:
    """Bytes per language summed over every repo, noise languages dropped."""
    total: collections.Counter[str] = collections.Counter()
    for repo in repos:
        for language, count in api_or(
            f"/repos/{repo['full_name']}/languages", {}
        ).items():
            if language not in LANGUAGE_NOISE:
                total[language] += count
    return dict(total.most_common())


def language_labels(totals: dict[str, int], min_share: float = 0.01) -> set[str]:
    """Stack labels earned by languages holding at least `min_share` of bytes.

    The threshold keeps a stray config file or a one-off script from minting a
    skill badge.
    """
    grand = sum(totals.values()) or 1
    return {
        LANGUAGE_LABEL[language]
        for language, count in totals.items()
        if language in LANGUAGE_LABEL and count / grand >= min_share
    }
