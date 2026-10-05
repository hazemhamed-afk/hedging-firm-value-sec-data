# SEC Hedging Panel Builder

This GitHub-ready project builds the accounting backbone for a study of financial hedging,
internationalization, and firm value using public SEC EDGAR data.

## What it does

1. Downloads the current S&P 500 constituent list from the public GitHub repository
   `datasets/s-and-p-500-companies`.
2. Maps tickers to SEC CIK identifiers.
3. Retrieves SEC `submissions` metadata and `companyfacts` XBRL data for each firm.
4. Excludes financial firms (SIC 6000–6999) and utilities (SIC 4900–4999).
5. Builds annual firm-year variables for 2010–2025:
   - total assets
   - liabilities
   - stockholders' equity
   - revenue
   - net income
   - cash
   - R&D
   - capital expenditures
   - debt (current + noncurrent when available)
   - ROA
   - leverage
   - log assets
6. Saves:
   - `data/sec_financial_panel.csv`
   - `data/sec_firm_metadata.csv`
   - `data/sec_missingness_report.csv`
   - `data/sec_collection_log.csv`

The next research stage is to add:
- foreign sales / geographic exposure from 10-K geographic segment disclosures
- FX derivative use and notional values from 10-K derivative footnotes
- market-value data to construct Tobin's Q
- macro variables such as FX volatility and geopolitical risk

## SEC fair-access requirement

SEC requests must identify the researcher. In GitHub, create a repository variable named
`SEC_USER_AGENT` with a value such as:

`Your Name your-email@university.edu academic research`

In GitHub:
Settings -> Secrets and variables -> Actions -> Variables -> New repository variable

## Run in GitHub Actions

1. Open the **Actions** tab.
2. Choose **Collect SEC panel**.
3. Click **Run workflow**.
4. Choose start year, end year, and maximum firms.
5. When the workflow finishes, download the `sec-panel-data` artifact.

For the first test, use 25 firms. Once it works, rerun with 300 or 500 firms.

## Research design

The planned core model is:

Q_it = firm FE + year FE
       + beta1 Hedge_it
       + beta2 ForeignExposure_it
       + beta3 Hedge_it x ForeignExposure_it
       + controls_it + error_it

A negative beta3 supports substitution between financial hedging and operational
international diversification. A positive beta3 supports complementarity.

## Notes

- The panel is intentionally unbalanced.
- SEC XBRL tags vary across firms; the script uses tag fallbacks.
- The accounting panel should be audited before estimation.
- Market capitalization and FX-derivative notionals are not reliably standardized in
  SEC Company Facts and therefore belong in later collection modules.
