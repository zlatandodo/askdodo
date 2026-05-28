"""
regime.py — Logica di classificazione del regime macro e overlay sentiment.

Tutte le soglie sono centralizzate in RegimeThresholds.
Nessuna dipendenza esterna: solo stdlib.
"""

from dataclasses import dataclass
from typing import Literal

# ═══════════════════════════════════════════════════════════════
#  SOGLIE CENTRALIZZATE
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class RegimeThresholds:
    # Yield Curve 10Y-2Y
    YC_BOOM: float = 0.5        # > 0.5% → ciclo espansivo pieno
    YC_ZERO: float = 0.0        # > 0 → curva positiva
    YC_RESTEEP: float = -0.3    # usato in fallback

    # HY Spreads OAS
    HY_TIGHT: float  = 3.5      # < 3.5% → credito sereno
    HY_NORMAL: float = 4.0      # < 4.0% → ancora ok
    HY_STRESS: float = 5.0      # > 5.0% → stress creditizio

    # NAAIM Exposure Index
    NAAIM_EXTREME: float      = 90.0   # > 90 → gestori all-in, rischio top
    NAAIM_BULLISH: float      = 75.0   # > 75 → posizionamento rialzista
    NAAIM_CAPITULATION: float = 30.0   # < 30 → capitolazione, opportunità

    # CBOE SKEW
    SKEW_ELEVATED: float = 140.0  # > 140 → tail puts già care

    # VIX
    VIX_COMPLACENCY: float = 14.0  # < 14 → euforia/compiacenza
    VIX_NORMAL_HI: float   = 18.0  # < 18 → vol bassa
    VIX_ELEVATED: float    = 25.0  # > 25 → vol elevata

    # Breadth (% componenti sopra MA50)
    BREADTH_OK: float   = 40.0   # >= 40% → breadth sufficiente
    BREADTH_WEAK: float = 30.0   # < 30% → breadth debole

    # RSI Ratio
    RSI_BULL: float = 50.0
    RSI_STRONG: float = 60.0
    RSI_WEAK: float   = 40.0

    # Composite score soglie (su 5 criteri)
    SCORE_FORTE:    int = 4
    SCORE_MODERATO: int = 3
    SCORE_DEBOLE:   int = 2

    # CPI / PCE soglie per quadrante macro
    INFLATION_TARGET: float = 2.5   # sopra target Fed

    # Chicago Fed Activity Index
    CFNAI_EXPANSION:   float =  0.2
    CFNAI_CONTRACTION: float = -0.2


THRESHOLDS = RegimeThresholds()


# ═══════════════════════════════════════════════════════════════
#  TIPI
# ═══════════════════════════════════════════════════════════════

Regime = Literal[
    "BOOM_RISK_ON",
    "LATE_CYCLE_EXPANSION",
    "LATE_CYCLE_STRESS",
    "INVERSION_WAITING",
    "RECESSION_RISK",
]

Overlay = Literal[
    "NEUTRAL",
    "DEFENSIVE_OVERLAY",
    "CAPITULATION_OPPORTUNITY",
]

OperationalState = Literal[
    "STRONG_BUY",
    "BUILDING_WATCH",
    "WAIT_NO_MOMENTUM",
    "TRADE_ONLY",
    "NEUTRAL",
    "AVOID",
]


# ═══════════════════════════════════════════════════════════════
#  CLASSIFICAZIONE REGIME
# ═══════════════════════════════════════════════════════════════

def classify_regime(yc_10y2y: float, hy_oas: float, yc_30d_ago: float) -> tuple[Regime, bool]:
    """Classifica il regime macro da yield curve e HY spreads.

    Args:
        yc_10y2y:   Spread 10Y-2Y corrente in %.
        hy_oas:     HY OAS corrente in %.
        yc_30d_ago: Spread 10Y-2Y di 30 giorni fa (per steepening flag).

    Returns:
        (regime, steepening_flag)
        steepening_flag = True se curva era negativa 30gg fa e ora è positiva.
    """
    t = THRESHOLDS
    if yc_10y2y > t.YC_BOOM and hy_oas < t.HY_TIGHT:
        regime: Regime = "BOOM_RISK_ON"
    elif yc_10y2y > t.YC_ZERO and hy_oas < t.HY_NORMAL:
        regime = "LATE_CYCLE_EXPANSION"
    elif yc_10y2y > t.YC_ZERO and hy_oas >= t.HY_NORMAL:
        regime = "LATE_CYCLE_STRESS"
    elif yc_10y2y <= t.YC_ZERO and hy_oas < t.HY_STRESS:
        regime = "INVERSION_WAITING"
    else:
        regime = "RECESSION_RISK"

    steepening = (yc_30d_ago < 0) and (yc_10y2y > 0)
    return regime, steepening


