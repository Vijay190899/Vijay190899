# Profile README automation

Most of this README updates itself. Nothing here is hand-edited on a normal day.

## What updates, and how

| Section | Source | Mechanism |
|---|---|---|
| Profile views counter | komarev.com | External image, updates on view |
| Streak card | `scripts/gen_cards.py` | SVG on the `metrics` branch, rebuilt by `cards.yml` |
| Frameworks and Tools card | `scripts/gen_cards.py` | SVG on the `metrics` branch, rebuilt by `cards.yml` |
| Languages card | `scripts/gen_cards.py` | SVG on the `metrics` branch, rebuilt by `cards.yml` |
| Pac-Man contribution graph | third-party action | SVG on the `output` branch, rebuilt by `pacman.yml` |
| **Current work** table | `scripts/gen_readme.py` | Markdown between `<!-- CURRENT_WORK:START/END -->`, rewritten by `readme.yml` |
| **Stack** badges | `scripts/gen_readme.py` | Markdown between `<!-- STACK:START/END -->`, rewritten by `readme.yml` |

The image cards can update in place because they are images. Current work and
Stack are markdown with real links, so they cannot be an image; instead a
workflow regenerates them and commits the README back (with `[skip ci]` so the
commit never re-triggers the workflow).

## ghdata.py: where the data comes from

Both generators import `scripts/ghdata.py`, so the cards and the badges always
describe the same repositories with the same rules.

**Which repos count.** Every owned, non-fork repo created on or after
`REPO_CUTOFF` (2025-01-01), private ones included. This profile repo is
excluded from its own statistics: its README lists every badge, so scanning it
would feed the generated Stack back into detection and each run would confirm
itself.

**How a stack is detected**, in order of confidence:

1. *File layout* — `PATH_SIGNALS` proves a tech from a path alone and costs no
   extra API call: `*.tf` means Terraform, `next.config.*` means Next.js,
   `.github/workflows/*.yml` means GitHub Actions.
2. *Manifests* — `pyproject.toml`, `requirements*.txt`, `package.json`,
   `go.mod`, `wrangler.toml`, compose files and friends, found **anywhere** in
   the tree rather than only at the root, because most repos here keep them
   nested (`backend/pyproject.toml`, `frontend/package.json`).
3. *README, only when a repo declares no manifest at all* — the paper repos are
   a README plus code. Tokens listed in `AMBIGUOUS` (`react`, `next`, `helm`…)
   are suppressed for this pass so English prose cannot mint a skill.

A token is a literal matched on a word boundary unless it is written
`re:<pattern>`, which is used as a raw regex. That escape exists because a bare
`next` also matches `NEXTAUTH_SECRET`.

**Languages** come from GitHub's own byte tally per repo, summed across all of
them. Generated files GitHub counts as languages (`BibTeX Style`, `Makefile`)
are dropped, and a language must hold at least 1% of all bytes before it earns
a badge.

### Private repos

Private repos feed the **aggregate only**: framework counts, language bytes,
and the repo total. No private repo name, description, or file content is ever
written to the README or a card. The Current work table is a curated allowlist
of public repos, and a repo that has since been made private is skipped rather
than named.

Reading them needs a token with `repo` scope: a workflow's default
`GITHUB_TOKEN` only sees this repository. Both workflows read

```yaml
GITHUB_TOKEN: ${{ secrets.METRICS_TOKEN || secrets.GITHUB_TOKEN }}
```

so setting a `METRICS_TOKEN` secret (a PAT with read access to your repos)
turns private coverage on, and removing it degrades to public-only instead of
failing. The card subtitles report how many repos were actually counted, which
is the quickest way to tell which mode a run used.

## gen_readme.py

Run locally with a token to preview:

```bash
GITHUB_TOKEN="$(gh auth token)" python scripts/gen_readme.py
```

- **Current work** is a curated allowlist (`FEATURED` in the script). Which
  projects appear is fixed by you; every row's link, description, and detected
  stack is pulled live, so a renamed repo or a new dependency shows up on the
  next run without touching the README. Descriptions come from `DESCRIPTIONS`
  (falling back to the repo's GitHub description); the signature infra labels
  come from `STACK_OVERRIDE`.
- **Stack** keeps the full curated baseline (`STACK_BASELINE`) and only ever
  *adds* to it: any tech detected across every repo that maps to a known badge
  and is not already listed gets appended to its category. It never removes a
  badge, so curated skills stay visible. A category with no labels at all is
  skipped rather than rendered empty.

To feature a different project, edit `FEATURED`. To teach the detector a new
tech, add one entry to `TECH` in `ghdata.py` — tokens, swatch colour, Stack
category, and badge URL live together, so nothing can be half-registered.
`in_card=False` keeps a label out of the frameworks card while still giving it
a badge; that is how near-uniform tooling (pytest, ruff, CI) and the languages
stay off a card they would otherwise crowd.

## gen_cards.py

```bash
GITHUB_TOKEN="$(gh auth token)" python scripts/gen_cards.py
```

Writes `cards/*.svg` (gitignored locally; published to the `metrics` branch by
CI) and prints what it measured, which is worth reading before pushing.

- **Streak** counts come from the public contributions calendar page, parsed
  from HTML because the REST API has no equivalent route. It needs no token.
- **Frameworks and Tools** ranks by *number of repos* a tech appears in, so a
  monorepo cannot outvote everything else. Ties break on `TECH` catalog order,
  which puts the agentic stack ahead of supporting libraries.
- **Languages** ranks by bytes written and drops anything under 0.5%, which
  would otherwise render as an invisible bar segment labelled "0.05%".

Both share-cards are drawn by the same `build_share_card`, so they stay
visually identical while measuring different things.

## Refresh cadence

`readme.yml` runs daily at 04:20 UTC, on manual dispatch, and on any push to
`main` (except README-only pushes). A push to a *different* repo cannot trigger
a workflow here, so the daily run is what keeps the sections current, the same
way the SVG cards refresh on a schedule.

### Optional: instant refresh on push to a project repo

To refresh the moment you push to a featured project instead of waiting for the
daily run, add this workflow to that project repo. It needs a
`PROFILE_DISPATCH_TOKEN` secret (a fine-grained PAT with `contents: write` or
the `repository_dispatch` permission on `Vijay190899/Vijay190899`):

```yaml
name: Refresh profile README
on:
  push:
    branches: [main]
permissions: {}
jobs:
  dispatch:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger profile refresh
        run: |
          curl -sf -X POST \
            -H "Authorization: Bearer ${{ secrets.PROFILE_DISPATCH_TOKEN }}" \
            -H "Accept: application/vnd.github+json" \
            https://api.github.com/repos/Vijay190899/Vijay190899/dispatches \
            -d '{"event_type":"refresh-readme"}'
```
