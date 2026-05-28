# 📊 Sector Rotation Dashboard

Dashboard settimanale automatico per l'analisi della rotazione settoriale.
Si aggiorna ogni domenica alle 22:00 ora italiana, pubblica su GitHub Pages e manda una mail di riepilogo.

**Fonti dati: tutte gratuite** — Yahoo Finance · FRED API · CFTC COT Report

---

## Setup in 15 minuti

### Step 1 — Crea il repository GitHub

1. Vai su [github.com](https://github.com) → crea un account gratuito se non ce l'hai
2. Clicca **New repository**
3. Nome: `sector-rotation` (o quello che vuoi)
4. Visibilità: **Public** (richiesto da GitHub Pages gratuito)
5. Clicca **Create repository**

### Step 2 — Carica i file

Carica questi file nel repository (trascina e rilascia nell'interfaccia web di GitHub, oppure usa Git):

```
sector-rotation/
├── .github/
│   └── workflows/
│       └── update_dashboard.yml   ← automazione settimanale
├── docs/
│   └── index.html                 ← dashboard (generato automaticamente)
├── sector_rotation.py             ← script principale
├── requirements.txt               ← dipendenze Python
└── README.md                      ← questo file
```

### Step 3 — Abilita GitHub Pages

1. Nel repository → **Settings** → **Pages** (barra laterale sinistra)
2. Source: **Deploy from a branch**
3. Branch: `main` · Folder: `/docs`
4. Clicca **Save**

Il tuo URL sarà: `https://TUO_USERNAME.github.io/sector-rotation/`

> Salva questo URL — ti servirà nello Step 5.

### Step 4 — FRED API Key (gratuita)

1. Vai su [fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html)
2. Clicca **Request API Key**
3. Registrazione rapida (nome, email, uso previsto)
4. Ricevi la chiave via email in pochi secondi

### Step 5 — Configura i Secrets GitHub

Nel repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Aggiungi questi secrets (uno alla volta):

| Nome Secret | Valore | Obbligatorio |
|---|---|---|
| `FRED_API_KEY` | la chiave FRED ricevuta via email | ✅ Sì |
| `EMAIL_SENDER` | tua@gmail.com | Solo per email |
| `EMAIL_PASSWORD` | App Password Gmail (16 caratteri) | Solo per email |
| `EMAIL_TO` | destinatario@email.com | Solo per email |
| `DASHBOARD_URL` | https://USERNAME.github.io/sector-rotation/ | Solo per email |

**Come ottenere l'App Password Gmail:**
1. Vai su [myaccount.google.com/security](https://myaccount.google.com/security)
2. Abilita la **Verifica in due passaggi** (se non è già attiva)
3. Torna su Security → cerca **Password per le app** (o App Passwords)
4. Seleziona app: "Posta" · Dispositivo: "Altro" → digita "sector-rotation"
5. Gmail genera una password di 16 caratteri — quella va in `EMAIL_PASSWORD`

> ⚠️ L'App Password è diversa dalla password del tuo account Google. Non usare la password normale.

### Step 6 — Primo avvio manuale

1. Nel repository → **Actions**
2. Clicca **Weekly Sector Rotation Dashboard** (barra sinistra)
3. Clicca **Run workflow** → **Run workflow** (bottone verde)
4. Aspetta 3–5 minuti che il workflow completi

Vedrai il log in tempo reale. Al termine:
- Il dashboard è pubblicato su `https://USERNAME.github.io/sector-rotation/`
- Hai ricevuto la mail di riepilogo (se configurata)

---

## Automazione

Una volta configurato, il workflow gira **automaticamente ogni domenica alle 20:00 UTC** (22:00 ora italiana) senza che tu debba fare nulla.

Puoi lanciarlo manualmente in qualsiasi momento da Actions → Run workflow.

---

## Uso locale (opzionale)

Se vuoi eseguire lo script sul tuo computer invece di GitHub:

```bash
# Installa dipendenze
pip install -r requirements.txt

# Imposta variabili d'ambiente
export FRED_API_KEY="la_tua_chiave"
export EMAIL_SENDER="tua@gmail.com"
export EMAIL_PASSWORD="app_password_16_chars"
export EMAIL_TO="destinatario@email.com"

# Esegui (genera HTML + invia mail)
python sector_rotation.py --email

# Solo HTML, senza mail
python sector_rotation.py

# Output custom
python sector_rotation.py --output /percorso/dashboard.html
```

---

## Struttura del Dashboard

| Tab | Contenuto |
|---|---|
| 🎯 **Scoring** | Carte per ogni settore con composite score 0–5 e breakdown dei criteri |
| 📈 **Charts** | Relative strength normalizzata, heatmap ritorni, yield curve + HY spreads |
| 📋 **Tabella** | Vista piatta con tutti i metrics ordinati per score |
| 🏦 **COT** | Posizionamento Managed Money sui futures commodity (CFTC) |
| 📖 **Guida** | Manuale completo di lettura e interpretazione |

---

## Come Funziona il Composite Score

Ogni settore riceve 1 punto per ciascuno dei 5 criteri:

| Criterio | Descrizione |
|---|---|
| **RS 4W vs SPY** | Sovraperformance relativa nelle ultime 4 settimane |
| **Trend Ratio UP** | Il ratio settore/SPY forma higher highs su 60 giorni |
| **Breadth >40%** | Almeno il 40% dei componenti è sopra la propria MA50 |
| **RS 12W vs SPY** | Sovraperformance confermata su 12 settimane |
| **RSI Ratio >50** | Momentum del ratio settore/SPY in territorio positivo |

**Soglie operative:**
- `4–5/5` → FORTE — procedi con l'analisi tecnica su TradingView
- `3/5` → MODERATO — watchlist, aspetta 1–2 conferme
- `2/5` → DEBOLE — non entrare
- `0–1/5` → NEGATIVO — evita o considera underweight

---

## Fonti Dati

| Fonte | Dato | Auth |
|---|---|---|
| Yahoo Finance (yfinance) | Prezzi ETF e componenti | No |
| FRED API (St. Louis Fed) | Yield curve, HY spreads, VIX, LEI | Chiave gratuita |
| CFTC.gov | COT Disaggregated Report | No |

---

*Non costituisce consulenza finanziaria. Strumento di analisi personale.*