def classify_overlay(naaim: float, skew: float, vix: float) -> Overlay:
    """Overlay sentiment basato su NAAIM, SKEW, VIX.

    Returns:
        DEFENSIVE_OVERLAY      se almeno 2 indicatori in zona estrema
        CAPITULATION_OPPORTUNITY se NAAIM in capitolazione
        NEUTRAL                altrimenti
    """
    t = THRESHOLDS
    extremes = sum([
        naaim >= t.NAAIM_EXTREME,   # >= 90: all-in
        skew  >= t.SKEW_ELEVATED,   # >= 140: tail care
        vix   < t.VIX_COMPLACENCY,  # < 14: complacency
    ])
    if extremes >= 2:
        return "DEFENSIVE_OVERLAY"
    if naaim < t.NAAIM_CAPITULATION:
        return "CAPITULATION_OPPORTUNITY"
    return "NEUTRAL"


# ═══════════════════════════════════════════════════════════════
#  LABEL E NARRATIVE
# ═══════════════════════════════════════════════════════════════

REGIME_LABELS: dict[Regime, str] = {
    "BOOM_RISK_ON":         "BOOM / RISK-ON",
    "LATE_CYCLE_EXPANSION": "LATE CYCLE EXPANSION",
    "LATE_CYCLE_STRESS":    "LATE CYCLE STRESS",
    "INVERSION_WAITING":    "INVERSION / WAITING",
    "RECESSION_RISK":       "RECESSION RISK",
}

REGIME_COLORS: dict[Regime, str] = {
    "BOOM_RISK_ON":         "#22c55e",
    "LATE_CYCLE_EXPANSION": "#f59e0b",
    "LATE_CYCLE_STRESS":    "#f97316",
    "INVERSION_WAITING":    "#ef4444",
    "RECESSION_RISK":       "#dc2626",
}

