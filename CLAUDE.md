## PROGETTO: Sector Rotation + Family Office Cruscotto Dashboard

## CONTESTO

Sto sviluppando una dashboard personale di analisi macro + sector rotation
per il mio portafoglio (~€3.7M, multi-asset, italiano).

L'obiettivo è accedere una volta a settimana e avere in 5 minuti un quadro
operativo: dove siamo nel ciclo, semaforo risk-on/off, settori favoriti,
posizionamento istituzionale.

Non ho ancora mai eseguito lo script né configurato GitHub. Partiamo da zero.

---

## FILE GIÀ IN CARTELLA

- **`sector_rotation.py`** — script principale ~2200 righe (versione v2 generata
  da una conversazione precedente con Claude). Da testare e raffinare.
- **`requirements.txt`** — dipendenze Python (yfinance, pandas, plotly, requests).
- **`.github/workflows/update_dashboard.yml`** — workflow GitHub Actions per
  esecuzione settimanale automatica.
- **`docs/index.html`** — placeholder, sarà sovrascritto dallo script.
- **`README.md`** — istruzioni di setup esistenti (potrebbero richiedere update).
- **`IL_CRUSCOTTO_DI_CONTROLLO.docx`** — framework concettuale del cruscotto:
  8 indicatori macro/sentiment con soglie operative e matrice traffic light
  Verde/Giallo/Rosso.
- **`QUADRANTI_MACROECONOMIA.docx`** — modello All-Weather a 4 quadranti basato
  su crescita × inflazione (Goldilocks/Reflazione/Stagflazione/Deflazione)
  con asset mapping.

**Prima azione obbligatoria:** leggi tutti questi file prima di procedere.

---

## COSA FA GIÀ LO SCRIPT v2

- Scarica prezzi 10 ETF settoriali USA + componenti (yfinance)
- Calcola composite score 0–5 per ogni settore
- Scarica indicatori macro da FRED (yield curve, HY spreads, VIX, LEI, CPI,
  Core PCE, Industrial Production, Chicago Fed)
- Detect quadrante All-Weather (Q1–Q4) automatico
- Calcola cruscotto traffic light con 8 indicatori
- Scarica COT Disaggregated CFTC per oil, nat gas, gold, silver, copper, S&P E-mini
- Genera HTML dashboard self-contained con Plotly (6 tab)
- Manda email Gmail SMTP con riepilogo
- GitHub Actions weekly cron

---

## RISORSE DISPONIBILI

- **Account TradingView a pagamento** (Pro o superiore) — accesso a dati
  intraday, screener avanzato, watchlist via API/Pine. Se serve un dato
  che le fonti gratuite non danno bene, valuta TradingView prima di
  scartare l'opzione. Esiste la libreria `tradingview-screener` Python
  che permette query strutturate su tutti i mercati.
- **FRED API key** — gratuita, dovrò registrarmi (mi guidi tu al momento giusto).
- **Gmail con 2FA** — per App Password (mi guidi al momento giusto).
- **GitHub** — non ho ancora creato il repo (mi guidi).
- **Fonti ETF flows da valutare** (in ordine di preferenza):
  1. `tradingview-screener` Python con account TV Pro (più affidabile)
  2. Scraper su `stockanalysis.com/etf/{ticker}/` (HTML pulito)
  3. Scraper su `etf.com/{ticker}` (più dati ma HTML complesso)
  4. Proxy via AUM change da yfinance: `shares_outstanding × price` deltas

---

## OBIETTIVI DI SVILUPPO

### PRIORITÀ ALTA — INDICATORI MANCANTI

1. **NAAIM Exposure Index** — scraper da naaim.org/wp-content/uploads (CSV)
   - Soglia: >90 all-in (rischio top), <40 capitulation (opportunità)

2. **CBOE Put/Call Ratio (Equity)** — scraper da CBOE o ticker Yahoo (^CPCE/^CPC)
   - Soglia: <0.60 euforia, >1.00 panico

