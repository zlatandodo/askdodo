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

## Sprint 1 — Fix bug critici + Setup GitHub (PROSSIMO)

### Fix bug (prima del deploy)
- [ ] **Bug #1:** Fix `fetch_extra_assets()` — `float(Series)` error su yfinance 1.3.0
      Causa: single-ticker download restituisce DataFrame non Series
      Fix: `.item()` o `.squeeze()` su `s.iloc[-1]`
- [ ] **Bug #2:** Fix `fetch_cot()` — URL CFTC non più risponde con zip valido
      Verificare URL attuale, aggiungere User-Agent, trovare alternativa se necessario
- [ ] **Bug #3:** Fix HES delisted in `COMPONENTS['XLE']` — sostituire con DVN o HAL

### GitHub + produzione
- [ ] Creare repository GitHub `sector-rotation`
- [ ] Creare `.github/workflows/update_dashboard.yml`
- [ ] Inizializzare Git localmente, primo commit, push
- [ ] Abilitare GitHub Pages su branch `main` folder `/docs`
- [ ] Generare Gmail App Password
- [ ] Configurare Secrets su GitHub (FRED_API_KEY, EMAIL_*)
- [ ] Lanciare primo workflow manuale
- [ ] Verificare mail + sito online
- [ ] SPRINT_1_REPORT.md con URL pubblico

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
