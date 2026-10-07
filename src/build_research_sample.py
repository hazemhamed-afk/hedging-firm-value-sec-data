#!/usr/bin/env python3
"""
Build the final point-in-time S&P 500 research sample from SEC Company Facts.

Inputs
------
data/research_sample_issuers_2010_2025.csv
data/research_sample_membership_intervals_2010_2025.csv
SEC bulk Company Facts archive (companyfacts.zip) OR an extracted directory.

Outputs
-------
data/research_sample_firmyears_2010_2025.csv
data/research_sample_screening_summary_2010_2025.csv
data/research_sample_missing_companyfacts_2010_2025.csv

Design
------
* Universe is defined ex ante by historical S&P 500 membership.
* Financials, Utilities, and Real Estate have already been removed upstream.
* Firm-year is retained only when the fiscal-year-end falls inside a membership interval.
* Requires an annual 10-K/10-K/A Company Facts observation and US-GAAP namespace.
* 20-F/40-F-only foreign private issuers therefore fail the annual-form screen.
* Acquired/delisted firms are retained through their final eligible public year.
* Hedge status is never used to determine inclusion.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import zipfile

START_DATE = date(2010, 1, 1)
END_DATE = date(2025, 12, 31)
ANNUAL_FORMS = {"10-K", "10-K/A"}


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def normalize_cik(value: str) -> str:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits.zfill(10)


@dataclass(frozen=True)
class Interval:
    start: date
    end: date | None

    def contains(self, d: date) -> bool:
        return self.start <= d and (self.end is None or d <= self.end)


def load_intervals(path: Path) -> dict[str, list[Interval]]:
    out: dict[str, list[Interval]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cik = normalize_cik(row["cik"])
            start = parse_date(row["date_added"])
            end = parse_date(row.get("date_removed"))
            if start:
                out[cik].append(Interval(start, end))
    return out


def load_issuers(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class CompanyFactsSource:
    def __init__(self, source: Path):
        self.source = source
        self._zip = zipfile.ZipFile(source) if source.is_file() else None
        if self._zip:
            self._names = set(self._zip.namelist())

    def read(self, cik: str) -> dict | None:
        filename = f"CIK{normalize_cik(cik)}.json"
        if self._zip:
            candidates = [filename, f"companyfacts/{filename}"]
            name = next((x for x in candidates if x in self._names), None)
            if not name:
                return None
            with self._zip.open(name) as fh:
                return json.load(io.TextIOWrapper(fh, encoding="utf-8"))
        path = self.source / filename
        if not path.exists():
            path = self.source / "companyfacts" / filename
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def close(self):
        if self._zip:
            self._zip.close()


def canonical_annual_filings(companyfacts: dict) -> list[dict]:
    """
    Infer one canonical annual filing per fiscal year from repeated US-GAAP
    Company Facts observations. Frequency across tags identifies the annual
    report/end-date/accession combination. Amendments are allowed but base
    10-K is preferred when the evidence count is tied.
    """
    usgaap = companyfacts.get("facts", {}).get("us-gaap", {})
    if not usgaap:
        return []

    votes: dict[int, Counter] = defaultdict(Counter)
    metadata: dict[tuple, dict] = {}

    for tag_data in usgaap.values():
        for observations in (tag_data.get("units") or {}).values():
            for obs in observations:
                form = obs.get("form")
                fy = obs.get("fy")
                fp = obs.get("fp")
                end = obs.get("end")
                accn = obs.get("accn")
                filed = obs.get("filed")
                if form not in ANNUAL_FORMS or fp != "FY" or fy is None or not end or not accn:
                    continue
                try:
                    fy_i = int(fy)
                except (TypeError, ValueError):
                    continue
                end_d = parse_date(end)
                if end_d is None or end_d < START_DATE or end_d > END_DATE:
                    continue
                key = (fy_i, end, accn, form, filed or "")
                votes[fy_i][key] += 1
                metadata[key] = {
                    "fiscal_year": fy_i,
                    "fiscal_year_end": end,
                    "accession": accn,
                    "form": form,
                    "filed": filed or "",
                }

    result = []
    for fy, counter in sorted(votes.items()):
        # highest tag support, then prefer 10-K, then later filing date
        ranked = sorted(
            counter.items(),
            key=lambda kv: (
                -kv[1],
                0 if kv[0][3] == "10-K" else 1,
                -(int((kv[0][4] or "0").replace("-", "")) if kv[0][4] else 0),
            ),
        )
        key, support = ranked[0]
        rec = dict(metadata[key])
        rec["companyfacts_support_count"] = support
        result.append(rec)
    return result


def inside_any_interval(d: date, intervals: list[Interval]) -> bool:
    return any(x.contains(d) for x in intervals)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--companyfacts", required=True, type=Path,
                    help="SEC companyfacts.zip or extracted Company Facts directory")
    ap.add_argument("--issuers", type=Path,
                    default=Path("data/research_sample_issuers_2010_2025.csv"))
    ap.add_argument("--intervals", type=Path,
                    default=Path("data/research_sample_membership_intervals_2010_2025.csv"))
    ap.add_argument("--outdir", type=Path, default=Path("data"))
    args = ap.parse_args()

    issuers = load_issuers(args.issuers)
    intervals = load_intervals(args.intervals)
    source = CompanyFactsSource(args.companyfacts)

    included = []
    issuer_summary = []
    missing = []

    try:
        for issuer in issuers:
            cik = normalize_cik(issuer["cik"])
            facts = source.read(cik)
            if facts is None:
                missing.append({
                    "cik": cik,
                    "canonical_name": issuer.get("canonical_name", ""),
                    "symbols": issuer.get("symbols", ""),
                    "reason": "COMPANYFACTS_NOT_FOUND",
                })
                issuer_summary.append({
                    "cik": cik,
                    "canonical_name": issuer.get("canonical_name", ""),
                    "symbols": issuer.get("symbols", ""),
                    "sector": issuer.get("sector", ""),
                    "companyfacts_found": 0,
                    "annual_10k_years_2010_2025": 0,
                    "membership_eligible_firmyears": 0,
                    "screen_status": "NO_COMPANYFACTS",
                })
                continue

            annuals = canonical_annual_filings(facts)
            eligible_count = 0
            membership = intervals.get(cik, [])

            for filing in annuals:
                fye = parse_date(filing["fiscal_year_end"])
                if not fye or not inside_any_interval(fye, membership):
                    continue
                eligible_count += 1
                accession_nodash = filing["accession"].replace("-", "")
                sec_index_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                    f"{accession_nodash}/{filing['accession']}-index.html"
                )
                included.append({
                    "cik": cik,
                    "canonical_name": issuer.get("canonical_name", ""),
                    "symbols": issuer.get("symbols", ""),
                    "sector": issuer.get("sector", ""),
                    "fiscal_year": filing["fiscal_year"],
                    "fiscal_year_end": filing["fiscal_year_end"],
                    "form": filing["form"],
                    "filed": filing["filed"],
                    "accession": filing["accession"],
                    "sec_filing_index_url": sec_index_url,
                    "companyfacts_support_count": filing["companyfacts_support_count"],
                    "sp500_member_at_fye": 1,
                    "us_gaap_namespace_present": 1,
                    "final_sample_rule_status": "ELIGIBLE",
                    "fx_hedge_dummy": "",
                    "fx_notional_usd": "",
                    "strict_foreign_sales_share": "",
                    "market_cap_fye_usd": "",
                    "approx_tobins_q": "",
                })

            issuer_summary.append({
                "cik": cik,
                "canonical_name": issuer.get("canonical_name", ""),
                "symbols": issuer.get("symbols", ""),
                "sector": issuer.get("sector", ""),
                "companyfacts_found": 1,
                "annual_10k_years_2010_2025": len(annuals),
                "membership_eligible_firmyears": eligible_count,
                "screen_status": "ELIGIBLE_YEARS_FOUND" if eligible_count else "NO_ELIGIBLE_FIRMYEARS",
            })
    finally:
        source.close()

    included.sort(key=lambda x: (x["cik"], x["fiscal_year_end"]))
    issuer_summary.sort(key=lambda x: (x["canonical_name"], x["cik"]))

    write_csv(
        args.outdir / "research_sample_firmyears_2010_2025.csv",
        included,
        [
            "cik","canonical_name","symbols","sector","fiscal_year","fiscal_year_end",
            "form","filed","accession","sec_filing_index_url","companyfacts_support_count",
            "sp500_member_at_fye","us_gaap_namespace_present","final_sample_rule_status",
            "fx_hedge_dummy","fx_notional_usd","strict_foreign_sales_share",
            "market_cap_fye_usd","approx_tobins_q",
        ],
    )
    write_csv(
        args.outdir / "research_sample_screening_summary_2010_2025.csv",
        issuer_summary,
        [
            "cik","canonical_name","symbols","sector","companyfacts_found",
            "annual_10k_years_2010_2025","membership_eligible_firmyears","screen_status",
        ],
    )
    write_csv(
        args.outdir / "research_sample_missing_companyfacts_2010_2025.csv",
        missing,
        ["cik","canonical_name","symbols","reason"],
    )

    print(f"Issuers screened: {len(issuers)}")
    print(f"Eligible firm-years: {len(included)}")
    print(f"Issuers missing Company Facts: {len(missing)}")
    print(f"Issuers with >=1 eligible firm-year: {sum(x['membership_eligible_firmyears'] > 0 for x in issuer_summary)}")


if __name__ == "__main__":
    main()
