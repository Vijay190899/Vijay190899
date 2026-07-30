# Profile README automation

Three parts of this README update themselves. Nothing here is hand-edited on a
normal day.

## What updates, and how

| Section | Source | Mechanism |
|---|---|---|
| Profile views counter | komarev.com | External image, updates on view |
| Streak card | `scripts/gen_cards.py` | SVG on the `metrics` branch, rebuilt by `cards.yml` |
| Frameworks and Tools card | `scripts/gen_cards.py` | SVG on the `metrics` branch, rebuilt by `cards.yml` |
| Pac-Man contribution graph | third-party action | SVG on the `output` branch, rebuilt by `pacman.yml` |
| **Current work** table | `scripts/gen_readme.py` | Markdown between `<!-- CURRENT_WORK:START/END -->`, rewritten by `readme.yml` |
| **Stack** badges | `scripts/gen_readme.py` | Markdown between `<!-- STACK:START/END -->`, rewritten by `readme.yml` |

The image cards can update in place because they are images. Current work and
Stack are markdown with real links, so they cannot be an image; instead a
workflow regenerates them and commits the README back (with `[skip ci]` so the
commit never re-triggers the workflow).

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
  *adds* to it: any tech detected across recent repos that maps to a known
  badge and is not already listed gets appended to its category. It never
  removes a badge, so curated skills stay visible.

To feature a different project, edit `FEATURED`. To add a badge the detector
should recognize, add it to `BADGE`, `TECH_TOKENS`, and (if not in the
baseline) `LABEL_CATEGORY`.

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
