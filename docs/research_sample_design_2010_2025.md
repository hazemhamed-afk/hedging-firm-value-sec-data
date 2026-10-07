# Research Sample Design (2010–2025)

## Sampling frame
The inferential sample is defined ex ante from point-in-time S&P 500 membership, not from hedge status or data convenience.

- Window: 2010-01-01 through 2025-12-31.
- Source: lawcal/sp500-components-history, data/components_history.csv.
- Unit of sampling: SEC issuer CIK.
- Sector exclusions: Financials, Utilities, Real Estate.
- Firm-year inclusion: retain an annual observation only when the firm's fiscal-year-end falls inside one of its S&P 500 membership intervals.
- Filing screen: require U.S. 10-K / 10-K-A and U.S. GAAP for the firm-year; exclude 20-F/40-F foreign-private-issuer observations.
- Acquired/delisted firms: retained through their last eligible public firm-year.
- Hedging status is never an inclusion criterion.
- The panel is intentionally unbalanced.

## Current frame
- Eligible nonfinancial/nonutility/non-real-estate issuer CIKs overlapping 2010–2025: 623
- Membership interval rows: 683

## Next pipeline stage
1. Pull SEC Company Facts for every issuer CIK.
2. Build the exact 10-K/10-K-A fiscal-year filing map.
3. Keep only firm-years whose fiscal-year-end lies within an index membership interval.
4. Extract accounting controls automatically.
5. Parse annual reports for strict foreign sales and explicit FX-derivative evidence.
6. Add fiscal-year-end market value and estimate Tobin's Q.
7. Run the preregistered two-way fixed-effects specifications without selecting firms based on the result.

## Sector counts
- communication_services: 32
- communication_services|consumer_discretionary: 1
- communication_services|information_technology: 1
- consumer_discretionary: 106
- consumer_discretionary|consumer_staples: 1
- consumer_staples: 54
- energy: 59
- health_care: 100
- industrials: 106
- industrials|consumer_discretionary: 1
- information_technology: 113
- materials: 47
- materials|industrials: 2
