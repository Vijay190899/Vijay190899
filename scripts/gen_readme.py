"""Regenerate the dynamic sections of README.md from live GitHub data.

Stdlib only. Rewrites two marker-delimited blocks in README.md:

- CURRENT_WORK : a table of featured repos. The set of projects is curated
  (FEATURED below), but every row's link, description, and detected stack is
  pulled live, so the table can never drift out of sync with the repos.
- STACK        : the skill badges. STACK_BASELINE is always shown; any tech
  detected across recent repos that is not already listed gets appended to its
  category. The baseline is never shrunk, so curated skills stay visible.

The "Frameworks and Tools" card is a separate SVG produced by gen_cards.py;
this script does not touch it.

Run: GITHUB_TOKEN=<token> python scripts/gen_readme.py
"""

import json
import os
import pathlib
import re
import urllib.request

USER = "Vijay190899"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
README = pathlib.Path("README.md")

# Only repos created on/after this date feed the Stack auto-grow, matching
# gen_cards.py so old notebook-era repos do not resurface stale tech.
REPO_CUTOFF = "2025-01-01"

# --- curated allowlist for the Current work table -----------------------------
# Order here is the display order. Description falls back to the repo's live
# GitHub description when a repo is not listed in DESCRIPTIONS.
FEATURED = [
    "supply-chain-agent-orchestrator",
    "disclosure-rag",
    "llm-gateway-observability",
]

DESCRIPTIONS = {
    "supply-chain-agent-orchestrator": (
        "Multi-agent logistics disruption response with a durable human-approval "
        "gate, an MCP tool server, and a written LangGraph vs CrewAI benchmark"
    ),
    "disclosure-rag": (
        "Retrieval over financial filings that cites the exact page and region for "
        "every claim, with self-correction before answering"
    ),
    "llm-gateway-observability": (
        "A single gateway in front of LLM providers: semantic caching, guardrails, "
        "rate limits, cost and latency tracking"
    ),
}

# Infra/technique labels that no manifest reliably reveals. Unioned with the
# live-detected stack per featured repo so the column never loses them.
STACK_OVERRIDE = {
    "supply-chain-agent-orchestrator": ["SQLite"],
    "disclosure-rag": ["Hybrid retrieval"],
    "llm-gateway-observability": ["EKS", "Terraform"],
}

# --- badge markup -------------------------------------------------------------
# label -> shields.io <img> tag. Covers the curated baseline plus extras that
# auto-grow can surface. Kept verbatim so regeneration is a no-op when nothing
# changed.
BADGE = {
    "Python": "https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white",
    "PyTorch": "https://img.shields.io/badge/PyTorch-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white",
    "Hugging Face": "https://img.shields.io/badge/Hugging_Face-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black",
    "LangChain": "https://img.shields.io/badge/LangChain-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white",
    "LangGraph": "https://img.shields.io/badge/LangGraph-1C3C3C?style=for-the-badge&logo=langgraph&logoColor=white",
    "CrewAI": "https://img.shields.io/badge/CrewAI-FF5A50?style=for-the-badge&logo=crewai&logoColor=white",
    "OpenAI": "https://img.shields.io/badge/OpenAI-412991?style=for-the-badge&logo=openai&logoColor=white",
    "MCP": "https://img.shields.io/badge/MCP-000000?style=for-the-badge&logo=modelcontextprotocol&logoColor=white",
    "Qdrant": "https://img.shields.io/badge/Qdrant-DC244C?style=for-the-badge&logo=qdrant&logoColor=white",
    "Langfuse": "https://img.shields.io/badge/Langfuse-000000?style=for-the-badge",
    "Anthropic": "https://img.shields.io/badge/Anthropic-191919?style=for-the-badge&logo=anthropic&logoColor=white",
    "Groq": "https://img.shields.io/badge/Groq-F55036?style=for-the-badge&logo=groq&logoColor=white",
    "vLLM": "https://img.shields.io/badge/vLLM-000000?style=for-the-badge",
    "FastAPI": "https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white",
    "Pydantic": "https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge&logo=pydantic&logoColor=white",
    "PostgreSQL": "https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white",
    "Redis": "https://img.shields.io/badge/Redis-FF4438?style=for-the-badge&logo=redis&logoColor=white",
    "SQLite": "https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white",
    "NumPy": "https://img.shields.io/badge/NumPy-013243?style=for-the-badge&logo=numpy&logoColor=white",
    "Pandas": "https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white",
    "scikit-learn": "https://img.shields.io/badge/scikit--learn-F7931E?style=for-the-badge&logo=scikitlearn&logoColor=white",
    "Jupyter": "https://img.shields.io/badge/Jupyter-F37626?style=for-the-badge&logo=jupyter&logoColor=white",
    "Neo4j": "https://img.shields.io/badge/Neo4j-4581C3?style=for-the-badge&logo=neo4j&logoColor=white",
    "Chroma": "https://img.shields.io/badge/Chroma-FF6F61?style=for-the-badge",
    "Docker": "https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white",
    "Kubernetes": "https://img.shields.io/badge/Kubernetes-326CE5?style=for-the-badge&logo=kubernetes&logoColor=white",
    "Helm": "https://img.shields.io/badge/Helm-0F1689?style=for-the-badge&logo=helm&logoColor=white",
    "Terraform": "https://img.shields.io/badge/Terraform-844FBA?style=for-the-badge&logo=terraform&logoColor=white",
    "AWS": "https://img.shields.io/badge/AWS-232F3E?style=for-the-badge&logo=amazonwebservices&logoColor=white",
    "Google Cloud": "https://img.shields.io/badge/Google_Cloud-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white",
    "GitHub Actions": "https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white",
    "Linux": "https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black",
    "Git": "https://img.shields.io/badge/Git-F05032?style=for-the-badge&logo=git&logoColor=white",
    "uv": "https://img.shields.io/badge/uv-DE5FE9?style=for-the-badge&logo=uv&logoColor=white",
    "Ruff": "https://img.shields.io/badge/Ruff-D7FF64?style=for-the-badge&logo=ruff&logoColor=black",
    "Pytest": "https://img.shields.io/badge/Pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white",
    "Pre-commit": "https://img.shields.io/badge/Pre--commit-FAB040?style=for-the-badge&logo=precommit&logoColor=black",
    "Ragas": "https://img.shields.io/badge/Ragas-6E56CF?style=for-the-badge",
    "Streamlit": "https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white",
}

