"""Generate the profile's metric cards as SVGs.

Stdlib only. Produces two dark-themed cards in ./cards/:

- streak.svg     : total contributions, current streak (flame ring), longest streak
- frameworks.svg : frameworks/tools across recent repos, stacked bar with legend

Contribution counts come from GitHub's public per-user contributions calendar;
framework usage is detected from repo manifests (pyproject.toml, Dockerfile,
CI workflows) for repos created on/after REPO_CUTOFF.

Run: GITHUB_TOKEN=<token> python scripts/gen_cards.py
"""

import base64
import datetime
import json
import os
import pathlib
import re
import urllib.request

USER = "Vijay190899"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = pathlib.Path("cards")

BG = "#0d1117"
BORDER = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#fb8c00"
FONT = "font-family='Segoe UI, Ubuntu, Helvetica, Arial, sans-serif'"

# Only repos created on or after this date count toward the frameworks card
# (keeps old notebook-era repos from skewing the picture).
REPO_CUTOFF = "2025-01-01"

GRADIENTS = (
    "<defs>"
    "<linearGradient id='gTotal' x1='0' y1='0' x2='1' y2='1'>"
    "<stop offset='0%' stop-color='#58a6ff'/><stop offset='100%' stop-color='#bc8cff'/>"
    "</linearGradient>"
    "<linearGradient id='gStreak' x1='0' y1='0' x2='0' y2='1'>"
    "<stop offset='0%' stop-color='#ffb347'/><stop offset='100%' stop-color='#ff5252'/>"
    "</linearGradient>"
    "<linearGradient id='gLongest' x1='0' y1='0' x2='1' y2='1'>"
    "<stop offset='0%' stop-color='#56d364'/><stop offset='100%' stop-color='#39d3d3'/>"
    "</linearGradient>"
    "<linearGradient id='gBorder' x1='0' y1='0' x2='1' y2='0'>"
    "<stop offset='0%' stop-color='#58a6ff'/><stop offset='50%' stop-color='#bc8cff'/>"
    "<stop offset='100%' stop-color='#ff9800'/>"
    "</linearGradient>"
    "<linearGradient id='gTitle' x1='0' y1='0' x2='1' y2='0'>"
    "<stop offset='0%' stop-color='#ff9800'/><stop offset='100%' stop-color='#f778ba'/>"
    "</linearGradient>"
    "</defs>"
)

# Framework detection: token searched in repo manifests -> (label, color).
# Deliberately excludes uniform tooling (pytest, ruff, CI): present in every
# repo, so it carries no information here. Dict order breaks ranking ties.
FRAMEWORKS = {
    "langgraph": ("LangGraph", "#4db6ac"),
    "crewai": ("CrewAI", "#ff5a50"),
    "langchain": ("LangChain", "#86efac"),
    "mcp": ("MCP", "#ffa657"),
    "openai": ("OpenAI", "#74aa9c"),
    "fastapi": ("FastAPI", "#009688"),
    "langfuse": ("Langfuse", "#bc8cff"),
    "qdrant": ("Qdrant", "#dc244c"),
    "redis": ("Redis", "#ff4438"),
    "pydantic": ("Pydantic", "#e92063"),
}
DOCKER_COLOR = "#2496ed"

WORDS_TO_NUM = {"No": 0}


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


# --- contribution data --------------------------------------------------------


def contribution_days() -> dict[datetime.date, int]:
    """Daily contribution counts from account creation until today."""
    created = datetime.date.fromisoformat(api(f"/users/{USER}")["created_at"][:10])
    today = datetime.date.today()
    days: dict[datetime.date, int] = {}
    for year in range(created.year, today.year + 1):
        html = http_get(
            f"https://github.com/users/{USER}/contributions"
            f"?from={year}-01-01&to={year}-12-31"
        )
        # Map cell ids to dates, then tooltip text (which carries the count)
        # back to those ids.
        id_to_date = dict(
            re.findall(r'data-date="(\d{4}-\d{2}-\d{2})" id="([^"]+)"', html)
        )
        id_to_date = {v: k for k, v in id_to_date.items()}
        if not id_to_date:
            id_to_date = {
                cell_id: date
                for date, cell_id in re.findall(
                    r'id="([^"]+)"[^>]*data-date="(\d{4}-\d{2}-\d{2})"', html
                )
            }
        for cell_id, text in re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]+)</tool-tip>', html):
            date_str = id_to_date.get(cell_id)
            if not date_str:
                continue
            match = re.match(r"(\d+|No) contribution", text.strip())
            if not match:
                continue
            raw = match.group(1)
            count = WORDS_TO_NUM.get(raw, None)
            days[datetime.date.fromisoformat(date_str)] = (
                int(raw) if count is None else count
            )
    return {d: c for d, c in days.items() if d <= today}