# Narrative complete per ogni combinazione (regime, overlay)
# Chiavi mancanti → fallback su (regime, "NEUTRAL")
REGIME_NARRATIVES: dict[tuple[Regime, Overlay], dict] = {
    ("BOOM_RISK_ON", "NEUTRAL"): {
        "title":       "BOOM / RISK-ON",
        "description": "Ciclo strutturalmente favorevole. Yield curve positiva, credito sereno, momentum in espansione.",
        "action":      "Mantenere o aumentare equity ciclica. Duration breve/media. Cash tattico minimo.",
        "hedging":     None,
    },
    ("BOOM_RISK_ON", "DEFENSIVE_OVERLAY"): {
        "title":       "BOOM con OVERLAY DIFENSIVO",
        "description": "Ciclo strutturalmente favorevole MA posizionamento istituzionale estremo (NAAIM/SKEW elevati). Distribuzione potenziale in arrivo.",
        "action":      "Mantenere core equity, NON aggiungere. Ridurre speculativi e small cap. Cash tattico 10–15%.",
        "hedging":     None,  # viene da hedging_advice()
    },
    ("BOOM_RISK_ON", "CAPITULATION_OPPORTUNITY"): {
        "title":       "BOOM / RISK-ON + CAPITOLAZIONE",
        "description": "Ciclo favorevole e gestori in capitolazione: combinazione rara e potente per entry.",
        "action":      "Incrementare esposizione equity. Privilegiare ciclici e growth. Timing favorevole.",
        "hedging":     None,
    },
    ("LATE_CYCLE_EXPANSION", "NEUTRAL"): {
        "title":       "LATE CYCLE EXPANSION",
        "description": "Ciclo maturo ma ancora in espansione. Credito sereno, curva positiva sotto il 50bp di soglia boom.",
        "action":      "Mantenere esposizione equity al target. PAC regolare. Iniziare ad accumulare liquidità tattica (5–10%).",
        "hedging":     None,
    },
    ("LATE_CYCLE_EXPANSION", "DEFENSIVE_OVERLAY"): {
        "title":       "LATE CYCLE + OVERLAY DIFENSIVO ⚠️",
        "description": "Ciclo maturo E posizionamento istituzionale estremo. Mercato vulnerabile a correzioni rapide senza trigger macro.",
        "action":      "Smettere di aggiungere posizioni speculative. Accumulare liquidità (XEON/CSH2). Coperture selettive.",
        "hedging":     None,
    },
    ("LATE_CYCLE_EXPANSION", "CAPITULATION_OPPORTUNITY"): {
        "title":       "LATE CYCLE + CAPITOLAZIONE",
        "description": "Ciclo maturo con gestori in capitolazione: segnale contrarian moderato.",
        "action":      "Considerare entry selettive su settori con score alto. Non caricare in modo aggressivo.",
        "hedging":     None,
    },
    ("LATE_CYCLE_STRESS", "NEUTRAL"): {
        "title":       "LATE CYCLE STRESS",
        "description": "Curva positiva ma HY spread in espansione: il credito inizia a prezzare rischio.",
        "action":      "Ridurre equity ciclica. Aumentare difensivi (XLV, XLU, XLP). Cash al 15–20%.",
        "hedging":     None,
    },
    ("LATE_CYCLE_STRESS", "DEFENSIVE_OVERLAY"): {
        "title":       "LATE CYCLE STRESS + OVERLAY DIFENSIVO 🔴",
        "description": "Credito sotto stress E sentiment estremo. Scenario di deterioramento accelerato.",
        "action":      "Riduzione significativa equity. Aumentare cash e Treasury/Bund. Attivare coperture.",
        "hedging":     None,
    },
    ("INVERSION_WAITING", "NEUTRAL"): {
        "title":       "INVERSION / WAITING",
        "description": "Curva invertita o piatta: segnale storico di recessione nei prossimi 12–18 mesi. Credito ancora sotto controllo.",
        "action":      "Ridurre equity. Aumentare difensivi e liquidità. Costruire posizione in Treasury lunghi gradualmente.",
        "hedging":     None,
    },
    ("INVERSION_WAITING", "DEFENSIVE_OVERLAY"): {
        "title":       "INVERSION + OVERLAY DIFENSIVO 🔴",
        "description": "Curva invertita, credito stressato e sentiment estremo. Alto rischio di repricing.",
        "action":      "BUNKER MODE. Cash elevato. Oro e TIPS. Ridurre equity aggressivamente. Attendere capitolazione.",
        "hedging":     None,
    },
    ("RECESSION_RISK", "NEUTRAL"): {
        "title":       "RECESSION RISK",
        "description": "Curva invertita e spread sotto stress: recessione attesa o in corso.",
        "action":      "Massimizzare cash e Treasury nominali lunghi. Oro come hedge. Equity solo difensiva.",
        "hedging":     None,
    },
    ("RECESSION_RISK", "CAPITULATION_OPPORTUNITY"): {
        "title":       "RECESSION RISK + CAPITOLAZIONE 🎯",
        "description": "Recessione in corso MA gestori in capitolazione: storicamente il miglior punto di entry ciclico.",
        "action":      "Iniziare accumulo graduale equity difensiva (XLV, XLP, XLU). Non affrettarsi — aspettare conferma tecnica.",
        "hedging":     None,
    },
}

def get_narrative(regime: Regime, overlay: Overlay) -> dict:
    """Restituisce la narrative per la coppia (regime, overlay).
    Fallback su (regime, NEUTRAL) se la combinazione non è nel dizionario.
    """
    key = (regime, overlay)
    if key in REGIME_NARRATIVES:
        return REGIME_NARRATIVES[key]
    return REGIME_NARRATIVES.get((regime, "NEUTRAL"), {
        "title":       REGIME_LABELS.get(regime, regime),
        "description": "",
        "action":      "",
        "hedging":     None,
    })


# ═══════════════════════════════════════════════════════════════
#  STATO OPERATIVO PER SETTORE
# ═══════════════════════════════════════════════════════════════

