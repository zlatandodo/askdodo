# DECISIONS — Scelte tecniche significative

---

## 2026-05-11 — Sprint 0

### Ambiente Python
- **Scelta:** Python 3.14.4 (versione di sistema su macOS)
- **Virtualenv:** `.venv/` nella cartella del progetto
- **Dipendenze:** yfinance 1.3.0, plotly 6.7.0, pandas 3.0.2, numpy 2.4.4

### FRED API Key
- Chiave configurata come variabile d'ambiente (`FRED_API_KEY`)
- Non committare mai nel codice o nei file versionati

### Fonte dati macro
- **FRED API** confermata come fonte primaria per yield curve, HY spreads, VIX, LEI, CPI, PCE, IndPro, CFNAI
- Tutte le serie FRED funzionano correttamente nella prima esecuzione

### Bug yfinance 1.3.0 (extra assets)
- **Problema:** `yf.download(single_ticker)['Close']` in yfinance 1.3.0 restituisce
  DataFrame colonna singola invece di Series; `float(s.iloc[-1])` fallisce
- **Fix pianificato Sprint 1:** usare `.item()` o `.squeeze()` per forzare scalare
- **Alternativa scartata:** downgrade yfinance — preferibile aggiornare il codice

### COT URL CFTC
- **Problema:** `https://www.cftc.gov/dea/newcot/c_disaggregated.zip` non risponde
  con zip valido al 11/05/2026
- **Da verificare Sprint 1:** URL alternativo CFTC, header User-Agent, API CFTC
- **Alternativa se irrecuperabile:** valutare proxy via Quandl/CFTC API ufficiale
