#!/usr/bin/env python3
"""
Fetch live TLDR newsletter subscriber counts from ClickHouse via Metabase
(internal tools API).

Requires network access to https://internal.tldr.tech (VPN / corp network).
If the endpoint returns 401/403, set auth via environment variables — see
--help.

Does NOT filter on stay_subscribed (see product caveats). Uses readers.*_subscribed
booleans and webdev_subscribed for TLDR Dev only.

**Does this update the hub on its own?** No. The hub only changes when you run this
script (e.g. manually) or when you schedule it (cron, launchd, GitHub Actions with a
runner that can reach internal.tldr.tech, etc.). There is no background daemon.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

API_URL = "https://internal.tldr.tech/api/tools/call"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX = REPO_ROOT / "index.html"

SQL = """
SELECT
  countDistinctIf(email, tech_subscribed)      AS tldr,
  countDistinctIf(email, ai_subscribed)        AS tldr_ai,
  countDistinctIf(email, data_subscribed)      AS tldr_data,
  countDistinctIf(email, it_subscribed)        AS tldr_it,
  countDistinctIf(email, webdev_subscribed)    AS tldr_dev,
  countDistinctIf(email, infosec_subscribed)   AS tldr_infosec,
  countDistinctIf(email, product_subscribed)   AS tldr_product,
  countDistinctIf(email, fintech_subscribed)   AS tldr_fintech,
  countDistinctIf(email, founders_subscribed)  AS tldr_founders,
  countDistinctIf(email, devops_subscribed)    AS tldr_devops,
  countDistinctIf(email, crypto_subscribed)    AS tldr_crypto,
  countDistinctIf(email, marketing_subscribed) AS tldr_marketing,
  countDistinctIf(email, design_subscribed)    AS tldr_design
