#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  SECTOR ROTATION DASHBOARD — Weekly Analysis Tool            ║
║  Fonti: Yahoo Finance · FRED API (gratuita) · CFTC COT       ║
║  Output: HTML self-contained apribile su qualsiasi browser   ║
╚══════════════════════════════════════════════════════════════╝

Prerequisiti:
  pip install yfinance pandas numpy plotly requests

FRED API Key (GRATUITA — richiede registrazione):
  https://fred.stlouisfed.org/docs/api/api_key.html
  Imposta come variabile d'ambiente: export FRED_API_KEY=tua_chiave
  Oppure modifica FRED_API_KEY = "..." direttamente sotto.

Utilizzo:
  python sector_rotation.py                    # genera dashboard
  python sector_rotation.py --output custom.html
"""

import sys, json, warnings, zipfile, io, os, argparse
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════
#  CONFIGURAZIONE — modifica qui
# ═══════════════════════════════════════════════════════════════

FRED_API_KEY = os.environ.get('FRED_API_KEY', 'YOUR_KEY_HERE')
# Chiave gratuita su: https://fred.stlouisfed.org/docs/api/api_key.html

OUTPUT_FILE = 'sector_rotation_dashboard.html'

# ── Email / Pubblicazione (opzionale) ────────────────────────
# Per Gmail: abilita 2FA → genera App Password su myaccount.google.com/apppasswords
EMAIL_SENDER   = os.environ.get('EMAIL_SENDER',   '')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')
EMAIL_TO       = os.environ.get('EMAIL_TO',       '')
DASHBOARD_URL  = os.environ.get('DASHBOARD_URL',  '')  # es. https://tuonome.github.io/sector-rotation/

SECTORS = {
    'XLK':  'Technology',
    'XLV':  'Healthcare',
    'XLE':  'Energy',
    'XLF':  'Financials',
    'XLI':  'Industrials',
    'XLB':  'Materials',
    'XLU':  'Utilities',
    'XLRE': 'Real Estate',
    'XLP':  'Staples',
    'XLY':  'Discretionary',
}

# ETF Tematici — universo separato dai SPDR settoriali
# Filtro qualità automatico: AUM > $300M e volume medio > $10M/giorno
THEMATICS = {
    'BOTZ': 'AI & Robotics',
    'SMH':  'Semiconductors',
    'CIBR': 'Cybersecurity',
    'IGV':  'Software',
    'SKYY': 'Cloud Computing',
    'XBI':  'Biotech',
    'ICLN': 'Clean Energy',
    'URA':  'Uranium / Nuclear',
    'ITA':  'Aerospace & Defense',
    'GDX':  'Gold Miners',
    'PAVE': 'Infrastructure USA',
    'LIT':  'Lithium & Battery',
    'EEM':  'Emerging Markets',
    'DRIV': 'Autonomous & Drones',
}

# ── Asset addizionali per Cruscotto di Controllo ──────────────
# Yahoo Finance tickers
EXTRA_ASSETS = {
    'DXY':       'DX-Y.NYB',  # Dollar Index
    'MOVE':      '^MOVE',     # Volatility bonds
    'VIX':       '^VIX',      # Volatility S&P (anche su FRED)
    'SKEW':      '^SKEW',     # CBOE SKEW: domanda istituzionale di put OTM
    'VVIX':      '^VVIX',     # VIX del VIX: incertezza sull'incertezza
    'COPPER':    'HG=F',      # Copper futures
    'GOLD':      'GC=F',      # Gold futures
    'SILVER':    'SI=F',      # Silver futures
    'OIL':       'CL=F',      # WTI Crude futures
    'NATGAS':    'NG=F',      # Natural Gas futures
    'TLT':       'TLT',       # 20Y Treasury ETF
    'GLD':       'GLD',       # Gold ETF
}

# Top 10 componenti per settore (per calcolo breadth interna)
COMPONENTS = {
    'XLK':  ['AAPL','MSFT','NVDA','AVGO','AMD','QCOM','NOW','ADBE','CRM','INTU'],
    'XLV':  ['LLY','UNH','JNJ','ABBV','MRK','TMO','DHR','ABT','PFE','BMY'],
    'XLE':  ['XOM','CVX','COP','EOG','SLB','MPC','OXY','PSX','VLO','DVN'],
    'XLF':  ['JPM','BAC','WFC','GS','MS','BLK','C','AXP','SPGI','CB'],
    'XLI':  ['GE','RTX','HON','UPS','CAT','DE','LMT','NOC','ETN','EMR'],
    'XLB':  ['LIN','APD','SHW','FCX','NEM','NUE','ALB','ECL','DD','PPG'],
    'XLU':  ['NEE','SO','DUK','D','AEP','EXC','SRE','XEL','PCG','ED'],
    'XLRE': ['PLD','AMT','EQIX','CCI','PSA','O','WELL','DLR','AVB','EQR'],
    'XLP':  ['PG','KO','PEP','COST','WMT','PM','MO','MDLZ','CL','STZ'],
    'XLY':  ['AMZN','TSLA','HD','MCD','NKE','SBUX','TJX','BKNG','LOW','CMG'],
}

# Codici CFTC per futures rilevanti (COT disaggregated)
# Ordine: rilevanza per cruscotto
COT_CODES = {
    'WTI Crude':   '067651',
    'Natural Gas': '023651',
    'Gold':        '088691',
    'Silver':      '084691',
    'Copper':      '085692',
    'S&P 500':     '13874+',  # E-mini S&P 500 (CME)
}

# Serie FRED da scaricare
FRED_SERIES = {
    'yield_curve': ('T10Y2Y',           '10Y-2Y Spread'),
    'hy_spreads':  ('BAMLH0A0HYM2',     'HY Spreads OAS'),
    'vix':         ('VIXCLS',           'VIX'),
    'lei':         ('USALOLITONOSTSAM', 'LEI USA (OECD)'),
    # Per quadrant detection growth + inflation
    'cpi':         ('CPIAUCSL',         'CPI USA'),                # Inflation gauge
    'core_pce':    ('PCEPILFE',         'Core PCE'),               # Fed preferred
    'indpro':      ('INDPRO',           'Industrial Production'),  # Growth gauge
    'unrate':      ('UNRATE',           'Tasso Disoccupazione USA'),
    'chicago_fed': ('CFNAI',            'Chicago Fed Activity'),   # ISM proxy
}

# ═══════════════════════════════════════════════════════════════
#  DATA FETCHING
# ═══════════════════════════════════════════════════════════════

def _fetch_etf_prices(tickers: list):
    """Helper generico: scarica prezzi close su ~380 giorni per una lista di ticker."""
    import yfinance as yf
    all_t = list(dict.fromkeys(tickers + ['SPY']))  # SPY sempre presente, no duplicati
    end   = datetime.now()
    start = end - timedelta(days=380)
    data  = yf.download(all_t, start=start, end=end,
                        progress=False, auto_adjust=True)['Close']
    return data.dropna(axis=1, thresh=int(len(data) * 0.7))


def fetch_sector_prices():
    """Scarica prezzi ETF settoriali + SPY su 52 settimane via yfinance."""
    print("  ↳ ETF prices (Yahoo Finance)...")
    return _fetch_etf_prices(list(SECTORS.keys()) + ['GLD', 'TLT'])


def fetch_thematic_prices(valid_tickers: list):
    """Scarica prezzi ETF tematici (già filtrati per qualità)."""
    print("  ↳ Thematic ETF prices...")
    return _fetch_etf_prices(valid_tickers)


def calc_metrics(prices, ticker_dict=None):
    """Calcola relative strength, momentum, breadth-proxy e oscillatori.

    ticker_dict: dict {ticker: name}. Default: SECTORS.
    Riutilizzabile per qualsiasi universo ETF (tematici, settoriali, custom).
    """
    import numpy as np, pandas as pd
    if ticker_dict is None:
        ticker_dict = SECTORS
    spy = prices['SPY']

    def safe_ret(series, lookback):
        if len(series) <= lookback: return float('nan')
        return round((series.iloc[-1] / series.iloc[-lookback] - 1) * 100, 2)

    results = {}
    for ticker, name in ticker_dict.items():
        if ticker not in prices.columns:
            continue
        p   = prices[ticker].dropna()
        rel = (p / spy.reindex(p.index)).dropna()

        # Returns
        r1w  = safe_ret(p, 5)
        r4w  = safe_ret(p, 20)
        r12w = safe_ret(p, 60)
        r26w = safe_ret(p, 130)

        # Relative strength vs SPY (excess return %)
        rs4w  = safe_ret(rel, 20)
        rs12w = safe_ret(rel, 60)
        rs26w = safe_ret(rel, 130)

        # MAs
        ma50  = p.rolling(50).mean().iloc[-1]
        ma200 = p.rolling(200).mean().iloc[-1]

        # RSI del ratio (14-period)
        delta = rel.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rsi_r = 100 - 100/(1 + gain/loss.replace(0, 1e-9))
        rsi_ratio = round(rsi_r.iloc[-1], 1)

        # Trend del ratio: confronto tre sottoperiodi da 60gg
        rel60 = rel.iloc[-60:] if len(rel)>=60 else rel
        thirds = len(rel60)//3
        if thirds > 0:
            t1 = rel60.iloc[:thirds].mean()
            t2 = rel60.iloc[thirds:2*thirds].mean()
            t3 = rel60.iloc[2*thirds:].mean()
            ratio_trend = 'UP' if t3>t2>t1 else 'DOWN' if t3<t2<t1 else 'FLAT'
        else:
            ratio_trend = 'FLAT'

        # Volatilità annualizzata 20gg
        vol = round(p.pct_change().rolling(20).std().iloc[-1]*252**0.5*100, 1)

        # Normalizza serie ratio per il chart (base 100 = 130 giorni fa)
        rel_tail = rel.iloc[-130:] if len(rel)>=130 else rel
        base = rel_tail.iloc[0]
        rel_norm = [round(v/base*100, 2) for v in rel_tail]

        results[ticker] = dict(
            name=name, price=round(p.iloc[-1],2),
            r1w=r1w, r4w=r4w, r12w=r12w, r26w=r26w,
            rs4w=rs4w, rs12w=rs12w, rs26w=rs26w,
            ma50=round(ma50,2), ma200=round(ma200,2),
            above_ma50=bool(p.iloc[-1]>ma50),
            above_ma200=bool(p.iloc[-1]>ma200),
            rsi_ratio=rsi_ratio, ratio_trend=ratio_trend, vol=vol,
            rel_norm=rel_norm,
            dates=[d.strftime('%Y-%m-%d') for d in rel_tail.index],
        )
    return results


def calc_breadth(prices):
    """% componenti sopra la MA50 per ogni settore."""
    import yfinance as yf, numpy as np
    print("  ↳ Sector breadth (components vs MA50)...")
    all_tickers = list({t for tl in COMPONENTS.values() for t in tl})
    try:
        comp = yf.download(all_tickers, period='1y',
                           progress=False, auto_adjust=True)['Close']
    except:
        return {}

    result = {}
    for sector, tickers in COMPONENTS.items():
        valid = [t for t in tickers if t in comp.columns]
        if not valid:
            result[sector] = float('nan')
            continue
        above = sum(
            1 for t in valid
            if len(comp[t].dropna()) >= 50
            and comp[t].dropna().iloc[-1] > comp[t].dropna().rolling(50).mean().iloc[-1]
        )
        result[sector] = round(above / len(valid) * 100, 1)
    return result


def fetch_fred_series(series_id, days=540):
    """Scarica una serie FRED (richiede API key gratuita)."""
    import requests
    if FRED_API_KEY == 'YOUR_KEY_HERE':
        return None
    url = 'https://api.stlouisfed.org/fred/series/observations'
    params = dict(
        series_id=series_id, api_key=FRED_API_KEY, file_type='json',
        observation_start=(datetime.now()-timedelta(days=days)).strftime('%Y-%m-%d'),
        sort_order='asc',
    )
    try:
        r   = requests.get(url, params=params, timeout=10)
        obs = r.json().get('observations', [])
        import pandas as pd
        df = pd.DataFrame(obs)
        df['date']  = pd.to_datetime(df['date'])
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        return df.dropna(subset=['value']).set_index('date')['value']
    except:
        return None


def fetch_macro():
    """Scarica tutti gli indicatori macro da FRED."""
    import numpy as np
    print("  ↳ Macro indicators (FRED)...")
    macro = {}
    for key, (sid, label) in FRED_SERIES.items():
        s = fetch_fred_series(sid)
        if s is None or len(s) == 0:
            continue
        curr = s.iloc[-1]
        prev = s.iloc[-5] if len(s) >= 5 else curr
        # YoY per CPI/Core PCE/IndPro
        yoy = None
        if key in ('cpi', 'core_pce', 'indpro') and len(s) >= 13:
            yoy = round((s.iloc[-1] / s.iloc[-13] - 1) * 100, 2)
        macro[key] = dict(
            label=label, current=round(curr,3),
            prev=round(prev,3),
            yoy=yoy,
            direction='UP' if curr > prev else 'DOWN',
            dates=[d.strftime('%Y-%m-%d') for d in s.index[-260:]],
            values=[round(v,3) for v in s.iloc[-260:]],
        )
    return macro


def fetch_extra_assets():
    """Scarica DXY, MOVE, Copper/Gold ratio, futures commodity."""
    import yfinance as yf, pandas as pd
    print("  ↳ Extra assets (DXY, MOVE, futures)...")
    assets = {}
    end   = datetime.now()
    start = end - timedelta(days=380)
    for label, ticker in EXTRA_ASSETS.items():
        try:
            df = yf.download(ticker, start=start, end=end,
                             progress=False, auto_adjust=True)['Close']
            if df is None or len(df) == 0:
                continue
            # yfinance 1.3.0 restituisce DataFrame a colonna singola per singolo ticker
            if hasattr(df, 'squeeze'):
                df = df.squeeze()
            s = df.dropna() if hasattr(df, 'dropna') else df
            if len(s) < 5:
                continue
            curr = float(s.iloc[-1])
            prev_w = float(s.iloc[-5])  if len(s) >=  5 else curr
            prev_m = float(s.iloc[-22]) if len(s) >= 22 else curr
            prev_q = float(s.iloc[-66]) if len(s) >= 66 else curr
            assets[label] = dict(
                ticker=ticker,
                current=round(curr, 4),
                ret_1w=round((curr/prev_w-1)*100, 2),
                ret_1m=round((curr/prev_m-1)*100, 2),
                ret_3m=round((curr/prev_q-1)*100, 2),
                direction='UP' if curr > prev_w else 'DOWN',
                dates=[d.strftime('%Y-%m-%d') for d in s.index[-130:]],
                values=[round(float(v),4) for v in s.iloc[-130:]],
            )
        except Exception as e:
            print(f"    {label} ({ticker}) fallito: {e}")

    # Calcola Copper/Gold ratio
    if 'COPPER' in assets and 'GOLD' in assets:
        copper = assets['COPPER']
        gold   = assets['GOLD']
        # Allinea le date
        c_dict = dict(zip(copper['dates'], copper['values']))
        g_dict = dict(zip(gold['dates'],   gold['values']))
        common = sorted(set(c_dict.keys()) & set(g_dict.keys()))
        if len(common) > 5:
            ratio_vals  = [round(c_dict[d]/g_dict[d], 6) for d in common]
            curr_r  = ratio_vals[-1]
            prev_w  = ratio_vals[-5]  if len(ratio_vals) >=  5 else curr_r
            prev_m  = ratio_vals[-22] if len(ratio_vals) >= 22 else curr_r
            assets['COPPER_GOLD'] = dict(
                ticker='HG/GC',
                current=curr_r,
                ret_1w=round((curr_r/prev_w-1)*100, 2),
                ret_1m=round((curr_r/prev_m-1)*100, 2),
                ret_3m=round((curr_r/ratio_vals[-66]-1)*100, 2) if len(ratio_vals)>=66 else 0,
                direction='UP' if curr_r > prev_w else 'DOWN',
                dates=common[-130:],
                values=ratio_vals[-130:],
            )
    return assets


def fetch_naaim():
    """NAAIM Exposure Index — scarica xlsx dalla pagina NAAIM (aggiornato ogni mercoledì).

    Soglie operative:
      > 90  = gestori all-in → rischio di top distributivo (🔴)
      60-90 = posizionamento normale-rialzista (🟡)
      40-60 = neutrale (🟢)
      < 40  = capitolazione → opportunità contrarian (🟢 forte)
    """
    import requests, io
    from bs4 import BeautifulSoup
    print("  ↳ NAAIM Exposure Index...")
    try:
        page = requests.get(
            'https://www.naaim.org/programs/naaim-exposure-index/',
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(page.text, 'html.parser')
        xlsx_url = next(
            (a['href'] for a in soup.find_all('a', href=True)
             if 'xlsx' in a['href'].lower()),
            None)
        if not xlsx_url:
            print("    NAAIM: link xlsx non trovato nella pagina")
            return None

        import pandas as pd
        r = requests.get(xlsx_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
        df = pd.read_excel(io.BytesIO(r.content), engine='openpyxl')
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date']).sort_values('Date')

        current  = round(float(df['NAAIM Number'].iloc[-1]), 1)
        prev_w   = round(float(df['NAAIM Number'].iloc[-2]), 1) if len(df) >= 2 else current
        date_str = df['Date'].iloc[-1].strftime('%Y-%m-%d')
        history  = [
            dict(date=row['Date'].strftime('%Y-%m-%d'),
                 value=round(float(row['NAAIM Number']), 1))
            for _, row in df.tail(26).iterrows()
        ]
        return dict(current=current, prev=prev_w,
                    change=round(current - prev_w, 1),
                    date=date_str, history=history)
    except Exception as e:
        print(f"    NAAIM fallito: {e}")
        return None


def fetch_cot():
    """Scarica COT Disaggregated da CFTC (zip pubblico, no auth).

    URL aggiornato 2026: CFTC ha spostato i file su /files/dea/history/fut_disagg_txt_YYYY.zip
    Contiene tutto l'anno corrente aggiornato settimanalmente.
    Fallback all'anno precedente se il file corrente non è ancora disponibile.
    """
    import requests, numpy as np
    print("  ↳ COT Report (CFTC.gov)...")
    year = datetime.now().year
    urls = [
        f'https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip',
        f'https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year-1}.zip',
    ]
    r = None
    for url in urls:
        try:
            resp = requests.get(url, timeout=60,
                                headers={'User-Agent': 'Mozilla/5.0'})
            if resp.status_code == 200 and resp.content[:4] == b'PK\x03\x04':
                r = resp
                break
        except Exception:
            continue
    if r is None:
        print("    COT: nessun URL CFTC raggiungibile")
        return {}
    try:
        z  = zipfile.ZipFile(io.BytesIO(r.content))
        fn = next(f for f in z.namelist() if f.endswith(('.csv','.txt')))

        import pandas as pd
        with z.open(fn) as f:
            df = pd.read_csv(f, encoding='latin-1', low_memory=False)

        out = {}
        for name, code in COT_CODES.items():
            # 13874+ è un fuzzy match per E-mini S&P 500
            code_clean = code.rstrip('+')
            df['CFTC_Contract_Market_Code'] = df['CFTC_Contract_Market_Code'].astype(str).str.strip()
            sub = df[df['CFTC_Contract_Market_Code'].str.startswith(code_clean)]
            if sub.empty:
                # Fallback su nome
                word = name.split()[0]
                sub  = df[df['Market_and_Exchange_Names']
                          .str.contains(word, case=False, na=False)]
            if sub.empty:
                continue

            # Per S&P, prendiamo solo E-MINI S&P 500
            if 'S&P' in name:
                sub = sub[sub['Market_and_Exchange_Names']
                          .str.contains('E-MINI', case=False, na=False)]
                if sub.empty:
                    continue

            sub = sub.sort_values('Report_Date_as_YYYY-MM-DD')
            row = sub.iloc[-1]

            def to_int(col, r=row):
                v = str(r.get(col,0)).replace(',','').strip()
                try: return int(float(v))
                except: return 0

            mm_long  = to_int('M_Money_Positions_Long_All')
            mm_short = to_int('M_Money_Positions_Short_All')
            mm_net   = mm_long - mm_short

            if len(sub) >= 2:
                pr = sub.iloc[-2]
                prev_net = to_int('M_Money_Positions_Long_All', r=pr) - \
                           to_int('M_Money_Positions_Short_All', r=pr)
                change   = mm_net - prev_net
            else:
                change = 0

            # Storia ultime 26 settimane per il chart
            history = []
            for _, hr in sub.tail(26).iterrows():
                hl = to_int('M_Money_Positions_Long_All', r=hr)
                hs = to_int('M_Money_Positions_Short_All', r=hr)
                history.append(dict(
                    date=str(hr.get('Report_Date_as_YYYY-MM-DD','')),
                    net=hl - hs
                ))

            out[name] = dict(
                mm_long=mm_long, mm_short=mm_short,
                mm_net=mm_net, change=change,
                sentiment='BULLISH' if mm_net>0 else 'BEARISH',
                direction='↑' if change>0 else '↓',
                date=str(row.get('Report_Date_as_YYYY-MM-DD','')),
                history=history,
            )
        return out
    except Exception as e:
        print(f"    COT non disponibile: {e}")
        return {}


# ═══════════════════════════════════════════════════════════════
#  ETF FLOWS (proxy via AUM / NAV da yfinance)
# ═══════════════════════════════════════════════════════════════

def fetch_etf_flows(tickers: list) -> dict:
    """Flow settimanale stimato: Δquote_implicite × NAV.

    quote_implicite = totalAssets / navPrice  (da yfinance.Ticker.info)
    Flow_netto_1W   = (quote_oggi − quote_scorsa_settimana) × NAV_oggi  [in M$]
    Segnale 4W      = 4 settimane consecutive di flow positivo = accumulo istituzionale.

    Storico salvato in history/flows_cache.json (max 8 snapshot).
    Prima run: flows N/A per mancanza di storico. Si auto-popola settimana dopo settimana.
    """
    import yfinance as yf, json
    from pathlib import Path
    print("  ↳ ETF flows (AUM proxy via yfinance)...")

    cache_path = Path('history/flows_cache.json')
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    except Exception:
        cache = {}

    today    = datetime.now().strftime('%Y-%m-%d')
    min_days = 5   # gap minimo tra snapshot (evita duplicati infrasettimanali)
    flows    = {}

    for ticker in tickers:
        try:
            info  = yf.Ticker(ticker).info
            aum   = info.get('totalAssets')
            nav   = info.get('navPrice') or info.get('regularMarketPrice')
            if not aum or not nav or nav == 0:
                continue

            shares_now = aum / nav
            hist = cache.get(ticker, [])  # lista {date, shares, nav}

            # ── Flow 1W ──────────────────────────────────────────
            flow_1w = None
            if hist:
                last = hist[-1]
                from datetime import datetime as dt
                days_diff = (dt.strptime(today, '%Y-%m-%d') -
                             dt.strptime(last['date'], '%Y-%m-%d')).days
                if days_diff >= min_days:
                    flow_1w = round((shares_now - last['shares']) * nav / 1e6, 1)

            # ── Flows storici (per segnale 4W) ───────────────────
            historical_flows = []
            for i in range(len(hist) - 1):
                curr_snap = hist[i + 1]
                prev_snap = hist[i]
                delta = (curr_snap['shares'] - prev_snap['shares']) * curr_snap['nav'] / 1e6
                historical_flows.append(round(delta, 1))

            # Aggiunge il flow corrente alla fine
            if flow_1w is not None:
                historical_flows.append(flow_1w)

            last4 = historical_flows[-4:]
            signal_4w = len(last4) == 4 and all(f > 0 for f in last4)

            flows[ticker] = dict(
                flow_1w=flow_1w,
                flows_4w=last4,
                signal_4w=signal_4w,
                aum_b=round(aum / 1e9, 2),
                nav=round(nav, 2),
            )

            # ── Aggiorna cache ────────────────────────────────────
            if not hist or hist[-1]['date'] != today:
                from datetime import datetime as dt
                if not hist or (dt.strptime(today, '%Y-%m-%d') -
                                dt.strptime(hist[-1]['date'], '%Y-%m-%d')).days >= min_days:
                    hist.append({'date': today, 'shares': shares_now, 'nav': nav})
                    hist = hist[-8:]  # max 8 settimane
            cache[ticker] = hist

        except Exception as e:
            print(f"    {ticker} flow fallito: {e}")

    try:
        cache_path.write_text(json.dumps(cache, indent=2))
    except Exception as e:
        print(f"    Cache flows non salvata: {e}")

    return flows


def filter_quality_etfs(tickers: list, min_aum_m: float = 300, min_vol_m: float = 10) -> tuple:
    """Filtra ETF per qualità: AUM > min_aum_m M$ e volume medio > min_vol_m M$/giorno.

    Returns (valid: list, excluded: list[tuple(ticker, motivo)]).
    ETF che non passano il filtro vengono esclusi dall'universo tematici.
    """
    import yfinance as yf
    valid, excluded = [], []
    for ticker in tickers:
        try:
            info    = yf.Ticker(ticker).info
            aum     = (info.get('totalAssets') or 0) / 1e6
            nav     = info.get('navPrice') or info.get('regularMarketPrice') or 0
            avg_vol = (info.get('averageVolume') or 0) * nav / 1e6
            if aum >= min_aum_m and avg_vol >= min_vol_m:
                valid.append(ticker)
            else:
                reason = f"AUM={aum:.0f}M$ · vol={avg_vol:.1f}M$/giorno"
                excluded.append((ticker, reason))
        except Exception as e:
            excluded.append((ticker, str(e)))
    return valid, excluded


# ═══════════════════════════════════════════════════════════════
#  SCORING
# ═══════════════════════════════════════════════════════════════

def compute_scores(metrics, breadth, cot, etf_flows=None):
    """Composite score 0–6 per settore (5 criteri tecnici + 1 flow istituzionale)."""
    import math
    if etf_flows is None:
        etf_flows = {}
    scores = {}
    for ticker, m in metrics.items():
        pts, details = 0, []

        def chk(cond, label, val):
            nonlocal pts
            if cond: pts += 1
            details.append((label, '✓' if cond else '✗', val, cond))

        rs4  = m['rs4w']  if not (isinstance(m['rs4w'],float) and math.isnan(m['rs4w'])) else -999
        rs12 = m['rs12w'] if not (isinstance(m['rs12w'],float) and math.isnan(m['rs12w'])) else -999

        chk(rs4  > 0,    'RS 4W vs SPY',
            f"{'+' if rs4>=0 else ''}{rs4}%")
        chk(m['ratio_trend'] == 'UP', 'Trend Ratio',
            m['ratio_trend'])
        b = breadth.get(ticker, float('nan'))
        b_ok = not math.isnan(b) and b >= 40
        chk(b_ok, 'Breadth >40%',
            f"{b}%" if not math.isnan(b) else 'N/A')
        chk(rs12 > 0,    'RS 12W vs SPY',
            f"{'+' if rs12>=0 else ''}{rs12}%")
        chk(m['rsi_ratio'] > 50, 'RSI Ratio >50',
            str(m['rsi_ratio']))

        # 6° criterio: flows istituzionali 4W positivi
        fd = etf_flows.get(ticker, {})
        f1w = fd.get('flow_1w')
        f4w_ok = fd.get('signal_4w', False)
        f_val = (f'1W:{f1w:+.0f}M$ · 4W:{"✓" if f4w_ok else "…"}' if f1w is not None
                 else 'N/A (prima run)')
        chk(f4w_ok, 'Flows 4W positivi', f_val)

        # COT link per settori commodity
        cot_note = None
        if ticker == 'XLE':
            d = cot.get('WTI Crude', {})
            if d:
                cot_note = f"WTI COT: MM Net {d.get('mm_net',0):+,} {d.get('direction','')}"
        elif ticker == 'XLB':
            d = cot.get('Copper', {})
            if d:
                cot_note = f"Copper COT: MM Net {d.get('mm_net',0):+,} {d.get('direction','')}"
        elif ticker == 'XLU' or ticker == 'XLV':
            d = cot.get('Gold', {})
            if d:
                cot_note = f"Gold COT: MM Net {d.get('mm_net',0):+,} {d.get('direction','')}"

        sig   = 'FORTE' if pts>=5 else 'MODERATO' if pts==4 else 'DEBOLE' if pts>=2 else 'NEGATIVO'
        color = '#22c55e' if pts>=5 else '#f59e0b' if pts==4 else '#f97316' if pts>=2 else '#ef4444'
        scores[ticker] = dict(score=pts, max_score=6, signal=sig, color=color,
                               details=details, cot_note=cot_note)
    return scores


# ═══════════════════════════════════════════════════════════════
#  MACRO QUADRANT DETECTION (modello All-Weather)
# ═══════════════════════════════════════════════════════════════

def detect_quadrant(macro):
    """Identifica il quadrante macro: Goldilocks / Reflazione / Stagflazione / Deflazione.

    Asse Crescita: direzione di Industrial Production YoY + LEI
    Asse Inflazione: direzione di CPI YoY + Core PCE YoY

    Returns dict completo con quadrante, descrizione, asset vincenti/perdenti.
    """
    # ── Crescita: positiva se IP YoY in salita E LEI in salita ──
    growth_up = None
    growth_signals = []

    if 'indpro' in macro and macro['indpro'].get('yoy') is not None:
        ip_yoy = macro['indpro']['yoy']
        # IP YoY > 0 = espansione
        growth_signals.append(ip_yoy > 0)
    if 'lei' in macro:
        lei_dir = macro['lei'].get('direction','FLAT')
        growth_signals.append(lei_dir == 'UP')
    if 'chicago_fed' in macro:
        cf = macro['chicago_fed'].get('current', 0)
        # Chicago Fed Activity Index: > 0 = sopra trend
        growth_signals.append(cf > -0.2)

    if growth_signals:
        growth_up = sum(growth_signals) > len(growth_signals)/2

    # ── Inflazione: positiva se CPI YoY in salita E sopra target ──
    inflation_up = None
    infl_signals = []

    if 'cpi' in macro and macro['cpi'].get('yoy') is not None:
        cpi_yoy = macro['cpi']['yoy']
        # CPI YoY > 2.5% = sopra target Fed
        infl_signals.append(cpi_yoy > 2.5)
    if 'core_pce' in macro and macro['core_pce'].get('yoy') is not None:
        pce_yoy = macro['core_pce']['yoy']
        # Core PCE > 2.5% = sopra target Fed
        infl_signals.append(pce_yoy > 2.5)

    if infl_signals:
        inflation_up = sum(infl_signals) > len(infl_signals)/2

    # ── Quadrante ───────────────────────────────────────────────
    if growth_up is None or inflation_up is None:
        # Fallback su yield curve + HY spreads se mancano dati FRED
        return _fallback_quadrant(macro)

    if growth_up and not inflation_up:
        q_id = 'Q1'
        q_name = 'GOLDILOCKS 🟢'
        q_color = '#22c55e'
        q_desc = 'Crescita in espansione, inflazione contenuta. Scenario ideale per asset di rischio: utili in salita, tassi stabili, liquidità abbondante.'
        winners = dict(
            equity=['XLK Tech', 'XLY Discretionary', 'Quality (XDEQ)', 'Growth large cap'],
            credit=['Corporate IG', 'High Yield (selettivo)'],
            real_assets=['Real Estate (REIT)'],
            other=[],
        )
        losers = ['Cash (rende poco)', 'Oro (no fear trade)', 'Commodities deboli']
        portfolio_action = 'Mantieni equity al target. PAC regolare. Considera tilt verso Quality e Growth large cap.'
    elif growth_up and inflation_up:
        q_id = 'Q2'
        q_name = 'REFLAZIONE 🟡'
        q_color = '#f59e0b'
        q_desc = 'Economia surriscaldata: domanda > offerta. Banche Centrali iniziano ad alzare i tassi, ma utili aziendali tengono ancora.'
        winners = dict(
            equity=['XLE Energy', 'XLB Materials', 'XLF Banks', 'XLI Industrials'],
            credit=['TIPS / BTP Italia (inflation-linked)'],
            real_assets=['Petrolio', 'Rame', 'Energy stocks (Exxon/Eni)'],
            other=[],
        )
        losers = ['Bond lunga scadenza nominali', 'Tech speculativo / Growth caro', 'Bond duration alta']
        portfolio_action = 'Riduci duration nominale. Aggiungi commodities e value. BTP Italia per protezione inflazione.'
    elif (not growth_up) and inflation_up:
        q_id = 'Q3'
        q_name = 'STAGFLAZIONE 🔴'
        q_color = '#ef4444'
        q_desc = 'Lo scenario peggiore: prezzi salgono ma economia rallenta. Azioni e bond scendono insieme (correlazione positiva). Il 60/40 viene massacrato.'
        winners = dict(
            equity=['XLE Energy stocks', 'Healthcare difensivo (XLV)'],
            credit=['TIPS', 'BTP Italia', 'Cash (XEON, CSH2)'],
            real_assets=['Oro (SGLD)', 'Materie prime energetiche'],
            other=['Liquidità alta'],
        )
        losers = ['60/40 tradizionale', 'Growth (multipli compressi)', 'Bond nominali lunghi', 'High Yield']
        portfolio_action = 'BUNKER MODE. Aumenta oro e inflation-linked. Riduci equity growth. Cash pronto per ribassi.'
    else:
        q_id = 'Q4'
        q_name = 'DEFLAZIONE / RECESSIONE 🔵'
        q_color = '#3b82f6'
        q_desc = 'Crisi finanziaria o recessione dura. Disoccupazione sale, domanda crolla, prezzi scendono. "Cash is King". Tassi crollano = bond nominali esplodono.'
        winners = dict(
            equity=['Healthcare (XLV)', 'Staples (XLP)', 'Utilities (XLU)'],
            credit=['Treasuries lunghi (TLT)', 'BTP/Bund 20Y nominali', 'Cash'],
            real_assets=['Oro (panic hedge)'],
            other=['Opzioni PUT su SPY', 'USD strong'],
        )
        losers = ['Equity (tutto, -20/40%)', 'Commodities (no demand)', 'High Yield (default wave)', 'Real estate (mutui in calo aiuta poco)']
        portfolio_action = 'Aumenta Treasury 20Y e Bund/BTP nominali. Considera PUT SPY come hedge. Cash al massimo storico target.'

    return dict(
        id=q_id,
        name=q_name,
        color=q_color,
        description=q_desc,
        growth_up=growth_up,
        inflation_up=inflation_up,
        winners=winners,
        losers=losers,
        portfolio_action=portfolio_action,
        # Per il regime banner sui settori
        favored=_quadrant_to_sectors(q_id),
        unfavored=_quadrant_to_unfavored(q_id),
    )


def _quadrant_to_sectors(q_id):
    return {
        'Q1': ['XLK','XLY','XLF','XLI'],
        'Q2': ['XLE','XLB','XLF','XLI'],
        'Q3': ['XLE','XLV','XLU','XLP'],
        'Q4': ['XLV','XLU','XLP'],
    }.get(q_id, [])


def _quadrant_to_unfavored(q_id):
    return {
        'Q1': ['XLU','XLP'],
        'Q2': ['XLK','XLRE'],
        'Q3': ['XLY','XLK','XLRE'],
        'Q4': ['XLE','XLB','XLY','XLK','XLF'],
    }.get(q_id, [])


def _fallback_quadrant(macro):
    """Quadrant detection di fallback se mancano dati CPI/IP."""
    yc = macro.get('yield_curve', {}).get('current', 0)
    hy = macro.get('hy_spreads',  {}).get('current', 4)

    if yc > 0.5 and hy < 3.5:
        q_id, q_name, q_color = 'Q1', 'GOLDILOCKS 🟢', '#22c55e'
    elif yc > -0.3 and hy >= 3.5:
        q_id, q_name, q_color = 'Q2', 'REFLAZIONE / LATE CYCLE 🟡', '#f59e0b'
    elif yc <= -0.3 and hy >= 4.5:
        q_id, q_name, q_color = 'Q3', 'STAGFLAZIONE / RECESSIONE 🔴', '#ef4444'
    else:
        q_id, q_name, q_color = 'Q4', 'DEFLAZIONE / RECESSIONE 🔵', '#3b82f6'

    return dict(
        id=q_id, name=q_name, color=q_color,
        description='Quadrante derivato da yield curve + HY spreads (FRED CPI/IP non disponibili).',
        growth_up=None, inflation_up=None,
        winners=dict(equity=[], credit=[], real_assets=[], other=[]),
        losers=[],
        portfolio_action='Configura FRED_API_KEY per detection completa con CPI + Industrial Production.',
        favored=_quadrant_to_sectors(q_id),
        unfavored=_quadrant_to_unfavored(q_id),
    )


# ═══════════════════════════════════════════════════════════════
#  CRUSCOTTO DI CONTROLLO — Traffic Light Synthesis
# ═══════════════════════════════════════════════════════════════

def compute_cruscotto(macro, assets, cot, naaim=None):
    """Sintesi semaforo basata sul cruscotto di controllo.

    Verifica le condizioni dei tre scenari:
    - VERDE  (Risk-On):    ISM-proxy > 0, HY < 3.5%, Put/Call > 0.8 [se disp]
    - GIALLO (Late Cycle): Yield Curve in dis-inversione, ISM-proxy < 0
    - ROSSO  (Risk-Off):   HY > 5%, Copper/Gold in calo, DXY > 105
    """
    indicators = []

    # ── 1. ISM proxy via Chicago Fed Activity (≈ ISM Manufacturing) ───
    if 'chicago_fed' in macro:
        cf = macro['chicago_fed']['current']
        if cf > 0.2:
            ind_status = 'VERDE'; ind_msg = f'Attività manifatturiera robusta ({cf:.2f})'
        elif cf > -0.2:
            ind_status = 'GIALLO'; ind_msg = f'Crescita sotto trend ({cf:.2f})'
        else:
            ind_status = 'ROSSO'; ind_msg = f'Attività in contrazione ({cf:.2f}) — recessione'
        indicators.append(dict(
            name='Chicago Fed (ISM proxy)',
            ticker='FRED:CFNAI',
            status=ind_status, value=f'{cf:+.2f}',
            message=ind_msg, threshold='> +0.2 verde · < -0.2 rosso'
        ))

    # ── 2. HY Spread ────────────────────────────────────────────
    if 'hy_spreads' in macro:
        hy = macro['hy_spreads']['current']
        hy_dir = macro['hy_spreads']['direction']
        if hy < 3.5:
            ind_status = 'VERDE'; ind_msg = 'Credito sereno, banche prestano'
        elif hy < 5.0:
            ind_status = 'GIALLO'; ind_msg = 'Spread in espansione, attenzione'
        else:
            ind_status = 'ROSSO'; ind_msg = 'Stress creditizio severo'
        indicators.append(dict(
            name='HY Spreads OAS',
            ticker='FRED:BAMLH0A0HYM2',
            status=ind_status, value=f'{hy:.2f}%',
            message=ind_msg + (f' (in {("salita ↑" if hy_dir=="UP" else "discesa ↓")})'),
            threshold='< 3.5% verde · > 4.5% giallo · > 5% rosso'
        ))

    # ── 3. Yield Curve 10Y-2Y ───────────────────────────────────
    if 'yield_curve' in macro:
        yc = macro['yield_curve']['current']
        yc_dir = macro['yield_curve']['direction']
        if yc > 0.3 and yc_dir == 'UP':
            # Dis-inversione completata = warning recessione storica
            ind_status = 'GIALLO'; ind_msg = 'Curva si normalizza dopo inversione = SEGNALE storico di recessione imminente'
        elif yc > 0:
            ind_status = 'VERDE'; ind_msg = 'Curva positiva, espansione'
        elif yc_dir == 'UP':
            ind_status = 'GIALLO'; ind_msg = 'Curva ancora invertita ma in re-steepening = transizione'
        else:
            ind_status = 'ROSSO'; ind_msg = 'Curva invertita, recessione attesa nei prossimi 12-18M'
        indicators.append(dict(
            name='Yield Curve 10Y-2Y',
            ticker='FRED:T10Y2Y',
            status=ind_status, value=f'{yc:+.2f}%',
            message=ind_msg,
            threshold='dis-inversione rapida = pre-recessione'
        ))

    # ── 4. Copper/Gold Ratio ────────────────────────────────────
    if 'COPPER_GOLD' in assets:
        cg = assets['COPPER_GOLD']
        ret_3m = cg['ret_3m']
        if ret_3m > 5:
            ind_status = 'VERDE'; ind_msg = 'Crescita batte paura → ciclico bullish'
        elif ret_3m > -5:
            ind_status = 'GIALLO'; ind_msg = 'Stabile, segnale ambiguo'
        else:
            ind_status = 'ROSSO'; ind_msg = 'Oro batte rame → fear trade attivo, preparare difese'
        indicators.append(dict(
            name='Copper/Gold Ratio',
            ticker='HG/GC',
            status=ind_status, value=f'{cg["current"]:.5f}',
            message=ind_msg + f' (3M: {"+" if ret_3m>=0 else ""}{ret_3m}%)',
            threshold='in salita = risk-on · in calo = risk-off'
        ))

    # ── 5. Dollar Index (DXY) ───────────────────────────────────
    if 'DXY' in assets:
        dxy = assets['DXY']
        v = dxy['current']
        if v < 100:
            ind_status = 'VERDE'; ind_msg = 'Dollaro debole, sostegno commodities ed EM'
        elif v < 105:
            ind_status = 'GIALLO'; ind_msg = 'Dollaro moderato'
        else:
            ind_status = 'ROSSO'; ind_msg = 'Dollaro troppo forte → stress sistemico globale'
        indicators.append(dict(
            name='Dollar Index (DXY)',
            ticker='DX-Y.NYB',
            status=ind_status, value=f'{v:.1f}',
            message=ind_msg + f' (1M: {"+" if dxy["ret_1m"]>=0 else ""}{dxy["ret_1m"]}%)',
            threshold='< 100 verde · 100-105 giallo · > 105 rosso'
        ))

    # ── 6. MOVE Index (bond volatility) ─────────────────────────
    if 'MOVE' in assets:
        mv = assets['MOVE']
        v = mv['current']
        if v < 100:
            ind_status = 'VERDE'; ind_msg = 'Mercato bond stabile'
        elif v < 130:
            ind_status = 'GIALLO'; ind_msg = 'Volatilità bond elevata'
        else:
            ind_status = 'ROSSO'; ind_msg = 'Stress severo sui bond → rischio sistemico'
        indicators.append(dict(
            name='MOVE Index (bond VIX)',
            ticker='^MOVE',
            status=ind_status, value=f'{v:.1f}',
            message=ind_msg,
            threshold='< 100 verde · 100-130 giallo · > 130 rosso'
        ))

    # ── 7. VIX ──────────────────────────────────────────────────
    if 'vix' in macro:
        vx = macro['vix']['current']
        if vx < 18:
            ind_status = 'VERDE'; ind_msg = 'Bassa volatilità, complacency'
        elif vx < 28:
            ind_status = 'GIALLO'; ind_msg = 'Volatilità normale'
        else:
            ind_status = 'ROSSO'; ind_msg = 'Stress di mercato — opportunità contrarian a -20/30%'
        indicators.append(dict(
            name='VIX',
            ticker='^VIX',
            status=ind_status, value=f'{vx:.1f}',
            message=ind_msg,
            threshold='< 18 verde · 18-28 giallo · > 28 rosso'
        ))

    # ── 8. NAAIM Exposure Index ──────────────────────────────────
    if naaim:
        nv = naaim['current']
        nc = naaim['change']
        if nv > 90:
            ind_status = 'ROSSO'
            ind_msg = f'Gestori all-in ({nv}) → rischio di top distributivo, posizionamento estremo'
        elif nv > 75:
            ind_status = 'GIALLO'
            ind_msg = f'Gestori molto rialzisti ({nv}) → euforia crescente'
        elif nv < 40:
            ind_status = 'VERDE'
            ind_msg = f'Capitolazione ({nv}) → opportunità contrarian, gestori in fuga'
        else:
            ind_status = 'VERDE'
            ind_msg = f'Posizionamento normale ({nv})'
        indicators.append(dict(
            name='NAAIM Exposure Index',
            ticker='naaim.org',
            status=ind_status, value=f'{nv}',
            message=ind_msg + f' (WoW: {"+" if nc>=0 else ""}{nc})',
            threshold='> 90 rosso · 75-90 giallo · < 40 verde (capitolazione)'
        ))

    # ── 9. SKEW Index (domanda istituzionale di protezione) ──────
    if 'SKEW' in assets:
        sk = assets['SKEW']['current']
        sk_1m = assets['SKEW']['ret_1m']
        if sk > 145:
            ind_status = 'ROSSO'
            ind_msg = f'Istituzioni in forte acquisto di puts OTM — tail risk percepito alto'
        elif sk > 130:
            ind_status = 'GIALLO'
            ind_msg = f'Protezione istituzionale elevata — mercato nervoso'
        else:
            ind_status = 'VERDE'
            ind_msg = f'Skew basso — scarsa domanda di protezione, euforia o compiacenza'
        indicators.append(dict(
            name='CBOE SKEW Index',
            ticker='^SKEW',
            status=ind_status, value=f'{sk:.0f}',
            message=ind_msg + f' (1M: {"+" if sk_1m>=0 else ""}{sk_1m}%)',
            threshold='< 130 verde · 130-145 giallo · > 145 rosso'
        ))

    # ── Aggregato semaforo finale ───────────────────────────────
    counts = {'VERDE':0, 'GIALLO':0, 'ROSSO':0}
    for i in indicators:
        counts[i['status']] += 1

    n = max(1, len(indicators))
    pct_red = counts['ROSSO'] / n
    pct_green = counts['VERDE'] / n

    if counts['ROSSO'] >= 3 or pct_red >= 0.4:
        overall = 'ROSSO'
        scenario = 'SCENARIO C — RISK-OFF / BUNKER'
        action = ('Vendere parte azionario per liquidità · Aumentare oro e Treasury/Bund · '
                  'NON comprare il primo ribasso (-10%) · Aspettare capitolazione (-20/30%) o intervento Fed')
        color = '#ef4444'
    elif counts['ROSSO'] >= 1 or counts['GIALLO'] >= 4 or pct_green < 0.4:
        overall = 'GIALLO'
        scenario = 'SCENARIO B — LATE CYCLE / ATTENZIONE'
        action = ('Smettere di comprare speculativi (small cap, crypto minori) · '
                  'Accumulare liquidità (XEON/CSH2) · Attivare coperture (PUT mentre VIX è basso) · '
                  'Mantenere core difensivo')
        color = '#f59e0b'
    else:
        overall = 'VERDE'
        scenario = 'SCENARIO A — RISK-ON'
        action = ('Mantenere equity al target di portafoglio · Eseguire PAC regolarmente · '
                  'Considerare aumento esposizione su settori favoriti dal quadrante macro')
        color = '#22c55e'

    return dict(
        overall=overall,
        scenario=scenario,
        color=color,
        action=action,
        counts=counts,
        indicators=indicators,
    )


# ═══════════════════════════════════════════════════════════════
#  HTML GENERATION
# ═══════════════════════════════════════════════════════════════

def _nan_safe(v, decimals=2):
    import math
    if isinstance(v, float) and math.isnan(v): return None
    try: return round(float(v), decimals)
    except: return None

def generate_html(metrics, scores, breadth, macro, cot, quadrant, cruscotto, assets, naaim=None,
                  thematic_metrics=None, thematic_scores=None, thematic_excluded=None):
    import math

    updated = datetime.now().strftime('%d %B %Y — %H:%M')

    # Sort settori per score
    sorted_s = sorted(
        [(t,m,scores.get(t,{})) for t,m in metrics.items()],
        key=lambda x: x[2].get('score',0), reverse=True
    )

    # ── Cruscotto bar (NEW) ─────────────────────────────────────
    crusc_color = cruscotto.get('color', '#666')
    crusc_overall = cruscotto.get('overall', '—')
    crusc_scenario = cruscotto.get('scenario', '')
    crusc_action = cruscotto.get('action', '')
    crusc_counts = cruscotto.get('counts', {})
    crusc_indicators = cruscotto.get('indicators', [])

    crusc_indicators_html = ''
    for i in crusc_indicators:
        st = i.get('status', 'GIALLO')
        sc = '#22c55e' if st=='VERDE' else '#f59e0b' if st=='GIALLO' else '#ef4444'
        crusc_indicators_html += f'''
        <div class="crusc-row">
          <div class="crusc-dot" style="background:{sc}"></div>
          <div class="crusc-name">{i['name']}<span class="crusc-tk">{i.get('ticker','')}</span></div>
          <div class="crusc-val" style="color:{sc};font-weight:700">{i['value']}</div>
          <div class="crusc-msg">{i['message']}</div>
        </div>'''

    # ── Quadrante macro (NEW — Q1/Q2/Q3/Q4) ─────────────────────
    q_color = quadrant.get('color', '#666')
    q_name = quadrant.get('name', '—')
    q_id = quadrant.get('id', 'Q?')
    q_desc = quadrant.get('description', '')
    q_action = quadrant.get('portfolio_action', '')
    q_winners = quadrant.get('winners', {})
    q_losers = quadrant.get('losers', [])

    winners_html = ''
    for cat, items in q_winners.items():
        if items:
            cat_name = {'equity':'EQUITY','credit':'CREDIT','real_assets':'REAL ASSETS','other':'ALTRO'}.get(cat, cat.upper())
            tags = ' '.join(f'<span class="q-tag green">{x}</span>' for x in items)
            winners_html += f'<div class="q-cat"><span class="q-cat-name">{cat_name}</span>{tags}</div>'
    losers_html = ' '.join(f'<span class="q-tag red">{x}</span>' for x in q_losers)

    # Crescita / inflazione direzione
    g_up = quadrant.get('growth_up')
    i_up = quadrant.get('inflation_up')
    g_arrow = '⬆️' if g_up else '⬇️' if g_up is False else '?'
    i_arrow = '⬆️' if i_up else '⬇️' if i_up is False else '?'

    # ── Macro indicators bar ────────────────────────────────────
    macro_items_html = ''
    for key, (sid, label) in FRED_SERIES.items():
        if key not in macro:
            continue
        d   = macro[key]
        cur = d['current']
        di  = d['direction']
        arrow = '▲' if di=='UP' else '▼'

        if key == 'yield_curve':
            color = '#22c55e' if cur > 0.3 else '#f59e0b' if cur > -0.3 else '#ef4444'
            status = 'POSITIVA' if cur>0.3 else 'PIATTA' if cur>-0.3 else 'INVERTITA'
            val_str = f'{cur:+.2f}%'
        elif key == 'hy_spreads':
            color = '#22c55e' if cur<3.5 else '#f59e0b' if cur<5 else '#ef4444'
            status = 'RISK-ON' if cur<3.5 else 'CAUTO' if cur<5 else 'STRESS'
            val_str = f'{cur:.2f}%'
        elif key == 'vix':
            color = '#22c55e' if cur<18 else '#f59e0b' if cur<28 else '#ef4444'
            status = 'BASSA VOL' if cur<18 else 'NORMALE' if cur<28 else 'ALTA VOL'
            val_str = f'{cur:.1f}'
        elif key in ('cpi','core_pce'):
            yoy = d.get('yoy')
            if yoy is None:
                continue
            color = '#22c55e' if yoy<2.5 else '#f59e0b' if yoy<4 else '#ef4444'
            status = f'YoY {yoy:+.1f}%'
            val_str = f'{yoy:+.1f}%'
            label = label + ' YoY'
        elif key == 'indpro':
            yoy = d.get('yoy')
            if yoy is None:
                continue
            color = '#22c55e' if yoy>1 else '#f59e0b' if yoy>-1 else '#ef4444'
            status = f'YoY {yoy:+.1f}%'
            val_str = f'{yoy:+.1f}%'
            label = 'Industrial Prod YoY'
        elif key == 'unrate':
            color = '#22c55e' if cur<4 else '#f59e0b' if cur<5 else '#ef4444'
            status = f'{cur:.1f}%'
            val_str = f'{cur:.1f}%'
        elif key == 'chicago_fed':
            color = '#22c55e' if cur>0 else '#f59e0b' if cur>-0.5 else '#ef4444'
            status = 'SOPRA TREND' if cur>0 else 'SOTTO TREND' if cur>-0.5 else 'RECESSIONE'
            val_str = f'{cur:+.2f}'
        else:
            color = '#94a3b8'
            status = ''
            val_str = f'{cur:.2f}'

        macro_items_html += f'''
        <div class="macro-item">
          <div class="macro-lbl">{label}</div>
          <div class="macro-val" style="color:{color}">{val_str} <span class="arrow" style="color:{color}">{arrow}</span></div>
          <div class="macro-status">{status}</div>
        </div>'''

    if not macro_items_html:
        macro_items_html = '''<div class="no-fred">
          ⚠️  Configura <code>FRED_API_KEY</code> per abilitare gli indicatori macro.<br>
          Chiave gratuita: <a href="https://fred.stlouisfed.org/docs/api/api_key.html" target="_blank">fred.stlouisfed.org</a>
        </div>'''

    # ── Asset Watch (NEW) ───────────────────────────────────────
    asset_items_html = ''
    asset_priority = ['DXY', 'COPPER_GOLD', 'MOVE', 'OIL', 'GOLD', 'SILVER', 'NATGAS', 'COPPER']
    for key in asset_priority:
        if key not in assets:
            continue
        a = assets[key]
        cur = a['current']
        r1m = a['ret_1m']
        r3m = a['ret_3m']

        # Specifico colore per asset
        color = '#94a3b8'
        if key == 'DXY':
            color = '#22c55e' if cur<100 else '#f59e0b' if cur<105 else '#ef4444'
        elif key == 'COPPER_GOLD':
            color = '#22c55e' if r3m>5 else '#f59e0b' if r3m>-5 else '#ef4444'
        elif key == 'MOVE':
            color = '#22c55e' if cur<100 else '#f59e0b' if cur<130 else '#ef4444'
        else:
            color = '#22c55e' if r1m>=0 else '#ef4444'

        labels = {
            'DXY':'Dollar Index', 'COPPER_GOLD':'Copper/Gold Ratio',
            'MOVE':'MOVE Index (Bond VIX)', 'OIL':'WTI Crude',
            'GOLD':'Gold (futures)', 'SILVER':'Silver (futures)',
            'NATGAS':'Natural Gas', 'COPPER':'Copper (futures)',
        }
        val_fmt = f'{cur:.5f}' if key=='COPPER_GOLD' else f'{cur:.2f}'
        asset_items_html += f'''
        <div class="asset-item">
          <div class="asset-lbl">{labels.get(key, key)}</div>
          <div class="asset-val" style="color:{color}">{val_fmt}</div>
          <div class="asset-rets">
            <span style="color:{'#22c55e' if r1m>=0 else '#ef4444'}">1M: {'+' if r1m>=0 else ''}{r1m}%</span>
            <span style="color:{'#22c55e' if r3m>=0 else '#ef4444'}">3M: {'+' if r3m>=0 else ''}{r3m}%</span>
          </div>
        </div>'''

    # ── NAAIM gauge HTML ─────────────────────────────────────────
    naaim_html = ''
    if naaim:
        nv = naaim['current']
        nc = naaim['change']
        nd = naaim['date']
        naaim_color = '#ef4444' if nv > 90 else '#f59e0b' if nv > 75 else '#22c55e' if nv < 40 else '#22c55e'
        naaim_label = 'ALL-IN ⚠️' if nv > 90 else 'RIALZISTA' if nv > 75 else 'CAPITOLAZIONE 🎯' if nv < 40 else 'NEUTRALE'
        bar_pct = min(100, max(0, nv))  # NAAIM 0-200 ma in pratica 0-100+
        bar_color = naaim_color
        naaim_html = f'''
        <div class="naaim-box">
          <div class="naaim-hdr">
            <span>NAAIM Exposure Index</span>
            <span style="color:#64748b;font-size:11px">aggiornato {nd}</span>
          </div>
          <div class="naaim-gauge">
            <div class="naaim-bar-bg">
              <div class="naaim-bar-fill" style="width:{min(bar_pct,100)}%;background:{bar_color}"></div>
              <div class="naaim-mark" style="left:40%"><span>40</span></div>
              <div class="naaim-mark" style="left:75%"><span>75</span></div>
              <div class="naaim-mark" style="left:90%"><span>90</span></div>
            </div>
          </div>
          <div class="naaim-vals">
            <span class="naaim-num" style="color:{naaim_color}">{nv}</span>
            <span class="naaim-sig" style="color:{naaim_color}">{naaim_label}</span>
            <span class="naaim-wow" style="color:{'#22c55e' if nc>=0 else '#ef4444'}">WoW: {"+" if nc>=0 else ""}{nc}</span>
          </div>
          <div style="font-size:11px;color:#64748b;margin-top:6px">
            Soglie: &lt;40 capitolazione (opportunità) · &gt;90 all-in (rischio top)
          </div>
        </div>'''

    # ── Thematic ETF cards ───────────────────────────────────────
    thematic_cards_html = ''
    thematic_table_rows = ''
    if thematic_metrics and thematic_scores:
        sorted_th = sorted(
            [(t, m, thematic_scores.get(t, {})) for t, m in thematic_metrics.items()],
            key=lambda x: x[2].get('score', 0), reverse=True
        )
        for ticker, m, sc in sorted_th:
            score   = sc.get('score', 0)
            signal  = sc.get('signal', '—')
            color   = sc.get('color', '#666')
            details = sc.get('details', [])

            det_html = ''.join(
                f'<div class="det-row">'
                f'<span class="chk {"ok" if ok else "no"}">{"✓" if ok else "✗"}</span>'
                f'<span class="det-lbl">{lbl}</span>'
                f'<span class="det-val">{val}</span>'
                f'</div>'
                for lbl, sym, val, ok in details
            )

            def th_pct_str(v):
                import math
                if v is None or (isinstance(v, float) and math.isnan(v)): return '—'
                return f"{'+'if v>=0 else ''}{v}%"

            def th_pct_color(v):
                import math
                if v is None or (isinstance(v, float) and math.isnan(v)): return '#64748b'
                return '#22c55e' if v >= 0 else '#ef4444'

            bars = '█' * score + '░' * (6 - score)
            thematic_cards_html += f'''
        <div class="card" style="border-top:4px solid {color}">
          <div class="card-hdr">
            <div>
              <span class="tk">{ticker}</span>
              <div class="tk-name">{m.get('name', ticker)}</div>
            </div>
            <div style="text-align:center">
              <div class="score-dot" style="background:{color}">{score}/6</div>
              <div class="sig" style="color:{color}">{signal}</div>
            </div>
          </div>
          <div class="m-grid">
            <div class="m-cell">
              <div class="m-lbl">RS 4W</div>
              <div class="m-val" style="color:{th_pct_color(m.get('rs4w'))}">{th_pct_str(m.get('rs4w'))}</div>
            </div>
            <div class="m-cell">
              <div class="m-lbl">RS 12W</div>
              <div class="m-val" style="color:{th_pct_color(m.get('rs12w'))}">{th_pct_str(m.get('rs12w'))}</div>
            </div>
            <div class="m-cell">
              <div class="m-lbl">RS 26W</div>
              <div class="m-val" style="color:{th_pct_color(m.get('rs26w'))}">{th_pct_str(m.get('rs26w'))}</div>
            </div>
            <div class="m-cell">
              <div class="m-lbl">Trend</div>
              <div class="m-val" style="font-size:12px;color:{'#22c55e' if m.get('ratio_trend')=='UP' else '#ef4444' if m.get('ratio_trend')=='DOWN' else '#94a3b8'}">{m.get('ratio_trend','—')}</div>
            </div>
          </div>
          <div style="font-family:monospace;font-size:11px;color:#475569;margin:6px 0">[{bars}]</div>
          <div class="det-sect">{det_html}</div>
        </div>'''

            thematic_table_rows += f'''<tr>
              <td style="font-weight:700;color:#f1f5f9">{ticker}</td>
              <td style="color:#94a3b8">{m.get('name', ticker)}</td>
              <td><span class="score-pill" style="background:{color}">{score}/6</span></td>
              <td style="color:{color};font-weight:700">{signal}</td>
              <td style="color:{th_pct_color(m.get('r1w'))}">{th_pct_str(m.get('r1w'))}</td>
              <td style="color:{th_pct_color(m.get('r4w'))}">{th_pct_str(m.get('r4w'))}</td>
              <td style="color:{th_pct_color(m.get('rs4w'))}">{th_pct_str(m.get('rs4w'))}</td>
              <td style="color:{th_pct_color(m.get('rs12w'))}">{th_pct_str(m.get('rs12w'))}</td>
              <td style="color:{th_pct_color(m.get('rs26w'))}">{th_pct_str(m.get('rs26w'))}</td>
              <td style="color:{'#22c55e' if m.get('ratio_trend')=='UP' else '#ef4444' if m.get('ratio_trend')=='DOWN' else '#475569'}">{m.get('ratio_trend','—')}</td>
              <td style="color:#94a3b8">{round(m.get('rsi_ratio', 0), 1)}</td>
            </tr>'''

        # Riga ETF esclusi dal filtro qualità
        if thematic_excluded:
            excl_html = ' '.join(
                f'<span style="background:#1e293b;border:1px solid #334155;color:#64748b;'
                f'padding:3px 9px;border-radius:8px;font-size:11px">'
                f'{t} <span style="color:#475569">{r}</span></span>'
                for t, r in thematic_excluded
            )
        else:
            excl_html = '<span style="color:#475569">Tutti i tematici hanno passato il filtro qualità</span>'
    else:
        excl_html = ''

    # ── Settori favoriti dal quadrante (per banner sopra cards) ──
    favored_html = ' '.join(f'<span class="tag green">{t}</span>'
                            for t in quadrant.get('favored',[]))
    unfav_html   = ' '.join(f'<span class="tag red">{t}</span>'
                            for t in quadrant.get('unfavored',[]))
    steep_html   = ''
    yc_dir = macro.get('yield_curve', {}).get('direction', '')
    yc_val = macro.get('yield_curve', {}).get('current', 0)
    if yc_dir == 'UP' and yc_val < 0.3:
        steep_html = '<span class="tag orange">⚡ YIELD CURVE RE-STEEPENING — segnale di transizione</span>'

    # ── Score cards ───────────────────────────────────────────
    cards_html = ''
    for ticker, m, sc in sorted_s:
        score   = sc.get('score', 0)
        signal  = sc.get('signal','—')
        color   = sc.get('color','#666')
        details = sc.get('details',[])
        cot_n   = sc.get('cot_note','')
        b       = breadth.get(ticker, float('nan'))
        b_str   = f"{b}%" if not (isinstance(b,float) and math.isnan(b)) else '—'

        det_html = ''.join(
            f'<div class="det-row">'
            f'<span class="chk {"ok" if ok else "no"}">{"✓" if ok else "✗"}</span>'
            f'<span class="det-lbl">{lbl}</span>'
            f'<span class="det-val">{val}</span>'
            f'</div>'
            for lbl,sym,val,ok in details
        )

        def pct_color(v):
            if v is None or (isinstance(v,float) and math.isnan(v)): return '#64748b'
            return '#22c55e' if v>=0 else '#ef4444'
        def pct_str(v):
            if v is None or (isinstance(v,float) and math.isnan(v)): return '—'
            return f"{'+'if v>=0 else ''}{v}%"

        cot_tag = f'<div class="cot-tag">📊 {cot_n}</div>' if cot_n else ''
        fav_glow = ' style="box-shadow:0 0 0 2px #22c55e40"' \
                   if ticker in quadrant.get('favored',[]) else ''

        cards_html += f'''
        <div class="card" style="border-top:4px solid {color}"{fav_glow}>
          <div class="card-hdr">
            <div>
              <span class="tk">{ticker}</span>
              <span class="tk-name">{m['name']}</span>
            </div>
            <div class="score-dot" style="background:{color}">{score}/6</div>
          </div>
          <div class="sig" style="color:{color}">{signal}</div>
          <div class="m-grid">
            <div class="m-cell"><div class="m-lbl">RS 4W vs SPY</div>
              <div class="m-val" style="color:{pct_color(m['rs4w'])}">{pct_str(m['rs4w'])}</div></div>
            <div class="m-cell"><div class="m-lbl">Ret 4W</div>
              <div class="m-val" style="color:{pct_color(m['r4w'])}">{pct_str(m['r4w'])}</div></div>
            <div class="m-cell"><div class="m-lbl">Breadth</div>
              <div class="m-val">{b_str}</div></div>
            <div class="m-cell"><div class="m-lbl">RSI Ratio</div>
              <div class="m-val">{m['rsi_ratio']}</div></div>
          </div>
          <div class="det-sect">{det_html}</div>
          {cot_tag}
        </div>'''

    # ── Table rows ────────────────────────────────────────────
    table_rows = ''
    for ticker, m, sc in sorted_s:
        color  = sc.get('color','#666')
        signal = sc.get('signal','—')
        score  = sc.get('score', 0)
        b = breadth.get(ticker, float('nan'))
        b_str = f"{b}%" if not (isinstance(b,float) and math.isnan(b)) else '—'

        def td(v, pct=True):
            if v is None or (isinstance(v,float) and math.isnan(v)): return '<td>—</td>'
            c = '#22c55e' if v>=0 else '#ef4444'
            s = '+' if v>=0 else ''
            return f'<td style="color:{c}">{s}{v}{"%" if pct else ""}</td>'

        ma_str = f"{'✓' if m['above_ma50'] else '✗'} / {'✓' if m['above_ma200'] else '✗'}"
        table_rows += f'''<tr>
          <td><b>{ticker}</b></td>
          <td>{m['name']}</td>
          <td><span class="score-pill" style="background:{color}">{score}/6</span></td>
          <td style="color:{color};font-weight:600">{signal}</td>
          {td(m['r1w'])}{td(m['r4w'])}{td(m['r12w'])}
          {td(m['rs4w'])}{td(m['rs12w'])}{td(m['rs26w'])}
          <td>{b_str}</td>
          <td>{m['rsi_ratio']}</td>
          <td>{m['ratio_trend']}</td>
          <td>{ma_str}</td>
          <td>{m['vol']}%</td>
        </tr>'''

    # ── COT items ─────────────────────────────────────────────
    cot_html = ''
    for name, d in cot.items():
        net    = d.get('mm_net',0)
        change = d.get('change',0)
        nc = '#22c55e' if net>0 else '#ef4444'
        cc = '#22c55e' if change>0 else '#ef4444'
        cot_html += f'''
        <div class="cot-card">
          <div class="cot-name">{name}</div>
          <div class="cot-net" style="color:{nc}">{net:+,}</div>
          <div class="cot-chg" style="color:{cc}">WoW: {change:+,} {d.get("direction","")}</div>
          <div class="cot-sent">{d.get("sentiment","—")}</div>
          <div class="cot-date" style="color:#475569;font-size:11px">{d.get("date","")}</div>
        </div>'''
    if not cot_html:
        cot_html = '<p class="no-fred">⚠️ Dati COT non disponibili (verifica connessione).</p>'

    # ── Chart data ────────────────────────────────────────────
    # RS chart — top 6 settori per score
    top6 = sorted_s[:6]
    rs_series_json = json.dumps([
        dict(name=f"{t} {m['name']}",
             dates=m['dates'],
             values=m['rel_norm'],
             score=sc.get('score',0))
        for t,m,sc in top6 if m.get('dates')
    ])

    # Heatmap data
    hm_json = json.dumps(dict(
        sectors=[m['name'] for _,m,_ in sorted_s],
        r1w=[_nan_safe(m['r1w']) for _,m,_ in sorted_s],
        r4w=[_nan_safe(m['r4w']) for _,m,_ in sorted_s],
        r12w=[_nan_safe(m['r12w']) for _,m,_ in sorted_s],
        rs4w=[_nan_safe(m['rs4w']) for _,m,_ in sorted_s],
        rs12w=[_nan_safe(m['rs12w']) for _,m,_ in sorted_s],
    ))

    macro_json = json.dumps({
        k: dict(dates=v['dates'][-52:], values=v['values'][-52:], label=v['label'])
        for k,v in macro.items()
    })

    # ═══════════════════════════════════════════════════════════
    #  HTML TEMPLATE
    # ═══════════════════════════════════════════════════════════
    return f'''<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Country Trader</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}}

/* HEADER */
.hdr{{background:linear-gradient(135deg,#1e293b,#0f172a);border-bottom:1px solid #334155;padding:14px 32px;display:flex;justify-content:space-between;align-items:center}}
.hdr-left{{display:flex;align-items:center;gap:14px}}
.hdr-logo{{height:64px;width:auto}}
.hdr h1{{font-size:22px;font-weight:900;letter-spacing:-0.5px;color:#f1f5f9}}
.hdr h1 span{{color:#3b82f6}}
.hdr .upd{{color:#475569;font-size:13px}}

/* CONTAINER */
.wrap{{max-width:1700px;margin:0 auto;padding:24px 28px}}

/* REGIME */
.regime{{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:20px 24px;margin-bottom:20px}}
.regime-q{{font-size:20px;font-weight:700;margin-bottom:6px}}
.regime-d{{color:#94a3b8;font-size:14px;margin-bottom:10px}}
.tag{{display:inline-block;padding:3px 11px;border-radius:20px;font-size:12px;font-weight:600;margin:2px}}
.tag.green{{background:#14532d;color:#86efac}}
.tag.red{{background:#450a0a;color:#fca5a5}}
.tag.orange{{background:#431407;color:#fed7aa}}

/* CRUSCOTTO BANNER */
.crusc-banner{{background:#1e293b;border-radius:14px;padding:24px;margin-bottom:20px;display:flex;gap:24px;align-items:center}}
.crusc-light{{width:120px;height:120px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all .3s}}
.crusc-overall{{font-size:24px;font-weight:900;color:#000;letter-spacing:1px}}
.crusc-body{{flex:1}}
.crusc-scenario{{font-size:18px;font-weight:800;margin-bottom:8px;letter-spacing:.5px}}
.crusc-action{{color:#cbd5e1;font-size:14px;line-height:1.7;margin-bottom:10px}}
.crusc-counts{{display:flex;gap:16px;font-size:13px;font-weight:600;align-items:center}}

/* CRUSCOTTO TABLE (in tab) */
.cruscotto-detail{{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:20px}}
.crusc-table{{display:flex;flex-direction:column;gap:10px}}
.crusc-row{{display:grid;grid-template-columns:14px 1.6fr 1fr 2fr;gap:14px;padding:12px;background:#0f172a;border-radius:8px;align-items:center}}
.crusc-dot{{width:14px;height:14px;border-radius:50%;flex-shrink:0}}
.crusc-name{{color:#e2e8f0;font-weight:600;font-size:13px;display:flex;flex-direction:column}}
.crusc-tk{{color:#475569;font-size:10px;font-family:monospace;margin-top:2px}}
.crusc-val{{font-size:18px;font-family:monospace;text-align:right}}
.crusc-msg{{color:#94a3b8;font-size:12px;line-height:1.5}}

/* QUADRANT BANNER */
.quadrant-banner{{background:#1e293b;border-radius:12px;padding:22px 26px;margin-bottom:20px}}
.q-header{{display:flex;align-items:center;gap:18px;margin-bottom:12px}}
.q-id{{width:56px;height:56px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900;color:#000;flex-shrink:0}}
.q-name{{font-size:20px;font-weight:800;letter-spacing:.5px}}
.q-axes{{color:#94a3b8;font-size:13px;margin-top:2px}}
.q-desc{{color:#cbd5e1;font-size:14px;line-height:1.7;margin-bottom:14px}}
.q-action{{background:#0f2744;border-left:3px solid #3b82f6;padding:10px 14px;color:#bfdbfe;font-size:13px;line-height:1.6;margin-bottom:16px;border-radius:6px}}
.q-winners-section{{margin-bottom:14px}}
.q-section-name{{color:#475569;font-size:11px;text-transform:uppercase;letter-spacing:.5px;font-weight:700;margin-bottom:6px}}
.q-cat{{margin-bottom:6px}}
.q-cat-name{{display:inline-block;color:#64748b;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-right:8px;width:90px}}
.q-tag{{display:inline-block;padding:3px 10px;border-radius:14px;font-size:12px;font-weight:600;margin:2px}}
.q-tag.green{{background:#14532d;color:#86efac}}
.q-tag.red{{background:#450a0a;color:#fca5a5}}
.q-sectors{{padding-top:14px;border-top:1px solid #334155;font-size:13px;line-height:2}}

/* ASSET WATCH */
.section-header{{color:#475569;font-size:12px;text-transform:uppercase;letter-spacing:.8px;font-weight:700;margin:24px 0 10px}}
.asset-bar{{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px;margin-bottom:20px}}
.asset-item{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:12px 14px}}
.asset-lbl{{color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}}
.asset-val{{font-size:20px;font-weight:800;font-family:monospace}}
.asset-rets{{display:flex;gap:10px;font-size:11px;font-weight:600;margin-top:4px}}

/* MACRO BAR */
.macro-bar{{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px;margin-bottom:20px}}
.macro-item{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px 18px}}
.macro-lbl{{color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}}
.macro-val{{font-size:26px;font-weight:800}}
.macro-status{{color:#64748b;font-size:12px;margin-top:2px}}
.arrow{{font-size:14px}}
.no-fred{{color:#64748b;grid-column:1/-1;padding:16px;font-size:14px;line-height:1.7}}
.no-fred a{{color:#3b82f6}}

/* TABS */
.tabs{{display:flex;gap:2px;margin-bottom:20px;background:#1e293b;border-radius:8px;padding:4px;width:fit-content}}
.tab{{padding:8px 22px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:500;color:#64748b;user-select:none;transition:all .15s}}
.tab:hover{{color:#e2e8f0}}
.tab.active{{background:#3b82f6;color:#fff;font-weight:700}}
.tab-content{{display:none}}
.tab-content.active{{display:block}}

/* CARDS */
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:14px}}
.card{{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:16px;transition:transform .15s}}
.card:hover{{transform:translateY(-2px)}}
.card-hdr{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px}}
.tk{{font-size:21px;font-weight:800;margin-right:6px}}
.tk-name{{color:#64748b;font-size:12px}}
.score-dot{{width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;color:#fff;flex-shrink:0}}
.sig{{font-size:10px;font-weight:800;letter-spacing:1.2px;text-transform:uppercase;margin-bottom:10px}}
.m-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px}}
.m-cell{{text-align:center}}
.m-lbl{{color:#475569;font-size:9px;text-transform:uppercase;letter-spacing:.3px}}
.m-val{{font-size:15px;font-weight:700}}
.det-sect{{border-top:1px solid #334155;padding-top:8px}}
.det-row{{display:flex;align-items:center;gap:6px;padding:2px 0;font-size:12px}}
.chk.ok{{color:#22c55e;font-size:13px;width:14px}}
.chk.no{{color:#ef4444;font-size:13px;width:14px}}
.det-lbl{{color:#94a3b8;flex:1}}
.det-val{{color:#64748b;font-size:11px}}
.cot-tag{{margin-top:8px;font-size:11px;color:#60a5fa;background:#172554;padding:5px 10px;border-radius:6px}}

/* TABLE */
.tbl-wrap{{overflow-x:auto;background:#1e293b;border:1px solid #334155;border-radius:12px;padding:4px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:#0f172a;color:#475569;padding:10px 12px;text-align:right;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid #334155;white-space:nowrap}}
th:nth-child(1),th:nth-child(2){{text-align:left}}
td{{padding:9px 12px;text-align:right;border-bottom:1px solid #1a2744;white-space:nowrap}}
td:nth-child(1),td:nth-child(2){{text-align:left}}
tr:hover td{{background:#253047}}
.score-pill{{padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;color:#fff}}

/* COT */
.cot-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px}}
.cot-card{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:16px}}
.cot-name{{color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}}
.cot-net{{font-size:24px;font-weight:800;margin-bottom:2px}}
.cot-chg{{font-size:14px;font-weight:600;margin-bottom:2px}}
.cot-sent{{color:#94a3b8;font-size:12px}}

/* CHARTS */
.chart-box{{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:16px;margin-bottom:16px}}
.chart-ttl{{color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:12px;font-weight:600}}

/* RESPONSIVE */
@media(max-width:768px){{
  .wrap{{padding:12px}}
  .grid{{grid-template-columns:1fr}}
  .m-grid{{grid-template-columns:repeat(2,1fr)}}
  .tabs{{overflow-x:auto;width:100%}}
}}
.naaim-box{{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:16px 20px;margin-bottom:20px}}
.naaim-hdr{{display:flex;justify-content:space-between;align-items:center;font-size:12px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px}}
.naaim-gauge{{margin:8px 0 10px}}
.naaim-bar-bg{{position:relative;height:10px;background:#0f172a;border-radius:5px;overflow:visible}}
.naaim-bar-fill{{height:100%;border-radius:5px;transition:width .3s}}
.naaim-mark{{position:absolute;top:12px;font-size:9px;color:#475569;transform:translateX(-50%)}}
.naaim-vals{{display:flex;align-items:center;gap:16px;margin-top:14px}}
.naaim-num{{font-size:28px;font-weight:900}}
.naaim-sig{{font-size:13px;font-weight:700}}
.naaim-wow{{font-size:12px;margin-left:auto}}
</style>
</head>
<body>

<div class="hdr">
  <div class="hdr-left">
    <img class="hdr-logo" src="data:image/png;base64,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" alt="Country Trader Logo">
    <h1>Country <span>Trader</span></h1>
  </div>
  <div class="upd">Aggiornato: {updated}</div>
</div>

<div class="wrap">

<!-- ═══════════════════════════════════════════════════════════
     CRUSCOTTO DI CONTROLLO — TRAFFIC LIGHT (NEW)
     ══════════════════════════════════════════════════════════ -->
<div class="crusc-banner" style="border:2px solid {crusc_color}">
  <div class="crusc-light" style="background:{crusc_color};box-shadow:0 0 24px {crusc_color}88">
    <div class="crusc-overall">{crusc_overall}</div>
  </div>
  <div class="crusc-body">
    <div class="crusc-scenario" style="color:{crusc_color}">{crusc_scenario}</div>
    <div class="crusc-action">{crusc_action}</div>
    <div class="crusc-counts">
      <span style="color:#22c55e">● {crusc_counts.get('VERDE',0)} verdi</span>
      <span style="color:#f59e0b">● {crusc_counts.get('GIALLO',0)} gialli</span>
      <span style="color:#ef4444">● {crusc_counts.get('ROSSO',0)} rossi</span>
      <span style="color:#475569;margin-left:14px;font-size:12px">su {len(crusc_indicators)} indicatori monitorati</span>
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════
     QUADRANTE MACRO — All-Weather (NEW)
     ══════════════════════════════════════════════════════════ -->
<div class="quadrant-banner" style="border-left:4px solid {q_color}">
  <div class="q-header">
    <div class="q-id" style="background:{q_color}">{q_id}</div>
    <div>
      <div class="q-name" style="color:{q_color}">{q_name}</div>
      <div class="q-axes">Crescita: <strong>{g_arrow}</strong> · Inflazione: <strong>{i_arrow}</strong></div>
    </div>
  </div>
  <div class="q-desc">{q_desc}</div>
  <div class="q-action"><strong>📋 AZIONE PORTAFOGLIO:</strong> {q_action}</div>
  <div class="q-winners-section">
    <div class="q-section-name">✅ ASSET VINCENTI</div>
    {winners_html}
    <div class="q-section-name" style="margin-top:12px">❌ ASSET PERDENTI</div>
    <div class="q-cat">{losers_html}</div>
  </div>
  <div class="q-sectors">
    <strong style="color:#64748b;font-size:12px">SETTORI EQUITY FAVORITI:</strong> {favored_html}
    <br><strong style="color:#64748b;font-size:12px">EVITARE:</strong> {unfav_html}
    {' &nbsp;&nbsp;' + steep_html if steep_html else ''}
  </div>
</div>

<!-- LEGENDA DUE LIVELLI -->
<div style="background:#0f172a;border:1px solid #1e3a5f;border-radius:10px;padding:14px 20px;margin-bottom:16px;display:flex;gap:24px;flex-wrap:wrap;font-size:12px;line-height:1.6">
  <div style="flex:1;min-width:220px">
    <span style="color:#f59e0b;font-weight:700">🚦 CRUSCOTTO = SENTIMENT DI MERCATO (breve termine)</span><br>
    <span style="color:#64748b">Misura 8 indicatori di rischio: VIX, HY spreads, NAAIM, SKEW, yield curve, DXY, MOVE, Copper/Gold.
    Risponde in settimane. Dice quanto è sicuro stare esposti adesso.</span>
  </div>
  <div style="flex:1;min-width:220px">
    <span style="color:{q_color};font-weight:700">🌍 QUADRANTE = CICLO MACRO (medio termine)</span><br>
    <span style="color:#64748b">Misura crescita (IP, LEI, Chicago Fed) e inflazione (CPI, PCE).
    Cambia in mesi. Dice quali asset sono strutturalmente favoriti nei prossimi 3–9 mesi.</span>
  </div>
  <div style="flex:1;min-width:220px;border-left:2px solid #1e3a5f;padding-left:20px">
    <span style="color:#94a3b8;font-weight:700">⚡ POSSONO DIVERGERE — è normale</span><br>
    <span style="color:#64748b">Cruscotto GIALLO + Quadrante STAGFLAZIONE significa:
    il macro è deteriorato ma i mercati non prezzano ancora il rischio pieno.
    Situazione da monitorare, non da ignorare.</span>
  </div>
</div>

<!-- MACRO BAR -->
<div class="macro-bar">{macro_items_html}</div>

<!-- ASSET WATCH (NEW) -->
{'<div class="section-header">🌐 Asset Watch — Indicatori Cross-Asset</div><div class="asset-bar">' + asset_items_html + '</div>' if asset_items_html else ''}

<!-- NAAIM -->
{naaim_html}

<!-- TABS -->
<div class="tabs">
  <div class="tab active" onclick="goTab('cruscotto')">🚦 Cruscotto</div>
  <div class="tab" onclick="goTab('scoring')">🎯 Scoring</div>
  <div class="tab" onclick="goTab('charts')">📈 Charts</div>
  <div class="tab" onclick="goTab('table')">📋 Tabella</div>
  <div class="tab" onclick="goTab('cot')">🏦 COT Multi-Asset</div>
  <div class="tab" onclick="goTab('tematici')">🚀 Tematici</div>
  <div class="tab" onclick="goTab('guide')">📖 Guida</div>
</div>

<!-- CRUSCOTTO TAB (NEW) -->
<div id="t-cruscotto" class="tab-content active">
  <div class="cruscotto-detail">
    <p style="color:#64748b;font-size:13px;margin-bottom:14px;line-height:1.7">
      Dettaglio dei {len(crusc_indicators)} indicatori monitorati. Ogni indicatore ha soglie operative dal framework family office del cruscotto di controllo.
    </p>
    <div class="crusc-table">
      {crusc_indicators_html}
    </div>
  </div>
</div>

<!-- SCORING TAB -->
<div id="t-scoring" class="tab-content">
  <div class="grid">{cards_html}</div>
</div>

<!-- CHARTS TAB -->
<div id="t-charts" class="tab-content">
  <div class="chart-box">
    <div class="chart-ttl">Relative Strength vs SPY — Top 6 Settori per Score (Normalizzato a 100 = 26W fa)</div>
    <div id="rs-chart" style="height:420px"></div>
  </div>
  <div class="chart-box">
    <div class="chart-ttl">Heatmap — Ritorni Assoluti e Relative Strength vs SPY</div>
    <div id="hm-chart" style="height:320px"></div>
  </div>
  <div class="chart-box" id="macro-box">
    <div class="chart-ttl">Indicatori Macro — Yield Curve & HY Spreads (52 settimane)</div>
    <div id="mc-chart" style="height:320px"></div>
  </div>
</div>

<!-- TABLE TAB -->
<div id="t-table" class="tab-content">
  <div class="tbl-wrap">
    <table>
      <thead>
        <tr>
          <th>Ticker</th><th>Settore</th><th>Score</th><th>Segnale</th>
          <th>Ret 1W</th><th>Ret 4W</th><th>Ret 12W</th>
          <th>RS 4W</th><th>RS 12W</th><th>RS 26W</th>
          <th>Breadth</th><th>RSI Ratio</th><th>Trend Ratio</th>
          <th>MA50/200</th><th>Volatilità</th>
        </tr>
      </thead>
      <tbody>{table_rows}</tbody>
    </table>
  </div>
</div>

<!-- COT TAB -->
<div id="t-cot" class="tab-content">
  <p style="color:#64748b;font-size:14px;margin-bottom:16px;line-height:1.7">
    Posizionamento netto dei <strong style="color:#94a3b8">Managed Money</strong> (hedge fund speculativi)
    sui futures commodity — fonte CFTC Disaggregated COT Report, aggiornamento settimanale.<br>
    <span style="color:#f59e0b">Net positivo + in aumento</span> = accumulo bullish → anticipa flussi sui settori correlati.
    <span style="color:#ef4444">Short covering</span> (net negativo ma in risalita) = segnale spesso più forte del long building.
  </p>
  <div class="cot-grid">{cot_html}</div>
</div>

<!-- TEMATICI TAB -->
<div id="t-tematici" class="tab-content">
  <div style="margin-bottom:16px">
    <div style="font-size:13px;color:#64748b;line-height:1.7;margin-bottom:8px">
      Universo ETF tematici monitorati — scoring identico ai settori SPDR (0–6/6).
      Filtro qualità: AUM &gt;$300M e volume medio &gt;$10M/giorno.
      Breadth non disponibile (no componenti mappati).
    </div>
    <div style="font-size:12px;color:#475569">
      ⚠️ Esclusi dal filtro qualità: {excl_html}
    </div>
  </div>
  {'<div class="grid">' + thematic_cards_html + '</div>' if thematic_cards_html else
   '<div style="color:#64748b;padding:40px;text-align:center">Nessun ETF tematico disponibile questa settimana.</div>'}
  {'''<div style="margin-top:24px">
    <div style="color:#475569;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px">Tabella Riepilogativa Tematici</div>
    <div class="tbl-wrap">
      <table>
        <thead>
          <tr>
            <th>Ticker</th><th>Tema</th><th>Score</th><th>Segnale</th>
            <th>Ret 1W</th><th>Ret 4W</th>
            <th>RS 4W</th><th>RS 12W</th><th>RS 26W</th>
            <th>Trend</th><th>RSI Ratio</th>
          </tr>
        </thead>
        <tbody>''' + thematic_table_rows + '''</tbody>
      </table>
    </div>
  </div>''' if thematic_table_rows else ''}
</div>

<!-- GUIDE TAB -->
<div id="t-guide" class="tab-content">
<style>
.g-wrap {{ max-width:900px; }}
.g-wrap h2 {{ font-size:22px; font-weight:800; color:#f1f5f9; margin-bottom:6px; }}
.g-wrap .g-subtitle {{ color:#64748b; font-size:14px; margin-bottom:32px; }}
.g-section {{ margin-bottom:36px; }}
.g-section h3 {{ font-size:16px; font-weight:700; color:#60a5fa; margin-bottom:14px;
                 padding-bottom:8px; border-bottom:1px solid #1e3a5f; display:flex; align-items:center; gap:8px; }}
.g-section p {{ color:#94a3b8; font-size:14px; line-height:1.8; margin-bottom:10px; }}
.g-section strong {{ color:#e2e8f0; }}

/* callout boxes */
.g-box {{ border-radius:10px; padding:16px 20px; margin:14px 0; font-size:14px; line-height:1.7; }}
.g-box.blue  {{ background:#0f2744; border-left:4px solid #3b82f6; color:#93c5fd; }}
.g-box.green {{ background:#052e16; border-left:4px solid #22c55e; color:#86efac; }}
.g-box.amber {{ background:#1c1002; border-left:4px solid #f59e0b; color:#fcd34d; }}
.g-box.red   {{ background:#1c0a0a; border-left:4px solid #ef4444; color:#fca5a5; }}
.g-box.slate {{ background:#1e293b; border-left:4px solid #475569; color:#94a3b8; }}
.g-box strong {{ color:inherit; }}

/* score legend */
.score-legend {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:10px; margin:14px 0; }}
.sl-item {{ border-radius:8px; padding:12px 14px; }}
.sl-score {{ font-size:20px; font-weight:800; margin-bottom:2px; }}
.sl-label {{ font-size:11px; font-weight:700; letter-spacing:1px; text-transform:uppercase; }}
.sl-desc  {{ font-size:12px; margin-top:4px; opacity:.8; }}

/* metric cards */
.metric-cards {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:10px; margin:14px 0; }}
.mc {{ background:#1e293b; border:1px solid #334155; border-radius:8px; padding:14px; }}
.mc-name {{ color:#60a5fa; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; margin-bottom:6px; }}
.mc-desc {{ color:#94a3b8; font-size:13px; line-height:1.6; }}
.mc-formula {{ background:#0f172a; border-radius:4px; padding:4px 8px; font-family:monospace; font-size:12px; color:#a78bfa; margin-top:6px; display:inline-block; }}

/* regime table */
.regime-table {{ width:100%; border-collapse:collapse; font-size:13px; margin:14px 0; }}
.regime-table th {{ background:#0f172a; color:#64748b; padding:8px 12px; text-align:left; font-size:11px;
                    font-weight:700; text-transform:uppercase; letter-spacing:.5px; border-bottom:1px solid #334155; }}
.regime-table td {{ padding:10px 12px; border-bottom:1px solid #1e293b; color:#94a3b8; vertical-align:top; }}
.regime-table tr:hover td {{ background:#1e293b; }}

/* workflow steps */
.workflow {{ display:flex; flex-direction:column; gap:0; margin:14px 0; }}
.wf-step {{ display:flex; gap:16px; }}
.wf-left {{ display:flex; flex-direction:column; align-items:center; }}
.wf-num {{ width:32px; height:32px; border-radius:50%; background:#1d4ed8; color:#bfdbfe;
           font-weight:800; font-size:14px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }}
.wf-line {{ width:2px; background:#1e3a5f; flex:1; margin:4px 0; min-height:16px; }}
.wf-body {{ padding:4px 0 20px; }}
.wf-title {{ color:#e2e8f0; font-weight:700; font-size:14px; margin-bottom:3px; }}
.wf-detail {{ color:#64748b; font-size:13px; line-height:1.6; }}

/* entry decision */
.entry-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:14px 0; }}
.entry-card {{ background:#1e293b; border:1px solid #334155; border-radius:8px; padding:14px; }}
.entry-card h4 {{ color:#f1f5f9; font-size:13px; font-weight:700; margin-bottom:8px; }}
.entry-card ul {{ margin:0 0 0 16px; color:#94a3b8; font-size:13px; line-height:1.8; }}

/* cot guide */
.cot-guide {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:14px 0; }}
.cg {{ background:#1e293b; border:1px solid #334155; border-radius:8px; padding:14px; }}
.cg-title {{ font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; margin-bottom:6px; }}
.cg-desc {{ color:#94a3b8; font-size:13px; line-height:1.6; }}

/* sources */
.sources {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:10px; margin:14px 0; }}
.src {{ background:#1e293b; border:1px solid #334155; border-radius:8px; padding:14px; }}
.src-name {{ color:#f1f5f9; font-weight:700; font-size:13px; margin-bottom:4px; }}
.src-url  {{ color:#3b82f6; font-size:12px; margin-bottom:6px; }}
.src-desc {{ color:#64748b; font-size:12px; line-height:1.5; }}
.src-badge {{ display:inline-block; background:#172554; color:#93c5fd; border-radius:4px;
              padding:1px 7px; font-size:10px; font-weight:700; margin-bottom:6px; }}

@media(max-width:640px){{
  .entry-grid,.cot-guide {{ grid-template-columns:1fr; }}
}}
</style>

<div class="g-wrap">

  <h2>📖 Manuale d'Uso — Sector Rotation Dashboard</h2>
  <p class="g-subtitle">Tutto ciò che serve per leggere ogni sezione, interpretare i segnali e tradurli in decisioni operative.</p>

  <!-- ══════════ 1. LOGICA GENERALE ══════════ -->
  <div class="g-section">
    <h3>🧠 1. Logica del Sistema a Tre Livelli</h3>
    <p>Il dashboard integra tre livelli di analisi sovrapposti. Tutti e tre devono convergere prima di agire. Un segnale tecnico senza macro e senza flussi è rumore.</p>
    <div class="g-box blue">
      <strong>LIVELLO 1 — MACRO REGIME</strong> (banner in cima + tab Macro)<br>
      Identifica in quale fase del ciclo economico ci troviamo. Determina <em>quali settori sono strutturalmente favoriti</em> nei prossimi 3–9 mesi. Cambia lentamente — controllalo ogni mese.<br><br>
      <strong>LIVELLO 2 — FLUSSI ISTITUZIONALI</strong> (Composite Score + COT)<br>
      Conferma che il denaro istituzionale si stia effettivamente muovendo nella direzione indicata dal macro. Senza questo, il segnale macro è anticipatorio ma non ancora azionabile.<br><br>
      <strong>LIVELLO 3 — MOMENTUM E BREADTH</strong> (RS, Breadth, RSI Ratio)<br>
      Verifica che il movimento sia ampio (partecipato dai componenti) e in accelerazione. Evita falsi breakout guidati da 2–3 mega-cap.
    </div>
    <div class="g-box amber">
      <strong>Regola d'oro:</strong> entra solo quando tutti e tre i livelli sono allineati. Non anticipare con il livello 1 da solo. Non inseguire con il livello 3 da solo.
    </div>
  </div>

  <!-- ══════════ 2. REGIME MACRO BANNER ══════════ -->
  <div class="g-section">
    <h3>🌍 2. Banner Regime Macro (in cima al dashboard)</h3>
    <p>Identifica automaticamente il quadrante del ciclo economico basandosi su yield curve 10Y–2Y e HY spreads. Il quadrante determina i settori strutturalmente favoriti e quelli da evitare.</p>
    <table class="regime-table">
      <thead><tr><th>Quadrante</th><th>Yield Curve</th><th>HY Spreads</th><th>Settori Favoriti</th><th>Evitare</th></tr></thead>
      <tbody>
        <tr>
          <td><strong style="color:#22c55e">BOOM / RISK-ON</strong></td>
          <td>> +0.5%</td><td>< 3.5%</td>
          <td>Tech, Discretionary, Financials, Industrials</td>
          <td>Utilities, Staples</td>
        </tr>
        <tr>
          <td><strong style="color:#f59e0b">LATE CYCLE / REFLAZIONE</strong></td>
          <td>da 0 a -0.3%</td><td>3.5–5%</td>
          <td>Energy, Materials, Healthcare, Industrials</td>
          <td>Real Estate, Tech</td>
        </tr>
        <tr>
          <td><strong style="color:#f97316">RECOVERY EARLY / STEEPENING</strong></td>
          <td>< 0 ma in risalita</td><td>in contrazione</td>
          <td>Financials, Industrials, Materials, poi Tech</td>
          <td>Utilities, Staples</td>
        </tr>
        <tr>
          <td><strong style="color:#ef4444">RECESSIONE / RISK-OFF</strong></td>
          <td>< -0.3%</td><td>> 4.5%</td>
          <td>Healthcare, Utilities, Staples, Cash</td>
          <td>Tech, Discretionary, Financials</td>
        </tr>
      </tbody>
    </table>
    <div class="g-box blue">
      <strong>⚡ Alert Steepening:</strong> quando appare il badge arancione "YIELD CURVE RE-STEEPENING", la curva sta passando da invertita a piatta. Questo è storicamente il segnale più precoce (4–8 settimane di anticipo) di transizione dal regime recessivo a quello di recovery. I Financials e i ciclici early-cycle iniziano a ricevere flussi prima che il mercato riconosca la transizione.
    </div>
  </div>

  <!-- ══════════ 3. INDICATORI MACRO ══════════ -->
  <div class="g-section">
    <h3>📡 3. Indicatori Macro (barra sotto il banner)</h3>
    <div class="metric-cards">
      <div class="mc">
        <div class="mc-name">📈 Yield Curve 10Y–2Y</div>
        <div class="mc-desc">Differenza tra i rendimenti dei Treasury USA a 10 anni e 2 anni. Indica le aspettative di crescita del mercato obbligazionario.</div>
        <div class="mc-formula">FRED: T10Y2Y</div>
        <div style="margin-top:8px;font-size:12px;color:#64748b">
          <span style="color:#22c55e">Verde = positiva</span> · 
          <span style="color:#f59e0b">Ambra = piatta</span> · 
          <span style="color:#ef4444">Rosso = invertita</span><br>
          La <strong style="color:#e2e8f0">direzione</strong> conta più del livello: una curva ancora negativa ma in risalita (▲) è il segnale di transizione più importante.
        </div>
      </div>
      <div class="mc">
        <div class="mc-name">💳 HY Spreads OAS</div>
        <div class="mc-desc">Option-Adjusted Spread delle obbligazioni High Yield USA vs Treasury. Misura la percezione del rischio di credito da parte del mercato.</div>
        <div class="mc-formula">FRED: BAMLH0A0HYM2</div>
        <div style="margin-top:8px;font-size:12px;color:#64748b">
          <span style="color:#22c55e">< 3.5% = Risk-On</span> · 
          <span style="color:#f59e0b">3.5–5% = Cautela</span> · 
          <span style="color:#ef4444">> 5% = Stress</span><br>
          Spreads che si <strong style="color:#e2e8f0">allargano rapidamente</strong> segnalano deterioramento del credito → riduci esposizione ciclica prima che il mercato azionario lo capisca.
        </div>
      </div>
      <div class="mc">
        <div class="mc-name">⚡ VIX</div>
        <div class="mc-desc">Indice di volatilità implicita a 30 giorni dell'S&P 500. Proxy della paura del mercato.</div>
        <div class="mc-formula">FRED: VIXCLS</div>
        <div style="margin-top:8px;font-size:12px;color:#64748b">
          <span style="color:#22c55e">< 18 = Bassa vol, complacency</span><br>
          <span style="color:#f59e0b">18–28 = Normale</span><br>
          <span style="color:#ef4444">> 28 = Stress → opportunità contrarian nei difensivi</span>
        </div>
      </div>
      <div class="mc">
        <div class="mc-name">📊 LEI USA (OECD)</div>
        <div class="mc-desc">Leading Economic Indicator — anticipa i turning point del ciclo economico di 6–9 mesi. Il dato più importante per la detection del regime.</div>
        <div class="mc-formula">FRED: USALOLITONOSTSAM</div>
        <div style="margin-top:8px;font-size:12px;color:#64748b">
          Smesso di scendere + stabilizzazione = prossimo regime in arrivo.<br>
          <strong style="color:#e2e8f0">Non guardare il livello assoluto — guarda la derivata.</strong>
        </div>
      </div>
    </div>
  </div>

  <!-- ══════════ 4. COMPOSITE SCORE ══════════ -->
  <div class="g-section">
    <h3>🎯 4. Composite Score 0–5 (tab Scoring)</h3>
    <p>Il cuore del sistema. Ogni settore riceve 1 punto per ciascuno dei 5 criteri soddisfatti. Rappresenta la convergenza tra momentum, flussi e struttura tecnica.</p>

    <div class="score-legend">
      <div class="sl-item" style="background:#052e16;border:1px solid #166534">
        <div class="sl-score" style="color:#22c55e">5–6/6</div>
        <div class="sl-label" style="color:#86efac">FORTE</div>
        <div class="sl-desc" style="color:#4ade80">Setup ottimale. Procedi all'analisi tecnica per il timing di entry.</div>
      </div>
      <div class="sl-item" style="background:#1c1002;border:1px solid #92400e">
        <div class="sl-score" style="color:#f59e0b">3/5</div>
        <div class="sl-label" style="color:#fcd34d">MODERATO</div>
        <div class="sl-desc" style="color:#fbbf24">Segnale presente ma incompleto. Watchlist attiva, aspetta 1–2 conferme.</div>
      </div>
      <div class="sl-item" style="background:#1a0e00;border:1px solid #7c2d12">
        <div class="sl-score" style="color:#f97316">2/5</div>
        <div class="sl-label" style="color:#fdba74">DEBOLE</div>
        <div class="sl-desc" style="color:#fb923c">Segnali prematuri o contraddittori. Non entrare ancora.</div>
      </div>
      <div class="sl-item" style="background:#1c0a0a;border:1px solid #7f1d1d">
        <div class="sl-score" style="color:#ef4444">0–1/6</div>
        <div class="sl-label" style="color:#fca5a5">NEGATIVO</div>
        <div class="sl-desc" style="color:#f87171">Evita o considera underweight. Potenziale short su breakout ribassista.</div>
      </div>
    </div>

    <p style="margin-top:16px">I cinque criteri in dettaglio:</p>
    <div class="metric-cards">
      <div class="mc">
        <div class="mc-name">① RS 4W vs SPY</div>
        <div class="mc-desc">Il settore ha sovraperformato l'S&P 500 nelle ultime 4 settimane (20 giorni di borsa). Il segnale più immediato di rotation in corso.</div>
        <div class="mc-formula">ratio_oggi / ratio_20gg_fa − 1 > 0</div>
        <div style="color:#64748b;font-size:12px;margin-top:6px">Anche +0.1% conta: la direzione importa, non la magnitudine assoluta.</div>
      </div>
      <div class="mc">
        <div class="mc-name">② Trend Ratio UP</div>
        <div class="mc-desc">Il ratio settore/SPY forma higher highs e higher lows negli ultimi 60 giorni. Filtra i falsi segnali di breve termine.</div>
        <div class="mc-formula">media(t3) > media(t2) > media(t1)</div>
        <div style="color:#64748b;font-size:12px;margin-top:6px">I 60gg sono divisi in tre sottoperiodi da 20gg ciascuno.</div>
      </div>
      <div class="mc">
        <div class="mc-name">③ Breadth >40%</div>
        <div class="mc-desc">Almeno il 40% dei 10 titoli principali del settore è sopra la propria MA50. Garantisce che il movimento sia partecipato, non trainato da 1–2 mega-cap.</div>
        <div class="mc-formula">titoli_sopra_MA50 / totale ≥ 40%</div>
        <div style="color:#64748b;font-size:12px;margin-top:6px">< 30% = movimento fragile, evita entry.</div>
      </div>
      <div class="mc">
        <div class="mc-name">④ RS 12W vs SPY</div>
        <div class="mc-desc">Conferma la sovraperformance su 12 settimane (60 giorni). Filtra i ritorni di breve legati a eventi singoli e valida la struttura del trend.</div>
        <div class="mc-formula">ratio_oggi / ratio_60gg_fa − 1 > 0</div>
        <div style="color:#64748b;font-size:12px;margin-top:6px">Se RS 4W è positiva ma RS 12W è negativa, il segnale è debole: possibile rimbalzo nel downtrend.</div>
      </div>
      <div class="mc">
        <div class="mc-name">⑤ RSI del Ratio >50</div>
        <div class="mc-desc">RSI a 14 periodi calcolato sul ratio settore/SPY (non sul prezzo assoluto). Misura il momentum interno della relative strength.</div>
        <div class="mc-formula">RSI(ratio, 14) > 50</div>
        <div style="color:#64748b;font-size:12px;margin-top:6px">> 60 = momentum forte. < 40 = il ratio sta perdendo slancio.</div>
      </div>
    </div>

    <div class="g-box slate">
      <strong>Come usare i cambiamenti di score settimana su settimana:</strong><br>
      Il segnale più azionabile non è il settore a 6/6 (già in trend) — è il settore che passa da <strong>2→3 o da 3→4</strong>. Quella è la rotation che inizia. Tieni traccia del delta settimanale, non del valore assoluto.
    </div>
  </div>

  <!-- ══════════ 5. CHARTS ══════════ -->
  <div class="g-section">
    <h3>📈 5. Grafici (tab Charts)</h3>

    <p><strong>Relative Strength Normalizzata (grafico linee)</strong></p>
    <p>Mostra l'andamento del ratio settore/SPY per i top 6 settori per score, normalizzato a 100 all'inizio del periodo (26 settimane). La linea tratteggiata grigia è SPY = baseline 100.</p>
    <div class="g-box blue">
      Come interpretarlo: una linea <strong>sopra 100 e in salita</strong> = il settore sta battendo l'indice e accelera. Una linea <strong>che sale da sotto 100</strong> dopo un minimo = rotation nascente — segnale più precoce disponibile nel dashboard, spesso 4–6 settimane prima del breakout assoluto.
    </div>

    <p><strong>Heatmap Ritorni e Relative Strength</strong></p>
    <p>Griglia settori × metriche con codice colore verde/rosso. Permette di vedere in un colpo d'occhio dove si concentra la forza relativa e assoluta.</p>
    <div class="g-box slate">
      Un settore con la colonna "RS 12W" rossa ma "RS 4W" verde può essere un rimbalzo tecnico nel downtrend (pericoloso) oppure l'inizio di una rotation (opportunità). Disambigua con il Trend Ratio e la breadth.
    </div>

    <p><strong>Yield Curve & HY Spreads (asse duale)</strong></p>
    <p>52 settimane di dati sovrapposti. La linea tratteggiata orizzontale segna lo zero per la yield curve. Nota: le due serie usano assi Y separati (sinistra e destra).</p>
  </div>

  <!-- ══════════ 6. COT REPORT ══════════ -->
  <div class="g-section">
    <h3>🏦 6. COT Report — Come Leggerlo (tab COT)</h3>
    <p>Il COT (Commitment of Traders) disaggregato della CFTC mostra il posizionamento netto dei <strong>Managed Money</strong> (hedge fund speculativi) sui futures commodity. Si aggiorna ogni venerdì con dati al martedì precedente.</p>
    <div class="cot-guide">
      <div class="cg">
        <div class="cg-title" style="color:#22c55e">✅ Segnali Bullish</div>
        <div class="cg-desc">
          • MM Net <strong style="color:#e2e8f0">positivo e in aumento</strong> → accumulo in corso<br>
          • MM Net <strong style="color:#e2e8f0">negativo ma in risalita rapida</strong> → short covering: segnale spesso più potente del long building perché crea urgenza<br>
          • MM Net positivo + variazione WoW crescente = momentum confermato
        </div>
      </div>
      <div class="cg">
        <div class="cg-title" style="color:#ef4444">❌ Segnali Bearish / Cautela</div>
        <div class="cg-desc">
          • MM Net positivo ma <strong style="color:#e2e8f0">in calo</strong> → distribuzione: gli hedge fund escono<br>
          • MM Net ai <strong style="color:#e2e8f0">massimi storici</strong> → posizionamento estremo = poco combustibile residuo, rischio reversal<br>
          • Commercials (produttori) che aumentano le coperture = aspettano prezzi più bassi
        </div>
      </div>
      <div class="cg">
        <div class="cg-title" style="color:#60a5fa">🔗 Collegamento ai Settori</div>
        <div class="cg-desc">
          • <strong style="color:#e2e8f0">WTI Crude / Natural Gas</strong> → anticipa flussi su XLE (Energy)<br>
          • <strong style="color:#e2e8f0">Copper</strong> → anticipa flussi su XLB (Materials) e XLI (Industrials)<br>
          • <strong style="color:#e2e8f0">Gold</strong> → anticipa flussi su difensivi e XLU (Utilities)
        </div>
      </div>
      <div class="cg">
        <div class="cg-title" style="color:#f59e0b">⚠️ Limiti del COT</div>
        <div class="cg-desc">
          • Lag di 3–4 giorni dalla raccolta alla pubblicazione<br>
          • Non cattura posizioni in equity diretta o ETF<br>
          • Posizionamento estremo può persistere settimane prima del reversal<br>
          • Usalo come <strong style="color:#e2e8f0">conferma</strong>, non come segnale primario
        </div>
      </div>
    </div>
  </div>

  <!-- ══════════ 7. WORKFLOW ══════════ -->
  <div class="g-section">
    <h3>🔄 7. Workflow Settimanale Operativo (30 minuti)</h3>
    <div class="workflow">
      <div class="wf-step">
        <div class="wf-left"><div class="wf-num">1</div><div class="wf-line"></div></div>
        <div class="wf-body">
          <div class="wf-title">Domenica sera — riesegui lo script</div>
          <div class="wf-detail">Apri il terminale: <code style="background:#0f172a;color:#a78bfa;padding:1px 6px;border-radius:3px">python sector_rotation.py</code> — si aggiorna tutto automaticamente in 2–3 minuti.</div>
        </div>
      </div>
      <div class="wf-step">
        <div class="wf-left"><div class="wf-num">2</div><div class="wf-line"></div></div>
        <div class="wf-body">
          <div class="wf-title">Controlla il regime (banner in cima)</div>
          <div class="wf-detail">Il quadrante è cambiato? C'è il badge steepening? Se il regime si è spostato, aggiorna mentalmente la mappa dei settori strutturalmente favoriti. Questo ha priorità su tutto il resto.</div>
        </div>
      </div>
      <div class="wf-step">
        <div class="wf-left"><div class="wf-num">3</div><div class="wf-line"></div></div>
        <div class="wf-body">
          <div class="wf-title">Leggi i delta di score (Scoring tab)</div>
          <div class="wf-detail">Quale settore è salito di score rispetto alla settimana scorsa? Il movimento da 2→3 o da 3→4 è il segnale operativo. Un settore già a 6/6 da 3 settimane è in trend, ma l'entry ottimale è già passata.</div>
        </div>
      </div>
      <div class="wf-step">
        <div class="wf-left"><div class="wf-num">4</div><div class="wf-line"></div></div>
        <div class="wf-body">
          <div class="wf-title">COT tab — conferma istituzionale</div>
          <div class="wf-detail">Per i settori in miglioramento, verifica il COT. MM Net in aumento = il denaro "smart" si posiziona nella stessa direzione. Se contraddice lo score, abbassa la conviction e dimezza il sizing.</div>
        </div>
      </div>
      <div class="wf-step">
        <div class="wf-left"><div class="wf-num">5</div><div class="wf-line"></div></div>
        <div class="wf-body">
          <div class="wf-title">Charts tab — relative strength visiva</div>
          <div class="wf-detail">Apri il grafico RS normalizzato. Una linea che risale da un minimo con pendenza crescente è il pattern ideale. Confronta la breadth: se la linea RS sale ma la breadth è sotto 40%, il movimento è fragile.</div>
        </div>
      </div>
      <div class="wf-step">
        <div class="wf-left"><div class="wf-num">6</div><div class="wf-line"></div></div>
        <div class="wf-body">
          <div class="wf-title">TradingView — setup tecnico (fuori dal dashboard)</div>
          <div class="wf-detail">Per ogni settore a 5–6/6, apri il chart su TradingView. Cerca: (a) breakout da consolidazione con volume, (b) pullback Fibonacci 38–50% su primo strappo, (c) inverse head & shoulders su base settimanale. Definisci entry, stop e target <strong style="color:#e2e8f0">prima</strong> di comprare.</div>
        </div>
      </div>
    </div>
  </div>

  <!-- ══════════ 8. ENTRY DECISION ══════════ -->
  <div class="g-section">
    <h3>⚡ 8. Framework di Decisione Entry</h3>
    <div class="entry-grid">
      <div class="entry-card" style="border-top:3px solid #22c55e">
        <h4 style="color:#22c55e">✅ Entra quando:</h4>
        <ul>
          <li>Score ≥ 5/6 questa settimana</li>
          <li>Regime macro favorisce il settore</li>
          <li>COT non contraddice (MM Net non in calo)</li>
          <li>Setup tecnico pulito (breakout o pullback) su TradingView</li>
          <li>Breadth > 40% e in risalita</li>
        </ul>
      </div>
      <div class="entry-card" style="border-top:3px solid #ef4444">
        <h4 style="color:#ef4444">❌ Non entrare quando:</h4>
        <ul>
          <li>Score ≥ 5/6 ma regime macro avverso</li>
          <li>RS 4W positiva ma RS 12W fortemente negativa</li>
          <li>Breadth < 30% (movimento concentrato su poche large cap)</li>
          <li>COT in forte calo (distribuzione istituzionale)</li>
          <li>Nessun setup tecnico identificabile (mercato in mezzo al niente)</li>
        </ul>
      </div>
      <div class="entry-card" style="border-top:3px solid #3b82f6">
        <h4 style="color:#60a5fa">📐 Sizing operativo:</h4>
        <ul>
          <li><strong style="color:#e2e8f0">Posizione base:</strong> 3–5% del portafoglio finanziario</li>
          <li><strong style="color:#e2e8f0">Add-on 1:</strong> +2% se conferma con volume entro 2W</li>
          <li><strong style="color:#e2e8f0">Add-on 2:</strong> +1% su ulteriore rottura di resistenza</li>
          <li><strong style="color:#e2e8f0">Max esposizione settore:</strong> 8–10%</li>
          <li><strong style="color:#e2e8f0">Stop loss:</strong> 7–8% dall'entry sull'ETF</li>
        </ul>
      </div>
      <div class="entry-card" style="border-top:3px solid #a855f7">
        <h4 style="color:#a855f7">🕰️ Orizzonte temporale:</h4>
        <ul>
          <li>Target: <strong style="color:#e2e8f0">3–9 mesi</strong> per catturare la rotation completa</li>
          <li>Non uscire alla prima correzione del 5–8% — normale in un trend di settore</li>
          <li>Trailing stop: dopo +15% porta lo stop a breakeven + 50% del gain</li>
          <li>Segnale di uscita: score scende sotto 2/6 per 2 settimane consecutive</li>
        </ul>
      </div>
    </div>
    <div class="g-box amber">
      <strong>Bias comportamentale da evitare:</strong> non entrare su un settore già a 6/6 da 6 settimane solo perché il dashboard lo mostra verde. L'opportunità è all'alba del trend (3→4), non a metà. Un settore già esploso ha il rischio/rendimento peggiore.
    </div>
  </div>

  <!-- ══════════ 9. FONTI ══════════ -->
  <div class="g-section">
    <h3>📡 9. Fonti Dati e Risorse Esterne</h3>
    <div class="sources">
      <div class="src">
        <div class="src-badge">GRATUITO — NO AUTH</div>
        <div class="src-name">Yahoo Finance (yfinance)</div>
        <div class="src-desc">Prezzi storici di tutti gli ETF settoriali e dei loro componenti. Base del calcolo RS, breadth e tutti i ritorni.</div>
      </div>
      <div class="src">
        <div class="src-badge">GRATUITO — REGISTRAZIONE</div>
        <div class="src-name">FRED API — St. Louis Fed</div>
        <div class="src-url">fred.stlouisfed.org</div>
        <div class="src-desc">Yield curve, HY spreads, VIX, LEI. Registrazione in 2 minuti, nessun costo. Chiave API via email immediata.</div>
      </div>
      <div class="src">
        <div class="src-badge">GRATUITO — NO AUTH</div>
        <div class="src-name">CFTC COT Report</div>
        <div class="src-url">cftc.gov</div>
        <div class="src-desc">Disaggregated Futures + Options Combined. Scaricato automaticamente dallo script ogni settimana.</div>
      </div>
      <div class="src">
        <div class="src-badge">GRATUITO</div>
        <div class="src-name">TradingView</div>
        <div class="src-url">tradingview.com</div>
        <div class="src-desc">Per il setup tecnico dopo che il dashboard identifica il settore. Costruisci il ratio XLV/SPY, XLE/SPY ecc. su timeframe settimanale.</div>
      </div>
      <div class="src">
        <div class="src-badge">GRATUITO</div>
        <div class="src-name">Unusual Whales</div>
        <div class="src-url">unusualwhales.com</div>
        <div class="src-desc">Block trades istituzionali sulle opzioni degli ETF settoriali. Complemento manuale al COT per leggere il posizionamento options.</div>
      </div>
      <div class="src">
        <div class="src-badge">GRATUITO</div>
        <div class="src-name">The Market Ear</div>
        <div class="src-url">themarketear.com</div>
        <div class="src-desc">Aggregatore di flow commentary dei desk GS/MS/JPM filtrati. Lettura quotidiana (5 min) per il contesto istituzionale.</div>
      </div>
    </div>
  </div>

  <!-- ══════════ 10. ERRORI COMUNI ══════════ -->
  <div class="g-section">
    <h3>⚠️ 10. Errori Comuni da Evitare</h3>
    <div class="g-box red">
      <strong>1. Usare solo lo score ignorando il regime macro.</strong><br>
      Un settore a 6/6 nel regime sbagliato è un segnale falso. Energy a 6/6 in piena recessione con HY spread al 7% è un rimbalzo nel downtrend, non una rotation.
    </div>
    <div class="g-box red">
      <strong>2. Confondere ritorno assoluto con relative strength.</strong><br>
      Un settore +5% in una settimana dove l'S&P sale del 6% sta sottoperformando. La RS è il numero che conta, non il ritorno assoluto.
    </div>
    <div class="g-box red">
      <strong>3. Agire su un solo segnale settimana.</strong><br>
      Un'unica settimana positiva è noise. Il segnale diventa azionabile quando la RS è positiva su 4W E 12W insieme, con breadth partecipante.
    </div>
    <div class="g-box red">
      <strong>4. Inseguire il settore già in trend da mesi.</strong><br>
      Se un settore è a 6/6 da 8 settimane, il grosso del movimento è già prezzato. La rotation del denaro istituzionale avviene nelle prime 4–8 settimane. Dopo, stai comprando da chi sta già vendendo.
    </div>
    <div class="g-box amber">
      <strong>Regola finale:</strong> il dashboard identifica il <em>cosa</em> e il <em>quando in termini di settimane</em>. Il timing preciso dell'entry (al giorno) richiede il setup tecnico su TradingView. Non sostituire uno con l'altro.
    </div>
  </div>

</div>
</div>

</div><!-- /wrap -->

<script>
// ── TABS ─────────────────────────────────────────────────────
const TABS = ['cruscotto','scoring','charts','table','cot','tematici','guide'];
function goTab(name) {{
  TABS.forEach(id => {{
    document.querySelectorAll('.tab')[TABS.indexOf(id)].classList.toggle('active', id===name);
    document.getElementById('t-'+id).classList.toggle('active', id===name);
  }});
  if (name === 'charts') renderCharts();
}}

// ── CHARTS ───────────────────────────────────────────────────
const PALETTE = ['#3b82f6','#22c55e','#f59e0b','#ec4899','#a855f7','#06b6d4'];
const DARK    = {{paper_bgcolor:'#1e293b',plot_bgcolor:'#1e293b',
                  font:{{color:'#94a3b8',size:12}},
                  xaxis:{{gridcolor:'#334155',showgrid:true}},
                  yaxis:{{gridcolor:'#334155',showgrid:true}},
                  legend:{{bgcolor:'#0f172a',bordercolor:'#334155'}},
                  margin:{{t:10,r:16,b:48,l:60}},
                  hovermode:'x unified'}};

const rsSeries = {rs_series_json};
const hmData   = {hm_json};
const macroD   = {macro_json};

let rendered = false;
function renderCharts() {{
  if (rendered) return;
  rendered = true;

  // ── RS Chart ─────────────────────────────────────
  if (rsSeries.length) {{
    const traces = rsSeries.map((s,i) => ({{
      x:s.dates, y:s.values, type:'scatter', mode:'lines',
      name:s.name, line:{{color:PALETTE[i%PALETTE.length],width:2.5}}
    }}));
    traces.push({{
      x:rsSeries[0].dates,
      y:rsSeries[0].dates.map(()=>100),
      name:'SPY baseline 100', type:'scatter', mode:'lines',
      line:{{color:'#475569',width:1,dash:'dash'}}, hoverinfo:'skip'
    }});
    Plotly.newPlot('rs-chart', traces, {{
      ...DARK,
      yaxis:{{...DARK.yaxis, title:'RS Normalizzato (100 = inizio periodo)'}}
    }});
  }}

  // ── Heatmap ─────────────────────────────────────
  const metrics = ['Ret 1W','Ret 4W','Ret 12W','RS 4W vs SPY','RS 12W vs SPY'];
  const zVals   = [hmData.r1w,hmData.r4w,hmData.r12w,hmData.rs4w,hmData.rs12w];
  const zText   = zVals.map(row =>
    row.map(v => v!=null ? (v>=0?'+':'')+v.toFixed(1)+'%' : '—')
  );
  Plotly.newPlot('hm-chart', [{{
    type:'heatmap', z:zVals, x:hmData.sectors, y:metrics,
    text:zText, texttemplate:'%{{text}}',
    colorscale:[[0,'#7f1d1d'],[0.4,'#ef4444'],[0.49,'#1e293b'],
                [0.51,'#1e293b'],[0.6,'#22c55e'],[1,'#14532d']],
    zmid:0, showscale:true,
    colorbar:{{bgcolor:'#1e293b',tickfont:{{color:'#94a3b8'}}}},
  }}], {{
    paper_bgcolor:'#1e293b', plot_bgcolor:'#1e293b',
    font:{{color:'#94a3b8',size:11}},
    margin:{{t:10,r:80,b:80,l:130}},
    xaxis:{{tickfont:{{size:12,color:'#e2e8f0'}}}},
    yaxis:{{tickfont:{{size:11}}}},
  }});

  // ── Macro Chart ─────────────────────────────────
  const yc = macroD.yield_curve;
  const hy = macroD.hy_spreads;
  if (yc && hy) {{
    Plotly.newPlot('mc-chart', [
      {{x:yc.dates,y:yc.values,name:yc.label,type:'scatter',mode:'lines',
        line:{{color:'#3b82f6',width:2}},yaxis:'y'}},
      {{x:hy.dates,y:hy.values,name:hy.label,type:'scatter',mode:'lines',
        line:{{color:'#ef4444',width:2}},yaxis:'y2'}},
    ], {{
      paper_bgcolor:'#1e293b', plot_bgcolor:'#1e293b',
      font:{{color:'#94a3b8',size:12}},
      xaxis:{{gridcolor:'#334155'}},
      yaxis:{{title:'Yield Curve (%)',gridcolor:'#334155',zeroline:true,zerolinecolor:'#475569'}},
      yaxis2:{{title:'HY Spread (%)',overlaying:'y',side:'right',gridcolor:'transparent'}},
      legend:{{bgcolor:'#0f172a',bordercolor:'#334155'}},
      shapes:[{{type:'line',x0:yc.dates[0],x1:yc.dates[yc.dates.length-1],
                y0:0,y1:0,yref:'y',line:{{color:'#475569',dash:'dot',width:1}}}}],
      margin:{{t:10,r:80,b:48,l:60}},
      hovermode:'x unified',
    }});
  }} else {{
    document.getElementById('macro-box').innerHTML =
      '<p style="color:#64748b;padding:20px;text-align:center">⚠️ Configura FRED_API_KEY per i grafici macro.</p>';
  }}
}}
</script>
</body>
</html>'''


# ═══════════════════════════════════════════════════════════════
#  EMAIL NOTIFICATION
# ═══════════════════════════════════════════════════════════════

def send_email(scores, metrics, macro, quadrant, cruscotto, dashboard_url,
               thematic_scores=None, thematic_metrics=None):
    """Manda una mail di riepilogo con cruscotto + quadrante + link al dashboard."""
    import smtplib, math
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_TO]):
        print("  ↳ Email non configurata — skipping.")
        return

    date_str = datetime.now().strftime('%d %B %Y')
    url_line = f'<p style="margin:20px 0"><a href="{dashboard_url}" style="background:#3b82f6;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px">📊 Apri Dashboard Completo</a></p>' \
               if dashboard_url else ''

    # ── Cruscotto traffic light ──
    crusc_color = cruscotto.get('color','#666')
    crusc_overall = cruscotto.get('overall','—')
    crusc_scenario = cruscotto.get('scenario','')
    crusc_action = cruscotto.get('action','')
    crusc_counts = cruscotto.get('counts',{})

    # ── Quadrante ──
    q_name = quadrant.get('name','—')
    q_color = quadrant.get('color','#666')
    q_action = quadrant.get('portfolio_action','')

    # Build sector ranking rows
    rows_html = ''
    signal_colors = {'FORTE':'#22c55e','MODERATO':'#f59e0b','DEBOLE':'#f97316','NEGATIVO':'#ef4444'}
    sorted_s = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)

    for ticker, sc in sorted_s:
        m       = metrics.get(ticker, {})
        score   = sc['score']
        signal  = sc['signal']
        color   = signal_colors.get(signal, '#666')
        rs4w    = m.get('rs4w', float('nan'))
        rs4w_s  = f"{'+'if rs4w>=0 else ''}{rs4w}%" if not (isinstance(rs4w,float) and math.isnan(rs4w)) else '—'
        rs4w_c  = '#22c55e' if not math.isnan(rs4w) and rs4w>=0 else '#ef4444'
        bars    = '●'*score + '○'*(5-score)
        name    = m.get('name', ticker)

        rows_html += f'''
        <tr style="border-bottom:1px solid #1e293b">
          <td style="padding:10px 14px;font-weight:700;color:#f1f5f9">{ticker}</td>
          <td style="padding:10px 14px;color:#94a3b8">{name}</td>
          <td style="padding:10px 14px;text-align:center">
            <span style="background:{color};color:white;padding:3px 10px;border-radius:12px;font-weight:700;font-size:13px">{score}/6</span>
          </td>
          <td style="padding:10px 14px;color:{color};font-weight:700;font-size:12px;letter-spacing:.5px">{signal}</td>
          <td style="padding:10px 14px;color:{rs4w_c};font-weight:600;text-align:right">{rs4w_s}</td>
        </tr>'''

    # Top picks SPDR
    top_picks = [t for t, sc in sorted_s if sc['score'] >= 5]
    top_html  = ' '.join(f'<span style="background:#1d4ed8;color:#bfdbfe;padding:4px 12px;border-radius:20px;font-weight:700;margin:3px;display:inline-block">{t}</span>' for t in top_picks) \
                if top_picks else '<span style="color:#64748b">Nessun settore a 5/6 questa settimana</span>'

    # Top 3 tematici
    th_top3_html = ''
    if thematic_scores and thematic_metrics:
        sorted_th = sorted(thematic_scores.items(), key=lambda x: x[1]['score'], reverse=True)
        top_th = sorted_th[:3]
        th_rows = ''
        for t, sc in top_th:
            m      = thematic_metrics.get(t, {})
            color  = sc.get('color', '#666')
            rs4w   = m.get('rs4w', float('nan'))
            rs_s   = f"{'+'if rs4w>=0 else ''}{rs4w}%" if not (isinstance(rs4w, float) and math.isnan(rs4w)) else '—'
            rs_c   = '#22c55e' if not (isinstance(rs4w, float) and math.isnan(rs4w)) and rs4w >= 0 else '#ef4444'
            th_rows += f'''
            <tr style="border-bottom:1px solid #1e293b">
              <td style="padding:8px 12px;font-weight:700;color:#f1f5f9">{t}</td>
              <td style="padding:8px 12px;color:#94a3b8;font-size:12px">{m.get('name', t)}</td>
              <td style="padding:8px 12px;text-align:center">
                <span style="background:{color};color:white;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:700">{sc['score']}/6</span>
              </td>
              <td style="padding:8px 12px;color:{rs_c};font-weight:600;text-align:right">{rs_s}</td>
            </tr>'''
        th_top3_html = f'''
  <!-- Top 3 Tematici -->
  <div style="background:#0f172a;border:1px solid #1e3a5f;border-left:3px solid #a855f7;border-radius:12px;padding:18px 24px;margin-bottom:16px">
    <div style="font-size:11px;color:#c084fc;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px;font-weight:700">🚀 Top 3 ETF Tematici questa settimana</div>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="background:#0f172a">
          <th style="padding:6px 12px;text-align:left;color:#475569;font-size:10px;font-weight:700;text-transform:uppercase">Ticker</th>
          <th style="padding:6px 12px;text-align:left;color:#475569;font-size:10px;font-weight:700;text-transform:uppercase">Tema</th>
          <th style="padding:6px 12px;text-align:center;color:#475569;font-size:10px;font-weight:700;text-transform:uppercase">Score</th>
          <th style="padding:6px 12px;text-align:right;color:#475569;font-size:10px;font-weight:700;text-transform:uppercase">RS 4W</th>
        </tr>
      </thead>
      <tbody style="background:#0f172a">{th_rows}</tbody>
    </table>
  </div>'''

    html_body = f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0f172a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="max-width:680px;margin:0 auto;padding:32px 16px">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #334155;border-radius:14px;padding:28px 32px;margin-bottom:20px">
    <div style="font-size:13px;color:#475569;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">Weekly Update · {date_str}</div>
    <div style="font-size:26px;font-weight:800;color:#f1f5f9">📊 Sector Rotation + Cruscotto</div>
    <div style="font-size:14px;color:#64748b;margin-top:6px">Aggiornamento settimanale automatico</div>
  </div>

  <!-- CRUSCOTTO — semaforo principale -->
  <div style="background:#1e293b;border:2px solid {crusc_color};border-radius:14px;padding:20px 24px;margin-bottom:16px;display:flex;gap:18px;align-items:center">
    <div style="width:80px;height:80px;border-radius:50%;background:{crusc_color};display:flex;align-items:center;justify-content:center;flex-shrink:0">
      <div style="font-size:14px;font-weight:900;color:#000;letter-spacing:1px">{crusc_overall}</div>
    </div>
    <div style="flex:1">
      <div style="font-size:15px;font-weight:800;color:{crusc_color};margin-bottom:6px">{crusc_scenario}</div>
      <div style="font-size:13px;color:#cbd5e1;line-height:1.6;margin-bottom:6px">{crusc_action}</div>
      <div style="font-size:11px;color:#64748b">
        <span style="color:#22c55e">●{crusc_counts.get('VERDE',0)}</span>
        <span style="color:#f59e0b;margin-left:8px">●{crusc_counts.get('GIALLO',0)}</span>
        <span style="color:#ef4444;margin-left:8px">●{crusc_counts.get('ROSSO',0)}</span>
      </div>
    </div>
  </div>

  <!-- QUADRANTE -->
  <div style="background:#1e293b;border:1px solid #334155;border-left:4px solid {q_color};border-radius:12px;padding:16px 20px;margin-bottom:16px">
    <div style="font-size:11px;color:#475569;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Quadrante Macro</div>
    <div style="font-size:17px;font-weight:800;color:{q_color};margin-bottom:6px">{q_name}</div>
    <div style="font-size:13px;color:#cbd5e1;line-height:1.6">{q_action}</div>
  </div>

  <!-- Top Picks -->
  <div style="background:#0f2744;border:1px solid #1e3a5f;border-radius:12px;padding:18px 24px;margin-bottom:16px">
    <div style="font-size:11px;color:#60a5fa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px;font-weight:700">⭐ Settori SPDR con Score ≥ 5/6</div>
    <div>{top_html}</div>
  </div>

  {th_top3_html}

  <!-- Ranking Table -->
  <div style="background:#1e293b;border:1px solid #334155;border-radius:12px;overflow:hidden;margin-bottom:16px">
    <div style="padding:14px 18px;border-bottom:1px solid #334155;font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.5px;font-weight:700">Ranking Settori</div>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="background:#0f172a">
          <th style="padding:8px 14px;text-align:left;color:#475569;font-size:10px;font-weight:700;text-transform:uppercase">Ticker</th>
          <th style="padding:8px 14px;text-align:left;color:#475569;font-size:10px;font-weight:700;text-transform:uppercase">Settore</th>
          <th style="padding:8px 14px;text-align:center;color:#475569;font-size:10px;font-weight:700;text-transform:uppercase">Score</th>
          <th style="padding:8px 14px;color:#475569;font-size:10px;font-weight:700;text-transform:uppercase">Segnale</th>
          <th style="padding:8px 14px;text-align:right;color:#475569;font-size:10px;font-weight:700;text-transform:uppercase">RS 4W</th>
        </tr>
      </thead>
      <tbody style="background:#1e293b">{rows_html}</tbody>
    </table>
  </div>

  <!-- CTA -->
  <div style="text-align:center;padding:10px 0 20px">
    {url_line}
    {'<p style="color:#475569;font-size:12px;margin-top:12px">Il link apre il dashboard completo con cruscotto, quadrante, COT multi-asset e grafici.</p>' if dashboard_url else '<p style="color:#475569;font-size:12px">Apri il file sector_rotation_dashboard.html per il dashboard completo.</p>'}
  </div>

  <!-- Footer -->
  <div style="text-align:center;color:#334155;font-size:11px;border-top:1px solid #1e293b;padding-top:16px">
    Generato da sector_rotation.py · Yahoo Finance · FRED · CFTC<br>
    Non costituisce consulenza finanziaria.
  </div>

</div>
</body>
</html>'''

    msg = MIMEMultipart('alternative')
    sema_emoji = '🟢' if crusc_overall=='VERDE' else '🟡' if crusc_overall=='GIALLO' else '🔴'
    top_th_tickers = [t for t, sc in sorted(thematic_scores.items(), key=lambda x: x[1]['score'], reverse=True)[:2]] \
                     if thematic_scores else []
    th_subject = f' | 🚀 {",".join(top_th_tickers)}' if top_th_tickers else ''
    msg['Subject'] = f'{sema_emoji} Sector Rotation {date_str} | {q_name.split()[0]} | Top: {", ".join(top_picks) if top_picks else "—"}{th_subject}'
    msg['From']    = EMAIL_SENDER
    msg['To']      = EMAIL_TO
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_TO, msg.as_string())
        print(f"  ✓ Email inviata a {EMAIL_TO}")
    except Exception as e:
        print(f"  ✗ Email fallita: {e}")


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Sector Rotation Dashboard')
    parser.add_argument('--output', default=OUTPUT_FILE, help='Output HTML path')
    parser.add_argument('--email',  action='store_true',  help='Invia email di riepilogo')
    parser.add_argument('--url',    default='',           help='URL pubblico del dashboard (per la mail)')
    args = parser.parse_args()

    # Permette override URL via argomento CLI
    url = args.url or DASHBOARD_URL

    print(f"\n{'═'*54}")
    print(f"  SECTOR ROTATION DASHBOARD")
    print(f"  {datetime.now().strftime('%d %B %Y — %H:%M')}")
    print(f"{'═'*54}\n")

    print("📊 Raccolta dati in corso...\n")

    prices  = fetch_sector_prices()
    print("  ↳ Computing metrics...")
    metrics   = calc_metrics(prices)
    breadth   = calc_breadth(prices)
    macro     = fetch_macro()
    assets    = fetch_extra_assets()
    naaim     = fetch_naaim()
    cot       = fetch_cot()
    etf_flows = fetch_etf_flows(list(SECTORS.keys()))

    print("  ↳ Scoring settori...")
    scores    = compute_scores(metrics, breadth, cot, etf_flows)
    quadrant  = detect_quadrant(macro)
    cruscotto = compute_cruscotto(macro, assets, cot, naaim)

    # ── ETF Tematici ──────────────────────────────────────────────
    print("  ↳ Filtro qualità ETF tematici...")
    valid_th, excluded_th = filter_quality_etfs(list(THEMATICS.keys()))
    if excluded_th:
        for t, r in excluded_th:
            print(f"    ✗ {t} escluso: {r}")
    valid_th_dict = {t: THEMATICS[t] for t in valid_th}

    thematic_metrics, thematic_scores, thematic_flows = {}, {}, {}
    if valid_th:
        th_prices      = fetch_thematic_prices(valid_th)
        print("  ↳ Computing thematic metrics...")
        thematic_metrics = calc_metrics(th_prices, ticker_dict=valid_th_dict)
        thematic_flows   = fetch_etf_flows(valid_th)
        print("  ↳ Scoring tematici...")
        thematic_scores  = compute_scores(thematic_metrics, {}, {}, thematic_flows)

    # Print summary
    print(f"\n{'─'*54}")
    print(f"  CRUSCOTTO: {cruscotto['overall']} — {cruscotto['scenario']}")
    print(f"{'─'*54}")
    for ind in cruscotto['indicators']:
        st = ind['status']
        sym = '🟢' if st=='VERDE' else '🟡' if st=='GIALLO' else '🔴'
        print(f"  {sym} {ind['name']:32}  {ind['value']:>10}  {ind['message']}")

    print(f"\n  QUADRANTE: {quadrant['name']}")
    print(f"  → {quadrant['portfolio_action']}")

    print(f"\n{'─'*54}")
    print(f"  RANKING COMPOSITE SCORE — SETTORI")
    print(f"{'─'*54}")
    import math
    for t, sc in sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True):
        m     = metrics.get(t,{})
        score = sc['score']
        bars  = '█'*score + '░'*(6-score)
        rs    = m.get('rs4w', float('nan'))
        rs_s  = f"RS4W: {'+'if rs>=0 else ''}{rs}%" if not math.isnan(rs) else "RS4W: —"
        fd    = etf_flows.get(t, {})
        f1w   = fd.get('flow_1w')
        f_s   = f"Flow: {f1w:+.0f}M$" if f1w is not None else "Flow: N/A"
        print(f"  {t:5}  [{bars}] {score}/6  {sc['signal']:10}  {rs_s}  {f_s}")

    if cot:
        print(f"\n  COT — MANAGED MONEY NET (Multi-Asset)")
        for name, d in cot.items():
            print(f"  {name:14}  {d['mm_net']:+,}  {d['sentiment']}  WoW: {d['change']:+,} {d['direction']}")

    if thematic_scores:
        print(f"\n{'─'*54}")
        print(f"  RANKING TEMATICI")
        print(f"{'─'*54}")
        for t, sc in sorted(thematic_scores.items(), key=lambda x: x[1]['score'], reverse=True):
            m     = thematic_metrics.get(t, {})
            score = sc['score']
            bars  = '█' * score + '░' * (6 - score)
            rs    = m.get('rs4w', float('nan'))
            import math
            rs_s  = f"RS4W: {'+'if rs>=0 else ''}{rs}%" if not math.isnan(rs) else "RS4W: —"
            print(f"  {t:5}  [{bars}] {score}/6  {sc['signal']:10}  {rs_s}")

    # Generate & save HTML
    print(f"\n🖥️  Generando dashboard HTML...")
    html = generate_html(metrics, scores, breadth, macro, cot, quadrant, cruscotto, assets, naaim,
                         thematic_metrics=thematic_metrics,
                         thematic_scores=thematic_scores,
                         thematic_excluded=excluded_th)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding='utf-8')
    size = out_path.stat().st_size / 1024
    print(f"  ✓ Salvato: {out_path}  ({size:.0f} KB)")
    if url:
        print(f"  🌐 URL: {url}")

    # Send email
    if args.email or (EMAIL_SENDER and EMAIL_TO):
        print(f"\n📧 Invio email...")
        send_email(scores, metrics, macro, quadrant, cruscotto, url,
                   thematic_scores=thematic_scores, thematic_metrics=thematic_metrics)

    print(f"\n{'═'*54}\n")


if __name__ == '__main__':
    main()
