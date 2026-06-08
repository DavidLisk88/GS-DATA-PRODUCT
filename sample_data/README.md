# Sample data

Tiny, **internally consistent** CSV slices of the LSEG mock catalog. Six
companies (AAPL, MSFT, GOOG, VOD, BMW, 7203 Toyota) carried through entity →
instrument → quote → pricing → fundamentals → estimates, plus an FX table
sufficient to do USD conversions and a few corporate actions.

The catalog also includes minimal slices for the extended domains:

- **Fixed Income:** `bond_terms.csv`, `credit_ratings_history.csv`,
  `yield_curves_eod.csv` (UST, SOFR-OIS, Bund, Gilt, JGB, CDX/iTraxx).
- **Derivatives:** `futures_series_chain.csv` + `futures_contracts.csv`
  (ES, NQ, CL, ZN, GC, FGBL), `options_chain.csv` + `options_eod_iv.csv`
  (AAPL + SPX strikes).
- **Funds (Lipper):** `fund_master.csv` (iShares S&P 500 ETF, Vanguard 500,
  Fidelity Contrafund, SPDR Gold, PIMCO Total Return).
- **World-Check:** `wc_individuals.csv` + `wc_sanctions_listings.csv` —
  **all rows are clearly-marked synthetic test records** (`WC-TEST-*` IDs,
  `FAKE_LIST` codes, jurisdiction `XX`). They do not correspond to any real
  person or organisation and must never be used for actual screening.

These are *not* random — `org_perm_id` 4295905573 (Apple) is consistent
across every file. Verify it works for the AI tool's joins by loading them
into any SQLite/DuckDB and running queries from
[`docs/lseg-mock-catalog/99-join-cookbook.md`](../docs/lseg-mock-catalog/99-join-cookbook.md).

Quick load (DuckDB):

```python
import duckdb, glob, os
con = duckdb.connect()
for path in glob.glob("sample_data/*.csv"):
    name = os.path.splitext(os.path.basename(path))[0]
    con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_csv_auto('{path}', header=True)")
con.execute("DESCRIBE").show()
```
