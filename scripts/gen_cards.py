"""Generate the profile's metric cards as SVGs.

Stdlib only. Produces three dark-themed cards in ./cards/:

- streak.svg     : total contributions, current streak (flame ring), longest streak
- frameworks.svg : frameworks and tools across every repo, stacked bar with legend
- languages.svg  : languages by bytes written across every repo

Contribution counts come from GitHub's public per-user contributions calendar.
The other two cards are built from every owned repo created on/after
REPO_CUTOFF, private ones included: see ghdata.py for how a repo's stack is
detected and what does (and does not) leave a private repo.

Run: GITHUB_TOKEN=<token> python scripts/gen_cards.py
"""

import collections
import datetime
import pathlib
import re

import ghdata
from ghdata import USER

OUT = pathlib.Path("cards")

# Legend slots per card. Two columns, so an even number fills the last row.
CARD_ITEMS = 12

BG = "#0d1117"
BORDER = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#fb8c00"
FONT = "font-family='Segoe UI, Ubuntu, Helvetica, Arial, sans-serif'"

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

WORDS_TO_NUM = {"No": 0}

# --- contribution data --------------------------------------------------------


def contribution_days() -> dict[datetime.date, int]:
    """Daily contribution counts from account creation until today."""
    created = datetime.date.fromisoformat(
        ghdata.api(f"/users/{USER}")["created_at"][:10]
    )
    today = datetime.date.today()
    days: dict[datetime.date, int] = {}
    for year in range(created.year, today.year + 1):
        # Public calendar page, no token: the API has no equivalent REST route.
        html = ghdata.http_get(
            f"https://github.com/users/{USER}/contributions"
            f"?from={year}-01-01&to={year}-12-31",
            token="",
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


def build_share_card(title: str, subtitle: str, shares: list[tuple[str, float, str]],
                     bar_id: str, width: int = 520) -> str:
    """A titled stacked bar over a two-column legend.

    `shares` is (label, fraction, color), already ranked and normalised. Both
    the frameworks and the languages card are this shape, so they stay visually
    identical while measuring different things.
    """
    rows = (len(shares) + 1) // 2
    height = 96 + rows * 34
    body = [
        f"<text x='24' y='40' fill='url(#gTitle)' font-size='20' font-weight='700' "
        f"{FONT}>{title}</text>",
        f"<text x='24' y='60' fill='{MUTED}' font-size='12' {FONT}>{subtitle}</text>",
    ]

    # Stacked bar. Segments overlap by 1px so hairline gaps never show between
    # them; the clip path keeps the rounded ends clean.
    bar_x, bar_y, bar_w, bar_h = 24, 74, width - 48, 12
    body.append(
        f"<clipPath id='{bar_id}'><rect x='{bar_x}' y='{bar_y}' width='{bar_w}' "
        f"height='{bar_h}' rx='6'/></clipPath>"
    )
    x = float(bar_x)
    for _, fraction, color in shares:
        seg = fraction * bar_w
        body.append(
            f"<rect x='{x:.1f}' y='{bar_y}' width='{seg + 1:.1f}' height='{bar_h}' "
            f"fill='{color}' clip-path='url(#{bar_id})'/>"
        )
        x += seg

    for i, (label, fraction, color) in enumerate(shares):
        cx = 24 if i % 2 == 0 else width // 2 + 12
        cy = 116 + (i // 2) * 34
        body.append(f"<circle cx='{cx + 6}' cy='{cy - 5}' r='6' fill='{color}'/>")
        body.append(
            f"<text x='{cx + 22}' y='{cy}' fill='{TEXT}' font-size='14' {FONT}>"
            f"{escape(label)} {fraction * 100:.2f}%</text>"
        )
    return card(width, height, "".join(body))


def framework_shares(repos: list[dict]) -> list[tuple[str, float, str]]:
    """(label, share, color) for frameworks and tools across every repo.

    A framework counts once per repo it appears in, so a monorepo cannot
    outvote the rest. Shares are fractions of the mentions actually shown.
    """
    counts: collections.Counter[str] = collections.Counter()
    for repo in repos:
        counts.update(
            label for label in ghdata.detect_tech(repo) if ghdata.TECH[label].in_card
        )

    # Rank by repo count; break ties on catalog order so the agentic stack
    # (LangGraph, CrewAI, MCP...) outranks supporting libraries.
    ranked = sorted(
        counts.items(), key=lambda kv: (-kv[1], ghdata.PRIORITY.get(kv[0], 999))
    )[:CARD_ITEMS]
    total = sum(count for _, count in ranked) or 1
    return [(label, count / total, ghdata.TECH[label].color) for label, count in ranked]


def language_shares(totals: dict[str, int],
                    min_share: float = 0.005) -> list[tuple[str, float, str]]:
    """(language, share, color) by bytes written, largest first.

    Languages under `min_share` of the total are dropped rather than listed at
    "0.05%", which reads as noise and renders as an invisible bar segment. The
    remaining shares are renormalised so the legend sums to 100%.
    """
    grand = sum(totals.values()) or 1
    ranked = [
        (name, count) for name, count in totals.items()
        if count / grand >= min_share
    ][:CARD_ITEMS]
    total = sum(count for _, count in ranked) or 1
    return [
        (name, count / total, ghdata.LANGUAGE_COLOR.get(name, ghdata.LANGUAGE_FALLBACK))
        for name, count in ranked
    ]


def escape(text: str) -> str:
    """XML-escape a label. Catalog entries are hand-written, but language names
    come from the API and must not be able to break the document."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def main() -> None:
    OUT.mkdir(exist_ok=True)
    stats = streaks(contribution_days())
    (OUT / "streak.svg").write_text(build_streak_card(stats), encoding="utf-8")

    repos = ghdata.owned_repos()
    private = sum(1 for r in repos if r.get("private"))
    scope = f"across {len(repos)} repositories"
    if private:
        scope += f", {private} of them private"

    frameworks = framework_shares(repos)
    (OUT / "frameworks.svg").write_text(
        build_share_card("Frameworks and Tools", scope, frameworks, "barFw"),
        encoding="utf-8",
    )

    languages = language_shares(ghdata.language_bytes(repos))
    (OUT / "languages.svg").write_text(
        build_share_card("Languages", f"by bytes written, {scope}", languages,
                         "barLang"),
        encoding="utf-8",
    )

    print(
        f"total={stats['total']} current={stats['current']} "
        f"longest={stats['longest']} repos={len(repos)} "
        f"frameworks={[l for l, _, _ in frameworks]} "
        f"languages={[l for l, _, _ in languages]}"
    )


if __name__ == "__main__":
    main()