def streaks(days: dict[datetime.date, int]):
    today = datetime.date.today()
    active = sorted(d for d, c in days.items() if c > 0)
    total = sum(days.values())
    first = active[0] if active else today

    # Longest run of consecutive active days.
    longest, longest_range = 0, (today, today)
    run_start = None
    prev = None
    for day in active:
        if prev is None or (day - prev).days > 1:
            run_start = day
        run_len = (day - run_start).days + 1
        if run_len > longest:
            longest, longest_range = run_len, (run_start, day)
        prev = day

    # Current streak: consecutive days ending today (or yesterday, when today
    # has no contributions yet).
    end = today if days.get(today, 0) > 0 else today - datetime.timedelta(days=1)
    current = 0
    cursor = end
    while days.get(cursor, 0) > 0:
        current += 1
        cursor -= datetime.timedelta(days=1)
    current_range = (cursor + datetime.timedelta(days=1), end) if current else (today, today)

    return {
        "total": total,
        "first": first,
        "current": current,
        "current_range": current_range,
        "longest": longest,
        "longest_range": longest_range,
    }


# --- rendering ----------------------------------------------------------------


def fmt(date: datetime.date) -> str:
    return f"{date.strftime('%b')} {date.day}, {date.year}"


def fmt_range(a: datetime.date, b: datetime.date) -> str:
    if a.year == b.year:
        return f"{a.strftime('%b')} {a.day} - {b.strftime('%b')} {b.day}"
    return f"{fmt(a)} - {fmt(b)}"


def card(width: int, height: int, body: str) -> str:
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' "
        f"viewBox='0 0 {width} {height}'>{GRADIENTS}"
        f"<rect x='1' y='1' width='{width - 2}' height='{height - 2}' rx='8' "
        f"fill='{BG}' stroke='url(#gBorder)' stroke-width='1.5'/>{body}</svg>"
    )


