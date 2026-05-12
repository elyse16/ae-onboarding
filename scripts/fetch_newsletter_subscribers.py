#!/usr/bin/env python3
"""
Fetch live TLDR newsletter subscriber counts from ClickHouse via Metabase
(internal tools API).

Requires network access to https://internal.tldr.tech (VPN / corp network).
If the endpoint returns 401/403, set auth via environment variables — see
--help or README in repo root if documented.

Does NOT filter on stay_subscribed (see product caveats). Uses readers.*_subscribed
booleans and webdev_subscribed for TLDR Dev only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

API_URL = "https://internal.tldr.tech/api/tools/call"

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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch newsletter subscriber counts via internal Metabase SQL tool.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a text table.",
    )
    args = parser.parse_args()

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
        return 1
    except urllib.error.URLError as e:
        sys.stderr.write(f"Request failed: {e}\n")
        return 1

    if status != 200:
        sys.stderr.write(f"Unexpected status {status}\n")
        return 1

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"Invalid JSON from API: {e}\n{raw[:2000]}\n")
        return 1

    if isinstance(payload, dict) and payload.get("error"):
        sys.stderr.write(f"API error: {payload.get('error')}\n{json.dumps(payload, indent=2)[:4000]}\n")
        return 1

    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, list) or not result:
        sys.stderr.write(f"Unexpected response shape (expected result: [{{...}}]):\n{raw[:4000]}\n")
        return 1

    row = result[0]
    if not isinstance(row, dict):
        sys.stderr.write(f"Unexpected row type: {type(row)!r}\n")
        return 1

    try:
        counts = _parse_counts(row)
    except (KeyError, ValueError) as e:
        sys.stderr.write(f"Could not parse counts: {e}\n")
        return 1

    _print_table(counts, json_out=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