# Curated baseline: category -> labels always shown, in order. Mirrors the
# hand-authored Stack section so a no-change run is a true no-op.
STACK_BASELINE = [
    ("AI and agents", ["Python", "PyTorch", "Hugging Face", "LangChain", "LangGraph",
                       "CrewAI", "OpenAI", "MCP", "Qdrant", "Langfuse"]),
    ("Backend and data", ["FastAPI", "Pydantic", "PostgreSQL", "Redis", "SQLite",
                          "NumPy", "Pandas", "scikit-learn", "Jupyter"]),
    ("Cloud and operations", ["Docker", "Kubernetes", "Helm", "Terraform", "AWS",
                             "Google Cloud", "GitHub Actions", "Linux", "Git"]),
    ("Tooling and quality", ["uv", "Ruff", "Pytest", "Pre-commit"]),
]

# Where an auto-detected label lands if it is not already in the baseline.
LABEL_CATEGORY = {
    "Anthropic": "AI and agents", "Groq": "AI and agents", "vLLM": "AI and agents",
    "Neo4j": "Backend and data", "Chroma": "Backend and data",
    "Streamlit": "Backend and data",
    "Ragas": "Tooling and quality",
}

# Detection: manifest/topic token -> canonical label.
TECH_TOKENS = {
    "langgraph": "LangGraph", "crewai": "CrewAI", "langchain": "LangChain",
    "modelcontextprotocol": "MCP", "mcp": "MCP", "openai": "OpenAI",
    "fastapi": "FastAPI", "langfuse": "Langfuse", "qdrant": "Qdrant",
    "redis": "Redis", "pydantic": "Pydantic", "sqlite": "SQLite",
    "numpy": "NumPy", "pandas": "Pandas", "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn", "jupyter": "Jupyter", "pytorch": "PyTorch",
    "torch": "PyTorch", "huggingface": "Hugging Face", "transformers": "Hugging Face",
    "terraform": "Terraform", "kubernetes": "Kubernetes", "helm": "Helm",
    "anthropic": "Anthropic", "groq": "Groq", "chromadb": "Chroma",
    "chroma": "Chroma", "neo4j": "Neo4j", "streamlit": "Streamlit",
    "ragas": "Ragas", "vllm": "vLLM",
}

# Priority for ordering the per-repo Core stack column (lower shows first).
_MASTER = [label for _, labels in STACK_BASELINE for label in labels] + [
    "Anthropic", "Groq", "vLLM", "Neo4j", "Chroma", "Streamlit", "Ragas",
    "Hybrid retrieval", "EKS",
]
PRIORITY = {label: i for i, label in enumerate(_MASTER)}