def build_streak_card(stats: dict) -> str:
    width, height = 740, 210
    col = width // 6
    body = []

    # Column dividers
    for x in (width // 3, 2 * width // 3):
        body.append(f"<line x1='{x}' y1='40' x2='{x}' y2='{height - 40}' stroke='{BORDER}'/>")

    # Left: total contributions
    body.append(
        f"<text x='{col}' y='92' text-anchor='middle' fill='url(#gTotal)' font-size='34' "
        f"font-weight='700' {FONT}>{stats['total']}</text>"
    )
    body.append(
        f"<text x='{col}' y='124' text-anchor='middle' fill='{TEXT}' font-size='15' {FONT}>"
        f"Total Contributions</text>"
    )
    body.append(
        f"<text x='{col}' y='152' text-anchor='middle' fill='{MUTED}' font-size='12' {FONT}>"
        f"{fmt(stats['first'])} - Present</text>"
    )

    # Middle: current streak inside a flame ring
    cx = 3 * col
    body.append(
        f"<circle cx='{cx}' cy='92' r='44' fill='none' stroke='url(#gStreak)' stroke-width='5'/>"
    )
    # Small flame at the top of the ring
    body.append(
        f"<path d='M {cx} 34 c -5 8 -8 11 -8 17 a 8 8 0 0 0 16 0 c 0 -6 -3 -9 -8 -17 z' "
        f"fill='{BG}' stroke='url(#gStreak)' stroke-width='3'/>"
    )
    body.append(
        f"<text x='{cx}' y='103' text-anchor='middle' fill='{TEXT}' font-size='32' "
        f"font-weight='700' {FONT}>{stats['current']}</text>"
    )
    body.append(
        f"<text x='{cx}' y='163' text-anchor='middle' fill='{ACCENT}' font-size='15' "
        f"font-weight='700' {FONT}>Current Streak</text>"
    )
    body.append(
        f"<text x='{cx}' y='188' text-anchor='middle' fill='{MUTED}' font-size='12' {FONT}>"
        f"{fmt_range(*stats['current_range'])}</text>"
    )

    # Right: longest streak
    body.append(
        f"<text x='{5 * col}' y='92' text-anchor='middle' fill='url(#gLongest)' font-size='34' "
        f"font-weight='700' {FONT}>{stats['longest']}</text>"
    )
    body.append(
        f"<text x='{5 * col}' y='124' text-anchor='middle' fill='{TEXT}' font-size='15' {FONT}>"
        f"Longest Streak</text>"
    )
    body.append(
        f"<text x='{5 * col}' y='152' text-anchor='middle' fill='{MUTED}' font-size='12' {FONT}>"
        f"{fmt_range(*stats['longest_range'])}</text>"
    )
    return card(width, height, "".join(body))


def repo_file(full_name: str, path: str) -> str:
    """A file's text content, or empty string when it doesn't exist."""
    try:
        payload = api(f"/repos/{full_name}/contents/{path}")
        return base64.b64decode(payload["content"]).decode(errors="ignore")
    except Exception:
        return ""


def framework_usage() -> list[tuple[str, float, str]]:
    """(label, share, color) for frameworks/tools across recent repos.

    A framework counts once per repo where it appears in the dependency
    manifest; Docker counts by Dockerfile presence. Shares are fractions of
    all mentions. Only repos created on/after REPO_CUTOFF count.
    """
    repos = [
        r
        for r in api(f"/users/{USER}/repos?per_page=100&type=owner")
        if not r["fork"] and r["created_at"][:10] >= REPO_CUTOFF
    ]
    counts: dict[str, tuple[int, str]] = {}

    def bump(label: str, color: str) -> None:
        count, _ = counts.get(label, (0, color))
        counts[label] = (count + 1, color)

    for repo in repos:
        manifest = repo_file(repo["full_name"], "pyproject.toml")
        for token, (label, color) in FRAMEWORKS.items():
            if re.search(rf"\b{token}", manifest):
                bump(label, color)
        if repo_file(repo["full_name"], "Dockerfile"):
            bump("Docker", DOCKER_COLOR)

    # Rank by mentions; break ties by FRAMEWORKS order so the agentic stack
    # (LangGraph, CrewAI, MCP...) outranks supporting libraries.
    priority = {label: i for i, (label, _) in enumerate(FRAMEWORKS.values())}
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1][0], priority.get(kv[0], 99)))[:10]
    total = sum(count for _, (count, _) in ranked) or 1
    return [(label, count / total, color) for label, (count, color) in ranked]


def build_frameworks_card() -> str:
    shares = framework_usage()
    width = 480
    rows = (len(shares) + 1) // 2
    height = 118 + rows * 34
    body = [
        f"<text x='24' y='42' fill='url(#gTitle)' font-size='20' font-weight='700' {FONT}>"
        f"Frameworks and Tools</text>"
    ]

    # Stacked bar
    bar_x, bar_y, bar_w, bar_h = 24, 64, width - 48, 12
    body.append(f"<clipPath id='bar'><rect x='{bar_x}' y='{bar_y}' width='{bar_w}' height='{bar_h}' rx='6'/></clipPath>")
    x = float(bar_x)
    for _, fraction, color in shares:
        seg = fraction * bar_w
        body.append(
            f"<rect x='{x:.1f}' y='{bar_y}' width='{seg + 1:.1f}' height='{bar_h}' "
            f"fill='{color}' clip-path='url(#bar)'/>"
        )
        x += seg

    # Two-column legend
    for i, (lang, fraction, color) in enumerate(shares):
        cx = 24 if i % 2 == 0 else width // 2 + 12
        cy = 108 + (i // 2) * 34
        body.append(f"<circle cx='{cx + 6}' cy='{cy - 5}' r='6' fill='{color}'/>")
        body.append(
            f"<text x='{cx + 22}' y='{cy}' fill='{TEXT}' font-size='14' {FONT}>{lang} "
            f"{fraction * 100:.2f}%</text>"
        )
    return card(width, height, "".join(body))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    stats = streaks(contribution_days())
    (OUT / "streak.svg").write_text(build_streak_card(stats), encoding="utf-8")
    (OUT / "frameworks.svg").write_text(build_frameworks_card(), encoding="utf-8")
    print(f"total={stats['total']} current={stats['current']} longest={stats['longest']}")


if __name__ == "__main__":
    main()
