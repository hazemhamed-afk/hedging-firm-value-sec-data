import argparse
import os
import time
import json
from pathlib import Path
from typing import Optional, Dict, List

import numpy as np
import pandas as pd
import requests

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SP500_GITHUB_CSV = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"

TAG_CANDIDATES = {
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "rd": [
        "ResearchAndDevelopmentExpense",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForAdditionsToPropertyPlantAndEquipment",
    ],
    "debt_current": [
        "LongTermDebtCurrent",
        "ShortTermBorrowings",
        "DebtCurrent",
    ],
    "debt_noncurrent": [
        "LongTermDebtNoncurrent",
        "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
        "LongTermDebt",
    ],
}

def make_session() -> requests.Session:
    user_agent = os.getenv("SEC_USER_AGENT", "").strip()
    if not user_agent:
        raise RuntimeError(
            "SEC_USER_AGENT is required. Set it to 'Your Name email@domain.edu academic research'."
        )
    s = requests.Session()
    s.headers.update({
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Host": "data.sec.gov",
    })
    return s

def get_json(session: requests.Session, url: str, retries: int = 5) -> dict:
    delay = 0.15
    for attempt in range(retries):
        r = session.get(url, timeout=60)
        if r.status_code == 200:
            time.sleep(delay)
            return r.json()
        if r.status_code in (403, 429, 500, 502, 503, 504):
            time.sleep((attempt + 1) * 2)
            continue
        r.raise_for_status()
    raise RuntimeError(f"Failed after {retries} attempts: {url}")

def load_sp500() -> pd.DataFrame:
    df = pd.read_csv(SP500_GITHUB_CSV)
    symbol_col = "Symbol" if "Symbol" in df.columns else "symbol"
    name_col = "Security" if "Security" in df.columns else ("Name" if "Name" in df.columns else None)
    cik_col = "CIK" if "CIK" in df.columns else None
    if cik_col is None:
        raise RuntimeError("The S&P 500 GitHub dataset does not contain a CIK column.")

    out = pd.DataFrame({
        "ticker": df[symbol_col].astype(str).str.upper().str.replace(".", "-", regex=False),
        "cik": pd.to_numeric(df[cik_col], errors="coerce"),
    })
    if name_col:
        out["constituent_name"] = df[name_col].astype(str)
    out = out.dropna(subset=["cik"]).copy()
    out["cik"] = out["cik"].astype(int)
    return out.drop_duplicates(["ticker", "cik"])


def filing_metadata(session: requests.Session, cik: int) -> dict:
    d = get_json(session, SEC_SUBMISSIONS.format(cik=cik))
    return {
        "cik": cik,
        "entity_name": d.get("name"),
        "sic": pd.to_numeric(d.get("sic"), errors="coerce"),
        "sic_description": d.get("sicDescription"),
        "state_of_incorporation": d.get("stateOfIncorporation"),
        "fiscal_year_end": d.get("fiscalYearEnd"),
        "tickers_sec": "|".join(d.get("tickers", []) or []),
        "exchanges": "|".join(d.get("exchanges", []) or []),
    }

def is_excluded_sic(sic) -> bool:
    if pd.isna(sic):
        return False
    sic = int(sic)
    return 4900 <= sic <= 4999 or 6000 <= sic <= 6999

def get_units_for_tag(companyfacts: dict, tag: str) -> dict:
    usgaap = companyfacts.get("facts", {}).get("us-gaap", {})
    obj = usgaap.get(tag)
    if not obj:
        return {}
    return obj.get("units", {}) or {}

def select_unit(units: dict) -> Optional[List[dict]]:
    if "USD" in units:
        return units["USD"]
    if "shares" in units:
        return units["shares"]
    if units:
        return next(iter(units.values()))
    return None

def normalize_annual_records(records: List[dict], start_year: int, end_year: int) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=["fy", "val", "filed", "form", "frame", "accn"])
    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=["fy", "val", "filed", "form", "frame", "accn"])

    if "form" not in df.columns:
        return pd.DataFrame(columns=["fy", "val", "filed", "form", "frame", "accn"])
    df = df[df["form"].isin(["10-K", "10-K/A"])].copy()
    if "fy" not in df.columns:
        return pd.DataFrame(columns=["fy", "val", "filed", "form", "frame", "accn"])

    df["fy"] = pd.to_numeric(df["fy"], errors="coerce")
    df["val"] = pd.to_numeric(df.get("val"), errors="coerce")
    df["filed"] = pd.to_datetime(df.get("filed"), errors="coerce")
    df = df[df["fy"].between(start_year, end_year, inclusive="both")]
    df = df.dropna(subset=["fy", "val"])
    df = df.sort_values(["fy", "filed"]).drop_duplicates("fy", keep="last")
    return df

def extract_metric(companyfacts: dict, candidates: List[str], start_year: int, end_year: int):
    for tag in candidates:
        units = get_units_for_tag(companyfacts, tag)
        records = select_unit(units)
        if records:
            df = normalize_annual_records(records, start_year, end_year)
            if not df.empty:
                return tag, df[["fy", "val"]].rename(columns={"val": tag})
    return None, pd.DataFrame(columns=["fy"])