START = "<!-- {0}:START -->"
END = "<!-- {0}:END -->"


def http_get(url: str, token: str = "") -> str:
    headers = {"User-Agent": USER}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/vnd.github+json"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as response:
        return response.read().decode()


def api(path: str):
    return json.loads(http_get(f"https://api.github.com{path}", TOKEN))


def repo_file(full_name: str, path: str) -> str:
    try:
        payload = api(f"/repos/{full_name}/contents/{path}")
        import base64

        return base64.b64decode(payload["content"]).decode(errors="ignore")
    except Exception:
        return ""


def detect_tech(repo: dict) -> set[str]:
    """Labels detected from a repo's manifests, Dockerfile, and topics."""
    full = repo["full_name"]
    blob = "\n".join(
        repo_file(full, p)
        for p in ("pyproject.toml", "requirements.txt", "package.json")
    ).lower()
    found: set[str] = set()
    for token, label in TECH_TOKENS.items():
        if re.search(rf"\b{re.escape(token)}", blob):
            found.add(label)
    for topic in repo.get("topics", []):
        label = TECH_TOKENS.get(topic.lower().replace("-", ""))
        if label:
            found.add(label)
    if repo_file(full, "Dockerfile"):
        found.add("Docker")
    return found


def core_stack(name: str, repo: dict, cap: int = 6) -> list[str]:
    """Detected tech first (by priority), with the curated signature labels
    (SQLite, EKS, Terraform, Hybrid retrieval) reserved so the cap never drops
    them."""
    override = [x for x in STACK_OVERRIDE.get(name, [])]
    detected = sorted(detect_tech(repo), key=lambda label: PRIORITY.get(label, 999))
    detected = [x for x in detected if x not in override]
    kept = detected[: max(0, cap - len(override))]
    return kept + override


def render_current_work(repo_by_name: dict) -> str:
    rows = ["| Project | What it does | Core stack |", "|---|---|---|"]
    for name in FEATURED:
        repo = repo_by_name.get(name) or api(f"/repos/{USER}/{name}")
        desc = DESCRIPTIONS.get(name) or repo.get("description") or ""
        stack = ", ".join(core_stack(name, repo)) or "-"
        rows.append(f"| [{name}]({repo['html_url']}) | {desc} | {stack} |")
    return "\n".join(rows)


def render_stack(detected: set[str]) -> str:
    blocks = []
    for category, baseline in STACK_BASELINE:
        shown = list(baseline)
        extras = sorted(
            (label for label in detected
             if LABEL_CATEGORY.get(label) == category
             and label not in shown and label in BADGE),
            key=lambda label: PRIORITY.get(label, 999),
        )
        shown.extend(extras)
        imgs = "\n".join(f'  <img src="{BADGE[label]}"/>' for label in shown if label in BADGE)
        blocks.append(f"**{category}**\n\n<p>\n{imgs}\n</p>")
    return "\n\n".join(blocks)


def replace_block(text: str, name: str, body: str) -> str:
    start, end = START.format(name), END.format(name)
    if start not in text or end not in text:
        raise SystemExit(f"markers for {name} not found in README.md")
    pre = text.split(start)[0]
    post = text.split(end, 1)[1]
    return f"{pre}{start}\n{body}\n{end}{post}"


def main() -> None:
    recent = [
        r
        for r in api(f"/users/{USER}/repos?per_page=100&type=owner")
        if not r["fork"] and r["created_at"][:10] >= REPO_CUTOFF
    ]
    repo_by_name = {r["name"]: r for r in recent}

    detected: set[str] = set()
    for repo in recent:
        detected |= detect_tech(repo)

    text = README.read_text(encoding="utf-8")
    text = replace_block(text, "CURRENT_WORK", render_current_work(repo_by_name))
    text = replace_block(text, "STACK", render_stack(detected))
    # Force LF so a Windows run and the Linux CI run produce identical bytes
    # (the repo is eol=lf); otherwise every run would rewrite the whole file.
    README.write_text(text, encoding="utf-8", newline="\n")

    added = sorted(l for l in detected if l in BADGE
                   and l not in {x for _, labels in STACK_BASELINE for x in labels})
    print(f"featured={len(FEATURED)} detected={len(detected)} "
          f"stack_additions={added or 'none'}")


if __name__ == "__main__":
    main()
