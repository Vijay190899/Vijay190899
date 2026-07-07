"""Generate the profile's metric cards as SVGs from the GitHub API.

Stdlib only. Produces two dark-themed cards in ./cards/:

- languages.svg  : donut chart of language share across public repos
- overview.svg   : big-number tiles (repos, stars, followers, commits)

Run: GITHUB_TOKEN=<token> python scripts/gen_cards.py
"""

import datetime
import json
import math
import os
import pathlib
import urllib.request

USER = "Vijay190899"
TOKEN = os.environ["GITHUB_TOKEN"]
OUT = pathlib.Path("cards")

BG = "#0d1117"
BORDER = "#30363d"
TEXT = "#c9d1d9"
MUTED = "#8b949e"
TITLE = "#58a6ff"

LANG_COLORS = {
    "Python": "#3572A5",
    "Jupyter Notebook": "#DA5B0B",
    "Shell": "#89e051",
    "Makefile": "#427819",
    "Dockerfile": "#384d54",
    "HTML": "#e34c26",
    "CSS": "#663399",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
}
FALLBACK_COLORS = ["#58a6ff", "#3fb950", "#d29922", "#f778ba", "#a371f7", "#f0883e"]
FONT = "font-family='Segoe UI, Ubuntu, Helvetica, Arial, sans-serif'"


def api(path: str):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": USER,
        },
    )
    with urllib.request.urlopen(req) as response:
        return json.load(response)


def card(width: int, height: int, title: str, body: str) -> str:
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' "
        f"viewBox='0 0 {width} {height}'>"
        f"<rect x='0.5' y='0.5' width='{width - 1}' height='{height - 1}' rx='6' "
        f"fill='{BG}' stroke='{BORDER}'/>"
        f"<text x='24' y='34' fill='{TITLE}' font-size='15' font-weight='600' {FONT}>{title}</text>"
        f"{body}</svg>"
    )


def donut_segments(shares: list[tuple[str, float, str]], cx: int, cy: int, r: int) -> str:
    circumference = 2 * math.pi * r
    offset = 0.0
    parts = []
    for _, fraction, color in shares:
        length = fraction * circumference
        parts.append(
            f"<circle cx='{cx}' cy='{cy}' r='{r}' fill='none' stroke='{color}' "
            f"stroke-width='26' stroke-dasharray='{length:.2f} {circumference - length:.2f}' "
            f"stroke-dashoffset='{-offset:.2f}' transform='rotate(-90 {cx} {cy})'/>"
        )
        offset += length
    return "".join(parts)


def build_languages_card() -> str:
    repos = [r for r in api(f"/users/{USER}/repos?per_page=100&type=owner") if not r["fork"]]
    totals: dict[str, int] = {}
    for repo in repos:
        for lang, size in api(f"/repos/{repo['full_name']}/languages").items():
            totals[lang] = totals.get(lang, 0) + size

    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:6]
    total = sum(size for _, size in ranked) or 1
    shares = []
    for i, (lang, size) in enumerate(ranked):
        color = LANG_COLORS.get(lang, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])
        shares.append((lang, size / total, color))

    body = [donut_segments(shares, cx=110, cy=130, r=62)]
    y = 78
    for lang, fraction, color in shares:
        body.append(f"<circle cx='222' cy='{y - 4}' r='5' fill='{color}'/>")
        body.append(
            f"<text x='236' y='{y}' fill='{TEXT}' font-size='13' {FONT}>{lang}"
            f"<tspan fill='{MUTED}'> {fraction * 100:.1f}%</tspan></text>"
        )
        y += 24
    return card(420, 220, "Most used languages", "".join(body))


def build_overview_card() -> str:
    user = api(f"/users/{USER}")
    repos = [r for r in api(f"/users/{USER}/repos?per_page=100&type=owner") if not r["fork"]]
    stars = sum(r["stargazers_count"] for r in repos)

    since = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
    try:
        commits = api(f"/search/commits?q=author:{USER}+author-date:>{since}")["total_count"]
    except Exception:
        commits = None

    tiles = [
        ("Public repos", str(user["public_repos"]), "#58a6ff"),
        ("Stars earned", str(stars), "#d29922"),
        ("Followers", str(user["followers"]), "#f778ba"),
        ("Commits, past year", str(commits) if commits is not None else "n/a", "#3fb950"),
    ]
    body = []
    positions = [(24, 70), (222, 70), (24, 150), (222, 150)]
    for (label, value, color), (x, y) in zip(tiles, positions):
        body.append(
            f"<text x='{x}' y='{y + 28}' fill='{color}' font-size='30' font-weight='700' {FONT}>"
            f"{value}</text>"
        )
        body.append(f"<text x='{x}' y='{y}' fill='{MUTED}' font-size='12' {FONT}>{label}</text>")
    return card(420, 220, "At a glance", "".join(body))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / "languages.svg").write_text(build_languages_card(), encoding="utf-8")
    (OUT / "overview.svg").write_text(build_overview_card(), encoding="utf-8")
    print("cards written to", OUT.resolve())


if __name__ == "__main__":
    main()
