# SPRINT 0 REPORT — Smoke Test
**Data:** 11 maggio 2026
**Ambiente:** Python 3.14.4 · macOS · virtualenv .venv
**Script:** sector_rotation.py (v2, ~2240 righe)

---

## ✅ COSA FUNZIONA

| Componente | Stato | Note |
|---|---|---|
| ETF prices (yfinance) | ✅ OK | 10 settori + SPY, dati 52 settimane |
| Relative strength / metrics | ✅ OK | RS 4W/12W/26W, RSI ratio, trend ratio, vol |
| Sector breadth | ✅ OK | % componenti > MA50 (warning: HES delisted, vedi bug #3) |
| FRED macro indicators | ✅ OK | 9 serie: yield curve, HY, VIX, LEI, CPI, PCE, IndPro, UnRate, ChiFed |
| Quadrante All-Weather | ✅ OK | Detection funzionante su dati FRED reali |
| Composite scoring | ✅ OK | Framework 0–5 per settore funzionante |
| HTML output | ✅ OK | 97 KB, self-contained, apribile nel browser |
| Email framework | ⏸️ IN STANDBY | Codice presente, non testato (mancano credenziali) |

---

## 🔴 BUG CRITICI DA CORREGGERE (Sprint 1)

### Bug #1 — `fetch_extra_assets()`: tutti gli asset extra falliscono
**Errore:** `float() argument must be a string or a real number, not 'Series'`

**Causa:** Con yfinance 1.3.0, `yf.download(single_ticker, ...)['Close']` restituisce
un DataFrame a una colonna, non una Series. Quindi `s.iloc[-1]` restituisce una Series
(non uno scalare) e `float(Series)` fallisce.

**Asset colpiti:** DXY, MOVE, VIX(yf), Copper, Gold, Silver, Oil, NatGas, TLT, GLD — tutti assenti.

**Impatto sul cruscotto:** mancano gli indicatori Copper/Gold Ratio, DXY, MOVE Index
→ solo 3–4 dei 8 indicatori del cruscotto sono disponibili invece di 8.

**Fix:** aggiungere `.squeeze()` o usare `.iloc[-1].item()` dopo `s.iloc[-1]`
per forzare il ritorno a scalare.

---

### Bug #2 — `fetch_cot()`: COT non disponibile
**Errore:** `File is not a zip file`

**Causa:** L'URL `https://www.cftc.gov/dea/newcot/c_disaggregated.zip` non restituisce
più un file zip valido. Il CFTC probabilmente ha cambiato struttura, restituisce
HTML di errore oppure richiede un User-Agent diverso.

**Impatto:** nessun dato COT su Oil, Gold, Silver, Copper, S&P 500 E-mini.
Il tab COT è vuoto, l'indicatore "COT S&P 500" manca dal cruscotto.

**Fix da valutare:** verificare l'URL attuale su cftc.gov, aggiungere header
`User-Agent` alla request, oppure usare l'URL del report corrente via API CFTC.

---

### Bug #3 — HES (Hess Corp) delisted
**Errore:** warning yfinance al download breadth XLE components.

**Causa:** HES è stata acquisita da Chevron (CVX) nel 2024 e delisted.

**Impatto minimo:** breadth XLE calcolata su 9/10 componenti. Non rompe nulla.

**Fix:** sostituire HES in `COMPONENTS['XLE']` con un titolo attuale (es. `HAL`, `DVN` o `FANG`).

---

## 📊 LETTURA DI MERCATO (dati reali, 11 maggio 2026)

### Cruscotto: 🟡 GIALLO — LATE CYCLE / ATTENZIONE
| Indicatore | Valore | Stato |
|---|---|---|
| Chicago Fed (ISM proxy) | -0.20 | 🔴 Contrazione borderline |
| HY Spreads OAS | 2.81% | 🟢 Credito sereno |
| Yield Curve 10Y-2Y | +0.48% | 🟢 Curva positiva |
| VIX | 17.2 | 🟢 Bassa volatilità |
| DXY | ❌ mancante | — |
| MOVE Index | ❌ mancante | — |
| Copper/Gold | ❌ mancante | — |
| COT S&P 500 | ❌ mancante | — |

### Quadrante: 🔴 STAGFLAZIONE
- **Crescita:** borderline (CFNAI -0.20, LEI in calo)
- **Inflazione:** ancora sopra target (CPI/PCE YoY > 2.5%)
- **Azione:** BUNKER MODE — aumenta oro e inflation-linked, riduci equity growth

### Ranking settori
| Ticker | Score | Segnale | RS 4W |
|---|---|---|---|
| XLK | 5/5 | FORTE | +12.62% |
| XLE | 1/5 | NEGATIVO | -4.16% |
| XLF | 1/5 | NEGATIVO | -7.16% |
| XLI | 1/5 | NEGATIVO | -5.27% |
| XLB | 1/5 | NEGATIVO | -5.59% |
| XLRE | 1/5 | NEGATIVO | -3.51% |
| XLP | 1/5 | NEGATIVO | -4.20% |
| XLV | 0/5 | NEGATIVO | -9.59% |
| XLU | 0/5 | NEGATIVO | -8.84% |
| XLY | 0/5 | NEGATIVO | -3.60% |

Situazione estrema: XLK domina tutto il mercato (+12.62% RS4W).
In un contesto di stagflazione teorica, il Tech dominante è una divergenza anomala
da monitorare (AI rally vs macro deterioramento).

---

## 📋 PROPOSTA SPRINT 1

**Obiettivo primario:** metti in produzione e fixa i 2 bug critici.

### Priorità fix (nell'ordine)

**1. Fix `fetch_extra_assets()` [Bug #1]** — 15 minuti di lavoro
```python
curr = float(s.iloc[-1].item() if hasattr(s.iloc[-1], 'item') else s.iloc[-1])
```
Questo ripristina DXY, MOVE, Copper/Gold e tutti gli altri asset extra → cruscotto completo.

**2. Fix `fetch_cot()` [Bug #2]** — richiede verifica URL + eventuale aggiunta User-Agent
Verificare prima se l'URL funziona via browser/curl. Se il problema è solo lo User-Agent:
```python
r = requests.get(url, timeout=45, headers={'User-Agent': 'Mozilla/5.0'})
```

**3. Fix HES delisted [Bug #3]** — 1 riga di codice
Sostituire `'HES'` con `'DVN'` o `'HAL'` in `COMPONENTS['XLE']`.

### Poi: setup GitHub + produzione

4. Creare repository GitHub (passo passo guidato)
5. Creare file `.github/workflows/update_dashboard.yml` (mancante)
6. Abilitare GitHub Pages su `/docs`
7. Generare Gmail App Password
8. Configurare Secrets su GitHub
9. Lanciare il primo workflow manuale
10. Verificare che la mail arrivi e il sito sia online

---

## 🗒️ AMBIENTE LOCALE — Comandi utili

```bash
# Attivare virtualenv
source .venv/bin/activate

# Eseguire script (solo HTML)
FRED_API_KEY=af5b5d... python sector_rotation.py --output test_output.html

# Eseguire con email
FRED_API_KEY=... EMAIL_SENDER=... EMAIL_PASSWORD=... EMAIL_TO=... python sector_rotation.py --email
```

---

*Fine Sprint 0 — nessuna riga di codice modificata.*
