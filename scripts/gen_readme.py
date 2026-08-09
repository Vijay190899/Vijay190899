"""Regenerate the dynamic sections of README.md from live GitHub data.

Stdlib only. Rewrites two marker-delimited blocks in README.md:

- CURRENT_WORK : a table of featured repos. The set of projects is curated
  (FEATURED below) and public by construction, but every row's link,
  description, and detected stack is pulled live, so the table can never drift
  out of sync with the repos.
- STACK        : the skill badges. STACK_BASELINE is always shown; any tech
  detected across every repo, private ones included, that is not already listed
  gets appended to its category. The baseline is never shrunk, so curated
  skills stay visible.

Detection, the repo list, and the tech catalog live in ghdata.py and are shared
with gen_cards.py. Private repos contribute badges only: no private name or
description is ever written here.

Run: GITHUB_TOKEN=<token> python scripts/gen_readme.py
"""

import pathlib

import ghdata
from ghdata import TECH, USER

README = pathlib.Path("README.md")

# --- curated allowlist for the Current work table -----------------------------
# Order here is the display order. Description falls back to the repo's live
# GitHub description when a repo is not listed in DESCRIPTIONS. Every entry must
# be a public repo; private ones are skipped at render time.
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

# Curated baseline: category -> labels always shown, in order. Categories render
# in this order; one with no labels at all is skipped.
#
# Groq, Matplotlib and LaTeX are evidenced only in private repos, so a run
# without a METRICS_TOKEN cannot rediscover them. They are curated here rather
# than left to auto-grow, which is exactly what a baseline that never shrinks is
# for: the skill stays visible whether or not the run could see the repo that
# proves it.
STACK_BASELINE = [
    ("AI and agents", ["Python", "PyTorch", "Hugging Face", "LangChain", "LangGraph",
                       "CrewAI", "OpenAI", "MCP", "Qdrant", "Langfuse", "Groq"]),
    ("Backend and data", ["FastAPI", "Pydantic", "PostgreSQL", "Redis", "SQLite",
                          "NumPy", "Pandas", "scikit-learn", "Jupyter",
                          "Matplotlib"]),
    ("Web and interfaces", ["TypeScript", "JavaScript", "React", "Next.js",
                            "Tailwind"]),
    ("Cloud and operations", ["Docker", "Kubernetes", "Helm", "Terraform", "AWS",
                              "Google Cloud", "GitHub Actions", "Linux", "Git"]),
    ("Tooling and quality", ["uv", "Ruff", "Pytest", "Pre-commit", "LaTeX"]),
]

BASELINE_LABELS = {label for _, labels in STACK_BASELINE for label in labels}

# Labels with no badge of their own, used only in the Current work stack column.
EXTRA_PRIORITY = ["Hybrid retrieval", "EKS"]
PRIORITY = dict(ghdata.PRIORITY)
PRIORITY.update({label: len(PRIORITY) + i for i, label in enumerate(EXTRA_PRIORITY)})

START = "<!-- {0}:START -->"
END = "<!-- {0}:END -->"


def core_stack(name: str, repo: dict, cap: int = 6) -> list[str]:
    """Detected tech first (by catalog order), with the curated signature labels
    (SQLite, EKS, Terraform, Hybrid retrieval) reserved so the cap never drops
    them."""
    override = list(STACK_OVERRIDE.get(name, []))
    detected = sorted(ghdata.detect_tech(repo), key=lambda l: PRIORITY.get(l, 999))
    detected = [x for x in detected if x not in override]
    kept = detected[: max(0, cap - len(override))]
    return kept + override


def render_current_work(repo_by_name: dict) -> str:
    rows = ["| Project | What it does | Core stack |", "|---|---|---|"]
    for name in FEATURED:
        repo = repo_by_name.get(name) or ghdata.api(f"/repos/{USER}/{name}")
        # A featured repo that has been made private must not be named here.
        if repo.get("private"):
            continue
        desc = DESCRIPTIONS.get(name) or repo.get("description") or ""
        stack = ", ".join(core_stack(name, repo)) or "-"
        rows.append(f"| [{name}]({repo['html_url']}) | {desc} | {stack} |")
    return "\n".join(rows)


def render_stack(detected: set[str]) -> str:
    blocks = []
    for category, baseline in STACK_BASELINE:
        shown = list(baseline)
        # Checked against the whole baseline, not just this category: a curated
        # label may sit in a different section than its catalog category (Qdrant
        # is filed under AI and agents here), and it must not be listed twice.
        extras = sorted(
            (label for label in detected
             if label not in BASELINE_LABELS
             and label in TECH
             and TECH[label].category == category
             and TECH[label].badge),
            key=lambda label: PRIORITY.get(label, 999),
        )
        shown.extend(extras)
        imgs = "\n".join(
            f'  <img src="{TECH[label].badge}"/>'
            for label in shown
            if label in TECH and TECH[label].badge
        )
        if imgs:
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
    repos = ghdata.owned_repos()
    repo_by_name = {r["name"]: r for r in repos}

    detected: set[str] = set()
    for repo in repos:
        detected |= ghdata.detect_tech(repo)
    # Languages earn a badge on byte share, so Go or TypeScript shows up even
    # where no manifest names it.
    detected |= ghdata.language_labels(ghdata.language_bytes(repos))

    text = README.read_text(encoding="utf-8")
    text = replace_block(text, "CURRENT_WORK", render_current_work(repo_by_name))
    text = replace_block(text, "STACK", render_stack(detected))
    # Force LF so a Windows run and the Linux CI run produce identical bytes
    # (the repo is eol=lf); otherwise every run would rewrite the whole file.
    README.write_text(text, encoding="utf-8", newline="\n")

    added = sorted(l for l in detected if l in TECH and TECH[l].badge
                   and l not in BASELINE_LABELS)
    print(f"repos={len(repos)} featured={len(FEATURED)} detected={len(detected)} "
          f"stack_additions={added or 'none'}")


if __name__ == "__main__":
    main()
