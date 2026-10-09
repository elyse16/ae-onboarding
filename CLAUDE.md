# Sales Onboarding Hub

Single-file static site for TLDR AE onboarding.

- **Source:** `index.html` in this folder — one file, no build step, no dependencies.
- **Repo:** `elyse16/ae-onboarding` (public). **Live:** https://elyse16.github.io/ae-onboarding/
- **Deploy:** edit → commit → `git push origin main`. GitHub Pages serves `main` in ~1 min.
- **Always `git pull --rebase` first.** The remote gets updated between sessions.

## Gotchas

- **Do not edit `~/Documents/Claude/Artifacts/sales-onboarding-hub/index.html`.** It is a stale
  May 2026 artifact copy that does NOT match the deployed site. This folder is the only source.
- The Google Drive folder `.../Members/Elyse Wolin/projects/ae-onboarding/` holds only tracker
  `.xlsx` files, not the site source.
- `gh` auth for this repo is the `elyse16` account (not `ewolin@tldr.tech`).

## Structure

Six tabs, each a `.tab-content` div switched by `switchTab()`:
`program` (Weeks 1–4 schedule tables) · `reference` (TLDR at a Glance) · `playbook` ·
`resources` (numbered categories) · `exercises` · `smes`.

Week cards collapse via `toggleWeek()`, which already ignores clicks inside `.week-body`.

## Progress checkboxes

Every schedule row and exercise card carries `<input class="item-chk" data-id="...">`.
State is per-viewer `localStorage`, keyed `ae-onboarding:v1:<data-id>`. No backend, no accounts.

**The `data-id` is the contract.** It is deliberately decoupled from visible text so that
renaming a session, rewording a description, moving a row to another day, or reordering rows
never disturbs anyone's saved progress. Rules:

- New row → assign a new, never-used id (`w<week>-<slug>` for schedule, `ex-<slug>` for exercises).
- **Never change or recycle an existing `data-id`.** That is the only edit that silently resets
  someone's checkmark.
- Deleted rows leave orphaned keys; `progPrune()` clears them on next load. Nothing to do.
- Bump the `v1:` namespace only to deliberately reset everyone.

Storage is per-origin (`elyse16.github.io`), not per-path — hence the `ae-onboarding:` prefix.
All storage access is wrapped in try/catch so private browsing degrades to a visible warning.

## TLDR at a Glance — data sources

Refreshed from live data, not hand-typed. Stamp the pull date when you update it.

| Element | Source |
|---|---|
| Newsletter card headline number | `countDistinctIf(email, <nl>_subscribed)` over `clickhouse.readers` |
| Card open rate | 30-day avg from `clickhouse.sponsor_slots` (`sends`, `open_rate`) |
| Card "Rate card:" line | `rate_card_lookup` — the contractual figures proposals must quote |
| Audience Mix card | `rate_card_lookup` → `portfolio` |
| Per-newsletter audience profiles | `brief_config` section=newsletters |
| Top Sponsors table | `clickhouse.sponsor_slots`, trailing 90 days, excluding `is_archived` / `makegood` |

**Hard-won caveats:**

- `readers.stay_subscribed` is **not** an activity flag. True for only 1–2% of rows in every
  signup-year cohort back to 2018. Filtering on it undercounts ~45x. Never use it.
- 18 subscription flags exist; only **14 carry advertising**. The other four (Mobile Dev,
  Telecom, GameDev, Applied AI ≈ 424K) have never run a sponsorship and appear in no send data.
  Portfolio total 8.2M includes them; the 14 sellable newsletters sum to 7.78M; **2.65M unique
  humans** hold ~3.1 subscriptions each.
- `clickhouse.*` runs on ClickHouse natively: use `today()`, not `CURRENT_DATE`.
- The old "40% Executive Readers" stat was unsourced. Correct figure is 22% VP-or-C-level,
  corroborated by enriched reader seniority data.

## scripts/fetch_newsletter_subscribers.py

Refreshes the live subscriber counts. Needs VPN + `TLDR_TOOLS_BEARER` / `TLDR_TOOLS_COOKIE`.
**Not a daemon** — nothing updates unless it is run or scheduled.

It rewrites **only** each card's `nl-subs` value, the two stats-bar values, and the freshness
line. Cadence/open-rate, rate-card and audience lines are hand-maintained in `index.html` and
must survive a run. Legacy lists are summed into the total stat only (no cards; "Newsletters"
stat stays 14).

If the card markup or a stats-bar label changes, re-check `_RE_NL_CARD_SUBS`, `_RE_TOTAL`
(keyed on the "Total Subscriptions" label) and `_RE_NL_GRID`. Test offline before pushing:

```bash
python3 -c "import importlib.util,io;s=importlib.util.spec_from_file_location('m','scripts/fetch_newsletter_subscribers.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print('ok')"
```

## Conventions

- **Role-specific content is badged in place, never given its own tab.** Agency-only items carry
  `<span class="fmt fmt-agency">AGENCY AE ONLY</span>`. Precedent: Week 2 already routes by
  segment inline ("Stef's video for enterprise, Laura's for mid-market"). Say "Agency AE only"
  (the role), not "Agency" — Resources has agency-*topic* items meant for all AEs.
- Schedule rows stay in chronological order within a week.
- Async prep rows precede the live session they prepare for.
- Exercise rows say "See Exercises tab" and have a matching card there.

## Verifying changes

Tag-balance checks are not enough — they pass even when a card is nested inside another card.
Serve and inspect the live DOM:

```bash
python3 -m http.server 8799
```

Then check: every tab activates exactly one panel with non-zero height; new cards are direct
children of their tab, not nested; checkbox counts and `data-id` set are unchanged by unrelated
edits. For checkbox work, test edit-resilience by copying the file, renaming/moving/deleting
rows in the copy, and confirming ticks survive with zero false checkmarks.

## Open threads

- Week 1 still has a standalone "Call library sync — Week 1"; Week 2's is folded into the
  Manager 1:1 and Week 3's was removed. Inconsistent.
- The standing weekly Manager 1:1 row appears only in Week 2.
- "Agency book scoring" has an Exercises card but the Agency ICP Framework doc it scores against
  is marked WIP, with tier thresholds still "TBD".
- Tiering vocabulary collision: the ICP framework tiers agencies A/B/C/F, while the "Tier S-A
  Agency Account Mapper" uses S/A.
- Manager-visible progress would need auth, which means moving to SSO-gated pages.tldr.tech —
  the public repo cannot safely hold a backend.