FROM readers
""".strip()

# API field order / display labels (hub uses "TLDR InfoSec" for consistency)
NEWSLETTER_LABELS: list[tuple[str, str]] = [
    ("tldr", "TLDR"),
    ("tldr_ai", "TLDR AI"),
    ("tldr_data", "TLDR Data"),
    ("tldr_it", "TLDR IT"),
    ("tldr_dev", "TLDR Dev"),
    ("tldr_infosec", "TLDR InfoSec"),
    ("tldr_product", "TLDR Product"),
    ("tldr_fintech", "TLDR Fintech"),
    ("tldr_founders", "TLDR Founders"),
    ("tldr_devops", "TLDR DevOps"),
    ("tldr_crypto", "TLDR Crypto"),
    ("tldr_marketing", "TLDR Marketing"),
    ("tldr_design", "TLDR Design"),
]

# Cadence copy for TLDR at a Glance cards (not returned by the SQL API)
NL_FREQ_BY_LABEL: dict[str, str] = {
    "TLDR": "Mon–Fri",
    "TLDR AI": "Mon–Fri",
    "TLDR Data": "Mon & Thu",
    "TLDR IT": "Mon–Fri",
    "TLDR Dev": "Mon–Fri",
    "TLDR Fintech": "Mon & Thu",
    "TLDR Product": "Tue & Fri",
    "TLDR InfoSec": "Mon–Fri",
    "TLDR Founders": "Mon–Wed–Fri",
    "TLDR DevOps": "Mon–Wed–Fri",
    "TLDR Crypto": "Mon–Fri",
    "TLDR Marketing": "Mon–Fri",
    "TLDR Design": "Mon–Fri",
}


def _auth_headers() -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    bearer = os.environ.get("TLDR_TOOLS_BEARER", "").strip()
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    cookie = os.environ.get("TLDR_TOOLS_COOKIE", "").strip()
    if cookie:
        headers["Cookie"] = cookie
    return headers


def _parse_counts(row: dict[str, Any]) -> list[tuple[str, str, int]]:
    out: list[tuple[str, str, int]] = []
    for key, label in NEWSLETTER_LABELS:
        if key not in row:
            raise KeyError(f"Response row missing expected key {key!r}: {row!r}")
        raw = row[key]
        if raw is None:
            raise ValueError(f"Null count for {key}")
        n = int(str(raw).replace(",", "").strip())
        out.append((key, label, n))
    return out


def format_total_stat(sum_subs: int) -> str:
    """Match hub style (~7.05M): sum of per-newsletter distinct counts."""
    return f"~{sum_subs / 1e6:.2f}M"


def build_nl_grid_inner_html(rows_sorted: list[tuple[str, str, int]]) -> str:
    lines: list[str] = []
    for _, lab, n in rows_sorted:
        freq = NL_FREQ_BY_LABEL.get(lab, "Schedule varies")
        safe_lab = html.escape(lab)
        safe_freq = html.escape(freq)
        lines.append(
            f'      <div class="nl-card"><div class="nl-name">{safe_lab}</div>'
            f'<div class="nl-subs">{n:,}</div><div class="nl-freq">{safe_freq}</div></div>'
        )
    return "\n".join(lines)


def build_fragment_html(rows_sorted: list[tuple[str, str, int]]) -> str:
    """Pasteable snippet: inner HTML only (no wrapping nl-grid)."""
    return build_nl_grid_inner_html(rows_sorted)


_RE_TOTAL = re.compile(
    r'(<div class="stats-bar">\s*<div class="stat-card"><div class="stat-value">)([^<]+)(</div><div class="stat-label">Total Subscribers</div></div>)',
    re.DOTALL,
)
_RE_NEWSLETTER_COUNT = re.compile(
    r'(<div class="stat-card"><div class="stat-value">)(\d+)(</div><div class="stat-label">Newsletters</div></div>)',
    re.DOTALL,
)
_RE_NL_GRID = re.compile(
    r'(<div class="nl-grid">\n)(.*?)(\n    </div>\n    <div class="freshness" id="subscriber-counts-freshness">)',
    re.DOTALL,
)
_RE_FRESHNESS = re.compile(
    r'(<div class="freshness" id="subscriber-counts-freshness">)([^<]*)(</div>)',
)


def patch_index_html(
    html_text: str,
    rows: list[tuple[str, str, int]],
    *,
    dry_run: bool,
) -> tuple[str, list[str]]:
    """Return (new_html, log_lines). Raises ValueError if patterns do not match."""
    rows_sorted = sorted(rows, key=lambda r: r[2], reverse=True)
    total_sum = sum(r[2] for r in rows_sorted)
    new_total = format_total_stat(total_sum)
    n_newsletters = len(NEWSLETTER_LABELS)
    new_grid = build_nl_grid_inner_html(rows_sorted)
    today = date.today()
    freshness = f"Subscriber counts from Metabase — {today:%B} {today.day}, {today:%Y}"

    log: list[str] = []
    m1 = _RE_TOTAL.search(html_text)
    if not m1:
        raise ValueError("Could not find stats-bar total subscriber stat-value to replace.")
    m2 = _RE_NEWSLETTER_COUNT.search(html_text)
    if not m2:
        raise ValueError("Could not find Newsletters stat-value to replace.")
    m3 = _RE_NL_GRID.search(html_text)
    if not m3:
        raise ValueError("Could not find nl-grid block to replace (expected structure near freshness line).")

    out = html_text
    out, n_subs = _RE_TOTAL.subn(rf"\g<1>{new_total}\g<3>", out, count=1)
    if n_subs != 1:
        raise ValueError("Total subscribers regex replace failed.")
    log.append(f"Total stat: {new_total} (sum of column distinct counts = {total_sum:,})")

    out, n_cnt = _RE_NEWSLETTER_COUNT.subn(rf"\g<1>{n_newsletters}\g<3>", out, count=1)
    if n_cnt != 1:
        raise ValueError("Newsletters count regex replace failed.")
    log.append(f"Newsletter count stat: {n_newsletters}")

    out, n_grid = _RE_NL_GRID.subn(rf"\g<1>{new_grid}\g<3>", out, count=1)
    if n_grid != 1:
        raise ValueError("nl-grid regex replace failed.")
    log.append("nl-grid: replaced all newsletter cards (sorted by subscribers, descending).")

    m4 = _RE_FRESHNESS.search(out)
    if m4:
        out, n_f = _RE_FRESHNESS.subn(rf"\g<1>{freshness}\g<3>", out, count=1)
        if n_f == 1:
            log.append(f"Freshness line: {freshness}")
    else:
        log.append(
            "Warning: freshness div with id=subscriber-counts-freshness not found; skipped freshness update."
        )

    if dry_run:
        log.insert(0, "[dry-run] No file written.")
    return out, log


def fetch_counts() -> tuple[list[tuple[str, str, int]], str]:
    """Return (counts, raw_json_body)."""
    body = json.dumps(
        {"name": "metabase_execute_sql", "arguments": {"sql": SQL}}
    ).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers=_auth_headers(),
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            status = resp.getcode()
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        sys.stderr.write(
            f"HTTP {e.code} {e.reason} calling {API_URL}\n"
            f"Body: {e.read().decode('utf-8', errors='replace')[:2000]}\n"
        )
        if e.code in (401, 403):
            sys.stderr.write(
                "Hint: set TLDR_TOOLS_BEARER and/or TLDR_TOOLS_COOKIE if your org requires auth.\n"
            )
        raise
    except urllib.error.URLError as e:
        sys.stderr.write(f"Request failed: {e}\n")
        raise

    if status != 200:
        raise RuntimeError(f"Unexpected status {status}")

    payload = json.loads(raw)

    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(f"API error: {payload.get('error')}\n{json.dumps(payload, indent=2)[:4000]}")

    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, list) or not result:
        raise RuntimeError(f"Unexpected response shape:\n{raw[:4000]}")

    row = result[0]
    if not isinstance(row, dict):
        raise RuntimeError(f"Unexpected row type: {type(row)!r}")

    counts = _parse_counts(row)
    return counts, raw


def _print_table(rows: list[tuple[str, str, int]], *, json_out: bool) -> None:
    rows_sorted = sorted(rows, key=lambda r: r[2], reverse=True)
    if json_out:
        print(
            json.dumps(
                [{"field": k, "newsletter": lab, "subscribers": n} for k, lab, n in rows_sorted],
                indent=2,
            )
        )
        return

    w_name = max(len(lab) for _, lab, _ in rows_sorted)
    w_cnt = max(len(f"{n:,}") for _, _, n in rows_sorted)
    total = sum(n for _, _, n in rows_sorted)

    header = f"{'Newsletter'.ljust(w_name)}  {'Subscribers'.rjust(w_cnt)}"
    sep = "-" * len(header)
    print(header)
    print(sep)
    for _, lab, n in rows_sorted:
        print(f"{lab.ljust(w_name)}  {n:>{w_cnt},}")
    print(sep)
    print(f"{'Total (sum of columns)'.ljust(w_name)}  {total:>{w_cnt},}")


def _resolve_index_path(p: Path | None) -> Path:
    """Resolve path for --write-index (default: repo root index.html)."""
    if p is None:
        return DEFAULT_INDEX
    p = Path(p)
    if not p.is_absolute() and len(p.parts) == 1 and p.parts[0].lower() == "index.html":
        return DEFAULT_INDEX
    if p.is_absolute():
        return p
    cand = Path.cwd() / p
    if cand.exists():
        return cand.resolve()
    return (REPO_ROOT / p).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch newsletter subscriber counts via internal Metabase SQL tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Automation:
  This script does nothing until you run it. To refresh the hub on a schedule,
  use cron / launchd, or CI with a runner that can reach internal.tldr.tech and
  has TLDR_TOOLS_BEARER / TLDR_TOOLS_COOKIE if required.

Examples:
  python3 scripts/fetch_newsletter_subscribers.py
  python3 scripts/fetch_newsletter_subscribers.py --write-index
  python3 scripts/fetch_newsletter_subscribers.py --write-index --dry-run
  python3 scripts/fetch_newsletter_subscribers.py --fragment
""".strip(),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a text table.",
    )
    parser.add_argument(
        "--fragment",
        action="store_true",
        help="Print only the nl-grid inner HTML (for manual paste), then exit (no index write).",
    )
    parser.add_argument(
        "--write-index",
        nargs="?",
        const=Path("index.html"),
        default=None,
        metavar="PATH",
        help="Patch TLDR at a Glance in the hub index.html (default: %(const)s under repo root).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --write-index, show replacements but do not write the file.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Do not print the subscriber table (still prints patch logs when writing).",
    )
    args = parser.parse_args()

    write_requested = args.write_index is not None
    index_path = _resolve_index_path(args.write_index) if write_requested else None

    try:
        counts, _raw = fetch_counts()
    except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError, json.JSONDecodeError, KeyError, ValueError) as e:
        sys.stderr.write(f"{e}\n")
        return 1

    rows_sorted = sorted(counts, key=lambda r: r[2], reverse=True)

    if args.fragment:
        print(build_fragment_html(rows_sorted))
        return 0

    if args.json:
        _print_table(counts, json_out=True)
    elif not args.quiet:
        _print_table(counts, json_out=False)

    if write_requested:
        assert index_path is not None
        if not index_path.exists():
            sys.stderr.write(f"Index file not found: {index_path}\n")
            return 1
        html_text = index_path.read_text(encoding="utf-8")
        try:
            new_html, log_lines = patch_index_html(html_text, counts, dry_run=args.dry_run)
        except ValueError as e:
            sys.stderr.write(f"{e}\n")
            return 1
        for line in log_lines:
            print(line, file=sys.stderr)
        if args.dry_run:
            return 0
        index_path.write_text(new_html, encoding="utf-8")
        print(f"Wrote {index_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