def build_company_panel(companyfacts: dict, cik: int, ticker: str,
                        start_year: int, end_year: int):
    years = pd.DataFrame({"fy": list(range(start_year, end_year + 1))})
    used_tags = {}
    panel = years.copy()

    for metric, candidates in TAG_CANDIDATES.items():
        tag, d = extract_metric(companyfacts, candidates, start_year, end_year)
        used_tags[metric] = tag
        if tag and not d.empty:
            d = d.rename(columns={tag: metric})
            panel = panel.merge(d, on="fy", how="left")
        else:
            panel[metric] = np.nan

    panel["cik"] = cik
    panel["ticker"] = ticker
    panel["debt"] = panel[["debt_current", "debt_noncurrent"]].fillna(0).sum(axis=1)
    no_debt_data = panel[["debt_current", "debt_noncurrent"]].isna().all(axis=1)
    panel.loc[no_debt_data, "debt"] = np.nan

    panel["roa"] = panel["net_income"] / panel["assets"]
    panel["leverage"] = panel["debt"] / panel["assets"]
    panel["cash_assets"] = panel["cash"] / panel["assets"]
    panel["rd_assets"] = panel["rd"] / panel["assets"]
    panel["capex_assets"] = panel["capex"] / panel["assets"]
    panel["log_assets"] = np.log(panel["assets"].where(panel["assets"] > 0))
    panel["sales_growth"] = panel["revenue"].pct_change(fill_method=None)

    panel = panel[(panel["assets"].notna()) | (panel["revenue"].notna())].copy()
    return panel, used_tags

def missingness_report(panel: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "assets","liabilities","equity","revenue","net_income","cash","rd","capex",
        "debt","roa","leverage","cash_assets","rd_assets","capex_assets","log_assets",
        "sales_growth"
    ]
    rows = []
    n = len(panel)
    for c in cols:
        if c in panel:
            rows.append({
                "variable": c,
                "n_total": n,
                "n_nonmissing": int(panel[c].notna().sum()),
                "pct_missing": float(panel[c].isna().mean() * 100) if n else np.nan,
            })
    return pd.DataFrame(rows)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start-year", type=int, default=2010)
    p.add_argument("--end-year", type=int, default=2025)
    p.add_argument("--max-firms", type=int, default=300,
                   help="Maximum eligible firms after SIC screening. Use 0 for all.")
    p.add_argument("--outdir", default="data")
    args = p.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    sec = make_session()

    universe = load_sp500()

    metadata_rows = []
    panel_parts = []
    log_rows = []
    eligible_count = 0

    for _, row in universe.iterrows():
        ticker = row["ticker"]
        cik = int(row["cik"])
        try:
            meta = filing_metadata(sec, cik)
            meta["ticker"] = ticker
            meta["constituent_name"] = row.get("constituent_name")
            meta["excluded_financial_or_utility"] = is_excluded_sic(meta["sic"])
            metadata_rows.append(meta)

            if meta["excluded_financial_or_utility"]:
                log_rows.append({"ticker": ticker, "cik": cik, "status": "excluded_sic", "error": ""})
                continue

            if args.max_firms and eligible_count >= args.max_firms:
                break

            facts = get_json(sec, SEC_COMPANYFACTS.format(cik=cik))
            panel, tags = build_company_panel(facts, cik, ticker, args.start_year, args.end_year)

            if not panel.empty:
                panel["entity_name"] = meta["entity_name"]
                panel["sic"] = meta["sic"]
                panel["sic_description"] = meta["sic_description"]
                panel_parts.append(panel)
                eligible_count += 1
                log_rows.append({
                    "ticker": ticker, "cik": cik, "status": "ok",
                    "n_firm_years": len(panel),
                    "used_tags": json.dumps(tags, sort_keys=True),
                    "error": ""
                })
            else:
                log_rows.append({"ticker": ticker, "cik": cik, "status": "no_annual_facts", "error": ""})
        except Exception as e:
            log_rows.append({"ticker": ticker, "cik": cik, "status": "error", "error": str(e)})

    metadata = pd.DataFrame(metadata_rows)
    logs = pd.DataFrame(log_rows)

    if panel_parts:
        panel = pd.concat(panel_parts, ignore_index=True)
        panel = panel.sort_values(["ticker", "fy"]).reset_index(drop=True)
    else:
        panel = pd.DataFrame()

    panel.to_csv(outdir / "sec_financial_panel.csv", index=False)
    metadata.to_csv(outdir / "sec_firm_metadata.csv", index=False)
    logs.to_csv(outdir / "sec_collection_log.csv", index=False)
    missingness_report(panel).to_csv(outdir / "sec_missingness_report.csv", index=False)

    print(f"Eligible firms collected: {eligible_count}")
    print(f"Firm-year observations: {len(panel)}")
    print(f"Output directory: {outdir.resolve()}")

if __name__ == "__main__":
    main()