SECTOR_REGIME_MAP: dict[Regime, dict] = {
    "BOOM_RISK_ON":         {"favored": ["XLK", "XLY", "XLF", "XLI"], "avoid": ["XLU", "XLP"]},
    "LATE_CYCLE_EXPANSION": {"favored": ["XLE", "XLB", "XLF", "XLI"], "avoid": ["XLK", "XLRE"]},
    "LATE_CYCLE_STRESS":    {"favored": ["XLE", "XLV", "XLP"],         "avoid": ["XLK", "XLY", "XLF"]},
    "INVERSION_WAITING":    {"favored": ["XLV", "XLU", "XLP"],         "avoid": ["XLF", "XLI", "XLB"]},
    "RECESSION_RISK":       {"favored": ["XLV", "XLU", "XLP"],         "avoid": ["XLK", "XLY", "XLF", "XLI"]},
}

OPERATIONAL_STATE_LABELS: dict[OperationalState, str] = {
    "STRONG_BUY":       "STRONG BUY",
    "BUILDING_WATCH":   "BUILDING / WATCH",
    "WAIT_NO_MOMENTUM": "WAIT — NO MOMENTUM",
    "TRADE_ONLY":       "TRADE (no thesis)",
    "NEUTRAL":          "NEUTRALE",
    "AVOID":            "EVITARE",
}

OPERATIONAL_STATE_COLORS: dict[OperationalState, str] = {
    "STRONG_BUY":       "#22c55e",
    "BUILDING_WATCH":   "#84cc16",
    "WAIT_NO_MOMENTUM": "#f59e0b",
    "TRADE_ONLY":       "#60a5fa",
    "NEUTRAL":          "#64748b",
    "AVOID":            "#ef4444",
}

def operational_state(ticker: str, score: int, regime: Regime) -> OperationalState:
    """Stato operativo per un settore: combina macro regime e momentum tecnico.

    Args:
        ticker: es. 'XLK'
        score:  composite score 0–5
        regime: regime corrente
    """
    t = THRESHOLDS
    mapping = SECTOR_REGIME_MAP.get(regime, {"favored": [], "avoid": []})
    favored     = ticker in mapping["favored"]
    avoid_macro = ticker in mapping["avoid"]

    if favored and score >= t.SCORE_FORTE:
        return "STRONG_BUY"
    if favored and score == t.SCORE_MODERATO:
        return "BUILDING_WATCH"
    if favored and score < t.SCORE_MODERATO:
        return "WAIT_NO_MOMENTUM"
    if not favored and score >= t.SCORE_FORTE:
        return "TRADE_ONLY"
    if avoid_macro and score < t.SCORE_MODERATO:
        return "AVOID"
    return "NEUTRAL"


# ═══════════════════════════════════════════════════════════════
#  HEDGING ADVICE
# ═══════════════════════════════════════════════════════════════

def hedging_advice(vix: float, skew: float) -> str:
    """Consiglio di copertura basato su VIX e SKEW correnti.

    Args:
        vix:  CBOE VIX corrente
        skew: CBOE SKEW corrente
    """
    t = THRESHOLDS
    if vix < t.VIX_NORMAL_HI and skew < t.SKEW_ELEVATED:
        return "VIX basso e tail economiche → comprare PUT OTM 5–10% per protezione tail"
    if vix < t.VIX_NORMAL_HI and skew >= t.SKEW_ELEVATED:
        return "VIX basso ma tail già price-in (SKEW elevato) → preferire PUT SPREAD 5%/15% OTM o COLLAR zero-cost"
    if t.VIX_NORMAL_HI <= vix < t.VIX_ELEVATED:
        return "Vol a costo equo → PUT SPREAD per coperture mirate, non comprare tail nude"
    return "Hedging caro (VIX elevato) → ridurre esposizione diretta invece di pagare premio elevato"


# ═══════════════════════════════════════════════════════════════
#  UTILITY
# ═══════════════════════════════════════════════════════════════

def pluralize_it(n: int, sing: str, plur: str) -> str:
    """Pluralizzazione italiana: pluralize_it(3, 'verde', 'verdi') → '3 verdi'."""
    return f"{n} {sing if n == 1 else plur}"
