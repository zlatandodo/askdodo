# TODO — Sector Rotation Dashboard

Aggiornato: 11 maggio 2026

---

## Sprint 0 — Smoke Test ✅ COMPLETATO

- [x] Lettura file esistenti
- [x] Setup virtualenv + installazione dipendenze
- [x] Prima esecuzione su dati reali
- [x] Identificazione bug
- [x] SPRINT_0_REPORT.md

---

## Sprint 1 — Fix bug critici + Setup GitHub ✅ COMPLETATO

### Fix bug
- [x] **Bug #1:** Fix `fetch_extra_assets()` — `.squeeze()` su yfinance 1.3.0
- [x] **Bug #2:** Fix `fetch_cot()` — nuovo URL CFTC `fut_disagg_txt_YYYY.zip` + colonna `Report_Date_as_YYYY-MM-DD`
- [x] **Bug #3:** HES delisted → sostituito con DVN in XLE components

### GitHub + produzione
- [x] Creato repository GitHub `zlatandodo/askdodo`
- [x] Creato `.github/workflows/update_dashboard.yml`
- [x] Git init, primo commit, push
- [x] GitHub Pages abilitato su `main` / `/docs`
- [x] Gmail App Password configurata
- [x] Secrets configurati (FRED_API_KEY, EMAIL_*)
- [x] Primo workflow manuale lanciato e completato con successo ✅
- [x] Sito online: https://zlatandodo.github.io/askdodo/
- [x] SPRINT_1_REPORT.md

---

## Sprint 2 — Indicatori sentiment mancanti

- [ ] NAAIM Exposure Index scraper
- [ ] CBOE Put/Call Ratio (Equity)
- [ ] ISM Manufacturing PMI vero (TradingView?)
- [ ] DXY più affidabile se yfinance continua a dare problemi

---

## Sprint 3 — ETF Flows

- [ ] Spike tecnico: confronto 4 fonti (TradingView, stockanalysis, etf.com, yfinance AUM proxy)
- [ ] Implementare `fetch_etf_flows()`
- [ ] ETF flows come 6° criterio scoring (0–6/6)
- [ ] Heatmap flows nel tab Charts

---

## Sprint 4 — ETF Tematici

- [ ] Lista finale tematici (confermare con utente)
- [ ] Filtro qualità AUM > $300M e volume > $10M/giorno
- [ ] Tab "🚀 Tematici" separato da SPDR
- [ ] Email: aggiungere "Top 3 tematici"

---

## Sprint 5 — Backtest e calibrazione

- [ ] Backtest composite score 10 anni
- [ ] Hit-rate per livello di score
- [ ] Calibrazione soglie cruscotto

---

## Sprint 6 — History tracking

- [ ] Snapshot JSON settimanali in `history/snapshots/YYYY-MM-DD.json`
- [ ] Tab "📜 Storia" dashboard
- [ ] Alert email solo se stato cruscotto cambia

---

## Sprint 7 — Portfolio overlay

- [ ] Schema `portfolio.json`
- [ ] Tab "💼 Portfolio Match"
- [ ] Over/underweight per asset class

---

## Issue aperte

| # | Descrizione | Priorità |
|---|---|---|
| 1 | `fetch_extra_assets()` fallisce con yfinance 1.3.0 | 🔴 ALTA |
| 2 | `fetch_cot()` URL CFTC non restituisce zip valido | 🔴 ALTA |
| 3 | HES delisted in XLE components | 🟡 MEDIA |
| 4 | `.github/workflows/` mancante | 🟡 MEDIA |