3. **ISM Manufacturing PMI vero** — non solo Chicago Fed proxy
   - Opzioni da valutare: scraping tradingeconomics.com, ycharts, S&P Global,
     **oppure tirarlo da TradingView via tradingview-screener** (ho l'account Pro)

4. **Real-time DXY più affidabile** (yfinance a volte zoppica)

5. **Tracciamento storico segnali** — snapshot settimanali in `history/snapshots/
   YYYY-MM-DD.json` per evoluzione cruscotto/quadrante nel tempo

6. **ETF Flows tracking — settori SPDR e tematici**
   - Flussi netti settimanali per ogni ETF monitorato
   - 4 settimane di flussi consecutivi positivi = segnale di accumulo istituzionale
   - Aggiungere come 6° criterio del composite score (diventa 0-6/6)
   - Soglia: flow netto >0 e in trend positivo su 4W = +1 punto
   - Visualizzazione: heatmap flow per settore + chart cumulativo

7. **ETF tematici — espansione universo monitorato**
   Aggiungere oltre ai 10 SPDR settoriali questi ETF tematici (1 per categoria
   per evitare overlap):
   - **AI/Robotica:** BOTZ (più liquido), ROBO (alternativa)
   - **Cybersecurity:** CIBR
   - **Semiconductors:** SMH (più pulito vs SOXX)
   - **Cloud:** SKYY
   - **Clean Energy:** ICLN
   - **Biotech:** XBI
   - **Uranium:** URA
   - **Defense:** ITA
   - **Space:** UFO o ARKX (verifica AUM minimo)
   - **Gold Miners:** GDX
   - **Lithium/Battery:** LIT
   - **Infrastructure:** PAVE
   - **EM:** EEM (proxy aggregato)
   
   Tab dedicato "🚀 Tematici" nella dashboard, separato dai settori SPDR.
   Stesso composite score, stesso framework relative strength vs SPY.
   
   **Filtro qualità da implementare:** scarta automaticamente ETF con
   AUM < $300M o volume medio < $10M/giorno (troppo illiquidi per swing trade).

### PRIORITÀ MEDIA — QUALITÀ DELL'ANALISI

8. **Backtest del composite score** su 10+ anni di dati storici → quanto
   spesso un settore a 4–5/5 sovraperforma SPY nei 6 mesi successivi?
9. **Z-score normalization del COT** (estremi storici percentile vs 5y)
10. **Detection di divergenze**: settore al massimo di prezzo ma score in calo
    = warning di top distributivo
11. **Refinement soglie cruscotto** sulla base dei dati reali (le attuali sono
    da framework teorico)
12. **Confidence interval sul quadrante** (es. "Q2 con 65% conf")

### PRIORITÀ BASSA — FEATURES

13. Cross-asset correlation matrix (rolling 60gg)
14. Settori europei (STOXX600) per confronto vs US
15. Personal portfolio overlay — caricare le mie posizioni effettive
    e mostrare allineamento al quadrante corrente
16. Notifica email solo se cambia il cruscotto (no spam settimanale)
17. Mobile-friendly responsive design

---

## ESTENSIONI FUTURE — IDEE NON ANCORA PIANIFICATE

Idee che potrebbero avere senso ma per ora non sono nel piano sprint.
Non implementarle senza discussione esplicita.

- **Smart money flow ratio** — confronto tra flow ETF settoriali "ufficiali"
  e flow di ETF inverse/leveraged correlati (segnale contrarian)
- **Insider transactions tracker** — Form 4 SEC per i settori top score
- **Short interest tracker** — su FINRA per ogni ETF monitorato
- **Earnings revision breadth** — % titoli del settore con revisioni EPS
  positive ultimi 30gg (richiede fonte come Estimize o scraping Yahoo)
- **News sentiment** — feed RSS per settore con classificazione sentiment
  (LLM-based, costo trascurabile via Anthropic API)
- **Settori europei (STOXX600)** — replica framework su mercato EU
- **Single stock conviction list** — non solo ETF ma anche le singole posizioni
  conviction del mio portafoglio (mappato su `portfolio.json`)

---

## DELIVERABLE FINALE ATTESO

Una dashboard a cui accedo ogni domenica sera che in 5 minuti mi dice:

1. **Stato cruscotto** (semaforo) con confidence
2. **Quadrante macro** corrente con asset action
3. **Top 3 settori SPDR** da watchlist questa settimana
4. **Top 3 tematici** da watchlist (universo separato)
5. **Flussi istituzionali** — quali settori stanno ricevendo soldi
   e quali ne stanno perdendo nelle ultime 4 settimane
6. **COT positioning** sui 6 future chiave (oil, gold, silver, nat gas,
   copper, S&P)
7. **Cambiamenti settimana-su-settimana significativi** (delta score,
   flow inversions, rotazioni in atto)
8. **Posizionamento mio portafoglio** vs teoria del quadrante

Email con oggetto azionabile, esempio:
- 🔴 BUNKER MODE — Cruscotto rosso, ridurre equity
- 🟢 RISK-ON — Healthcare nuovo top score, considera entry
- 🚀 TEMATICO — BOTZ 5/6 e flows positivi 4W consecutive

---

## PIANO SPRINT

### Sprint 0 — Setup + smoke test (PRIMA SESSIONE)

**Obiettivo:** far girare lo script una volta su dati reali, vedere cosa
funziona e cosa no, prima di scrivere una riga di codice nuovo.

1. Leggi `sector_rotation.py`, i due `.docx` e il `README.md`
2. Verifica che `python3` sia installato e quale versione
3. Crea un virtualenv: `python3 -m venv .venv && source .venv/bin/activate`
4. Installa `requirements.txt` e dimmi se ci sono errori
5. **STOP** e guidami a creare la FRED API key passo passo
6. Una volta che ho la key, esportala come variabile d'ambiente
7. Esegui lo script: `python sector_rotation.py --output test_output.html`
8. Mostrami output completo del terminale
9. Apri il file `test_output.html` per verifica visiva (dimmi tu se aprire
   automaticamente o se devo farlo io)
10. Identifica eventuali bug, dati mancanti, fonti che non rispondono
11. Genera un report `SPRINT_0_REPORT.md` con: cosa funziona, cosa no,
    cosa proponi per Sprint 1
12. **Fermati prima di toccare il codice esistente**

### Sprint 1 — Setup GitHub + GitHub Pages + Email (SECONDA SESSIONE)

**Obiettivo:** mettere in produzione la versione attuale, anche se non perfetta,
per avere subito la mail settimanale che funziona.

1. Guidami a creare repository GitHub (passo per passo)
2. Guidami a inizializzare Git localmente, primo commit, push
3. Guidami ad abilitare GitHub Pages
4. Guidami a generare la Gmail App Password
5. Guidami a configurare i Secrets su GitHub
6. Lancia il primo workflow manualmente
7. Verifica che la mail arrivi e il sito sia online
8. Crea `SPRINT_1_REPORT.md` con URL pubblico, stato deploy, eventuali fix

### Sprint 2 — Indicatori sentiment mancanti (SESSIONI 3-4)

1. NAAIM scraper — verifica URL CSV attuale, implementa, testa
2. Put/Call Ratio — valuta CBOE diretto vs Yahoo vs TradingView
3. ISM Manufacturing PMI vero — valuta TradingView con account Pro
4. Aggiorna cruscotto e tab dedicati nella dashboard
5. Re-deploy via push, verifica produzione

### Sprint 3 — ETF Flows (SESSIONI 5-6)

**Obiettivo:** integrare i flussi ETF come 6° criterio del composite score
e nuovo strumento di analisi.

1. **Spike tecnico** — prima di scrivere codice di produzione, scrivi un
   notebook di esplorazione che testa le 4 fonti possibili su 3-4 ETF
   (XLK, XLE, BOTZ) e mostra:
   - Quale fonte risponde con dati più completi
   - Quale ha latenza di pubblicazione minore (giornaliera vs settimanale)
   - Quale è più stabile a fronte di parsing
2. Mostrami il report comparativo, decidiamo insieme la fonte primaria
3. Implementa `fetch_etf_flows()` con la fonte scelta + 1 fallback
4. Aggiungi flows come 6° criterio dello score (4W flows positivi = +1 punto)
5. Nuova heatmap "ETF Flows 4W" nel tab Charts
6. Nel tab COT aggiungi sezione "Flussi ETF Settimanali"
7. Test su dati reali, deploy

### Sprint 4 — ETF Tematici (SESSIONE 7)

**Obiettivo:** estendere l'universo monitorato oltre i 10 SPDR settoriali.

1. Definisci la lista finale di tematici (default: lista in CLAUDE.md
   sezione obiettivo 7) ma chiedimi conferma prima di committarli
2. Implementa filtro qualità AUM/volume — scarta gli illiquidi
3. Estendi `calc_metrics()` e `compute_scores()` per gestire universi separati
   (SPDR settoriali vs Tematici) — non mescolarli nel ranking
4. Nuovo tab "🚀 Tematici" con stesso layout di Scoring ma per i tematici
5. Email update: aggiungi una riga "Top 3 tematici" nel riepilogo settimanale
6. Test su dati reali, deploy

### Sprint 5 — Backtest e calibrazione (SESSIONI 8-9)

1. Backtest composite score su 10 anni
2. Tabella hit-rate per ogni livello di score
3. Calibrazione soglie cruscotto sui risultati
4. Report dettagliato con grafici di performance

### Sprint 6 — History tracking (SESSIONE 10)

1. Snapshot JSON settimanali in `history/snapshots/YYYY-MM-DD.json`
2. Tab "📜 Storia" nella dashboard con timeline ultime 26 settimane
3. Logica "alert solo se cambia stato"

### Sprint 7 — Portfolio overlay (SESSIONI 11+)

1. Schema `portfolio.json` per le mie posizioni reali
2. Tab "💼 Portfolio Match" con confronto vs quadrante teorico
3. Calcolo over/underweight per asset class

---

## MODALITÀ DI LAVORO

### 1. APPROCCIO ITERATIVO

- Affronta UN obiettivo alla volta in ordine di priorità
- Per ogni feature: prima un mini-prototype testabile, poi integrazione
- Esegui sempre lo script con dati reali prima di committare
- Mostrami i print/log dell'esecuzione per validare

### 2. TESTING

- Scrivi unit test per le funzioni di scoring/detection (non per l'HTML)
- Test minimo: la funzione regge dati mancanti, edge case, NaN
- Esegui i test prima di ogni commit

### 3. STANDARDS DI CODICE

- Type hints su tutte le funzioni nuove
- Docstring breve ma esplicita su cosa fa, input, output
- Commenti SOLO quando il "perché" non è ovvio dal codice
- No over-engineering: se una funzione fa il suo lavoro in 20 righe leggibili,
  non astrarla in 5 classi
- **Refactoring trigger:** se aggiungendo feature N lo script supera 2500 righe,
  proponi split in moduli (`data_fetch.py`, `scoring.py`, `html_gen.py`, ecc.)
  PRIMA di iniziare a scriverla

### 4. COMUNICAZIONE

- Quando proponi una decisione tecnica, presentami 2 opzioni con pro/contro,
  non scegliere autonomamente per scelte significative
- Se trovi un'incoerenza nel codice esistente o nel framework, segnalala PRIMA
  di "fixarla"
- Dimmi sempre cosa hai installato/modificato/cancellato
- Quando una fonte dati cambia formato o non è più disponibile, fermati e
  chiedi: non inventare workaround silenziosi

### 5. STILE DELLE RISPOSTE

- Italiano nei commenti, log, output utente, e nelle nostre conversazioni
- Inglese nei nomi delle variabili e funzioni
- Risposta concisa: cosa hai fatto, come, cosa testare ora
- No fronzoli, no preamboli da chatbot

### 6. GIT

- Commit atomici con messaggio chiaro:
  - `feat(naaim): scraper per NAAIM exposure index`
  - `fix(cot): handle missing E-mini codes gracefully`
  - `refactor: split fetching logic into data_fetch module`
- **Non fare push automatico** — chiedimi conferma prima del push

### 7. GUIDA OPERATIVA

- Sono un investitore privato HNW italiano, NON sono un programmatore
- Capisco macro/finanza/COT a livello pratico
- Ogni volta che devo fare qualcosa fuori dal terminale (registrarmi a un
  servizio, configurare GitHub, ecc.) **dammi istruzioni passo-passo
  numerate** come se non lo avessi mai fatto
- Trattami come peer sofisticato sul dominio finanziario, principiante sul
  technical/devops
- Esempi tecnici sempre aggrappati al dominio: "questo evita che un fallimento
  di FRED faccia crashare anche la sezione COT" → meglio di "robust error
  handling pattern"

---

## REGOLE FINALI

- **Mai modificare i file `.docx`** — sono il framework concettuale di
  riferimento, sola lettura
- **Mai pushare codice contenente segreti** (FRED API key, Gmail password)
- **Mai inventare fonti dati** — se non sai se NAAIM ha ancora il CSV pubblico,
  vai a verificarlo prima di scrivere lo scraper
- **Mantieni un `TODO.md`** con stato dei sprint e issue aperte. Aggiornalo
  alla fine di ogni sessione
- **Mantieni un `DECISIONS.md`** dove logghi le scelte tecniche significative
  (es. "abbiamo scelto TradingView API per ISM perché CBOE non espone il dato")