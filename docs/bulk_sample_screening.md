# Bulk SEC sample-screening stage

The final research sample is now processed in bulk rather than firm-by-firm.

## Required SEC input

Download the SEC bulk Company Facts archive:

`https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip`

The script reads the ZIP directly, so extraction is optional.

## Run

```bash
python src/build_research_sample.py --companyfacts /path/to/companyfacts.zip
```

## Outputs

- `data/research_sample_firmyears_2010_2025.csv` — eligible point-in-time S&P 500 firm-years.
- `data/research_sample_screening_summary_2010_2025.csv` — issuer-level screening results.
- `data/research_sample_missing_companyfacts_2010_2025.csv` — CIKs not found in the SEC bulk archive.

## Screening logic

A firm-year is eligible only if:

1. the issuer belongs to the ex-ante historical S&P 500 research frame;
2. its fiscal-year-end falls inside one of its point-in-time S&P 500 membership intervals;
3. Company Facts contains a U.S.-GAAP namespace;
4. an annual `10-K` or `10-K/A` observation exists for that fiscal year; and
5. the fiscal-year-end lies within 2010-01-01 through 2025-12-31.

This automatically removes 20-F/40-F-only foreign private issuer observations. Acquired and delisted firms remain eligible through their final qualifying public firm-year. Hedge status is not used anywhere in the inclusion screen.

The output firm-year file intentionally leaves FX hedging, foreign sales, fiscal-year-end market capitalization, and Tobin's Q blank. Those variables are filled in subsequent bulk stages after the sampling frame is frozen.
