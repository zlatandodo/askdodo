"""
Genera 3 PDF professionali in italiano che spiegano i 3 scanner di trading.
"""
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

OUTPUT_DIR = Path("/Users/dodomac/Desktop/askdodo/output/docs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── Palette colori ───────────────────────────────────────────────────────────
DARK       = colors.HexColor("#1a1a2e")
ACCENT     = colors.HexColor("#0f3460")
HIGHLIGHT  = colors.HexColor("#16213e")
GREEN      = colors.HexColor("#22c55e")
YELLOW     = colors.HexColor("#eab308")
BLUE       = colors.HexColor("#3b82f6")
PURPLE     = colors.HexColor("#a855f7")
LIGHT_GRAY = colors.HexColor("#f1f5f9")
MID_GRAY   = colors.HexColor("#94a3b8")
WHITE      = colors.white

PAGE_W, PAGE_H = A4


def make_styles():
    base = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CustomTitle",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=26,
        textColor=WHITE,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "CustomSubtitle",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=13,
        textColor=colors.HexColor("#94a3b8"),
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    h1_style = ParagraphStyle(
        "H1",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        textColor=WHITE,
        spaceBefore=18,
        spaceAfter=6,
        backColor=ACCENT,
        leftIndent=-14,
        rightIndent=-14,
        borderPad=8,
    )
    h2_style = ParagraphStyle(
        "H2",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=ACCENT,
        spaceBefore=12,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=colors.HexColor("#1e293b"),
        leading=15,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    )
    bullet_style = ParagraphStyle(
        "Bullet",
        parent=body_style,
        leftIndent=16,
        bulletIndent=6,
        spaceAfter=3,
    )
    mono_style = ParagraphStyle(
        "Mono",
        parent=base["Normal"],
        fontName="Courier",
        fontSize=9,
        textColor=colors.HexColor("#1e293b"),
        backColor=LIGHT_GRAY,
        leading=13,
        leftIndent=12,
        rightIndent=12,
        spaceAfter=8,
        borderPad=6,
    )
    label_style = ParagraphStyle(
        "Label",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=MID_GRAY,
        alignment=TA_CENTER,
    )
    footer_style = ParagraphStyle(
        "Footer",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8,
        textColor=MID_GRAY,
        alignment=TA_CENTER,
    )
    return {
        "title": title_style,
        "subtitle": subtitle_style,
        "h1": h1_style,
        "h2": h2_style,
        "body": body_style,
        "bullet": bullet_style,
        "mono": mono_style,
        "label": label_style,
        "footer": footer_style,
    }


def header_block(title, subtitle, color=ACCENT):
    """Restituisce una Table che funge da header colorato."""
    t_style = ParagraphStyle("HT", fontName="Helvetica-Bold", fontSize=24,
                             textColor=WHITE, alignment=TA_CENTER, leading=30)
    s_style = ParagraphStyle("HS", fontName="Helvetica", fontSize=12,
                             textColor=colors.HexColor("#cbd5e1"),
                             alignment=TA_CENTER, leading=16)
    tbl = Table(
        [[Paragraph(title, t_style)],
         [Paragraph(subtitle, s_style)]],
        colWidths=[PAGE_W - 4*cm],
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), color),
        ("TOPPADDING",    (0,0), (-1,-1), 20),
        ("BOTTOMPADDING", (0,0), (-1,-1), 20),
        ("LEFTPADDING",   (0,0), (-1,-1), 24),
        ("RIGHTPADDING",  (0,0), (-1,-1), 24),
        ("ROUNDEDCORNERS", [8]),
    ]))
    return tbl


def score_table(rows, col_headers, s):
    """Crea una tabella score con intestazione colorata."""
    header_cells = [Paragraph(h, ParagraphStyle("TH", fontName="Helvetica-Bold",
                    fontSize=9, textColor=WHITE, alignment=TA_CENTER)) for h in col_headers]
    body_rows = []
    for row in rows:
        body_rows.append([
            Paragraph(str(c), ParagraphStyle("TD", fontName="Helvetica",
                      fontSize=9, textColor=colors.HexColor("#1e293b"),
                      alignment=TA_CENTER, leading=13))
            for c in row
        ])
    all_rows = [header_cells] + body_rows
    col_count = len(col_headers)
    avail = PAGE_W - 4*cm
    col_w = avail / col_count

    tbl = Table(all_rows, colWidths=[col_w]*col_count, repeatRows=1)
    style = [
        ("BACKGROUND", (0,0), (-1,0), ACCENT),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, LIGHT_GRAY]),
        ("GRID",      (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]
    tbl.setStyle(TableStyle(style))
    return tbl


def filter_table(rows, s):
    """Tabella verticale per filtri."""
    col_headers = ["#", "Filtro", "Valore", "Descrizione"]
    header_cells = [Paragraph(h, ParagraphStyle("TH", fontName="Helvetica-Bold",
                    fontSize=9, textColor=WHITE, alignment=TA_CENTER)) for h in col_headers]
    body_rows = []
    for row in rows:
        body_rows.append([
            Paragraph(str(c), ParagraphStyle("TD", fontName="Helvetica",
                      fontSize=9, textColor=colors.HexColor("#1e293b"),
                      alignment=TA_LEFT, leading=13))
            for c in row
        ])
    all_rows = [header_cells] + body_rows
    tbl = Table(all_rows, colWidths=[1*cm, 5*cm, 3.5*cm, 7.5*cm], repeatRows=1)
    style = [
        ("BACKGROUND", (0,0), (-1,0), ACCENT),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, LIGHT_GRAY]),
        ("GRID",      (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]
    tbl.setStyle(TableStyle(style))
    return tbl


def info_box(label, text, s, bg=LIGHT_GRAY, text_color=None):
    """Box informativo con sfondo."""
    lbl_style = ParagraphStyle("BL", fontName="Helvetica-Bold", fontSize=9,
                               textColor=ACCENT, spaceAfter=2)
    txt_style = ParagraphStyle("BT", fontName="Helvetica", fontSize=9,
                               textColor=text_color or colors.HexColor("#1e293b"),
                               leading=13)
    tbl = Table(
        [[Paragraph(label, lbl_style)],
         [Paragraph(text, txt_style)]],
        colWidths=[PAGE_W - 4*cm],
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), bg),
        ("TOPPADDING",    (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING",   (0,0), (-1,-1), 12),
        ("RIGHTPADDING",  (0,0), (-1,-1), 12),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return tbl


# ═══════════════════════════════════════════════════════════════════════════════
#  PDF 1: Livermore Buy the Dip
# ═══════════════════════════════════════════════════════════════════════════════
def build_livermore_pdf(s):
    path = OUTPUT_DIR / "Livermore_Buy_the_Dip.pdf"
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2.5*cm,
        title="Livermore Buy the Dip Scanner",
        author="AskDodo Trading Systems",
    )
    story = []

    # Header
    story.append(header_block(
        "Livermore Buy the Dip Scanner",
        "Replica standalone dello scanner AskLivermore — Universo S&amp;P 1500",
        color=colors.HexColor("#0f3460")
    ))
    story.append(Spacer(1, 20))

    # Intro
    story.append(Paragraph("1. Cos'è il Livermore Buy the Dip", s["h1"]))
    story.append(Paragraph(
        "Il <b>Livermore Buy the Dip (BTD)</b> è uno scanner che identifica titoli in uptrend strutturale "
        "che stanno attraversando un pullback temporaneo verso il supporto chiave dell'EMA65. "
        "L'obiettivo è comprare la debolezza a breve termine all'interno di un trend rialzista di medio "
        "periodo. La metodologia originale è attribuita a Jesse Livermore e reinterpretata dal portale "
        "<b>AskLivermore</b>.", s["body"]))
    story.append(Paragraph(
        "La logica di fondo è semplice: se un titolo è in uptrend (prezzo sopra le medie allineate) ma "
        "il momentum a breve termine è in ipervenduto (StochRSI ≤ 30), si trova in una finestra di "
        "opportunità — il mercato offre un ingresso vicino al supporto con un rischio contenuto.",
        s["body"]))

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 8))

    # Filtri
    story.append(Paragraph("2. Parametri di Filtro", s["h1"]))
    story.append(Paragraph(
        "I filtri vengono applicati in sequenza. Un titolo deve superarli tutti per comparire nella lista finale.",
        s["body"]))
    story.append(Spacer(1, 6))

    filtri = [
        ["1", "Prezzo > SMA200", "trend long", "Il titolo deve essere in uptrend di lungo periodo sopra la media mobile a 200 periodi."],
        ["2", "EMA65 > EMA88 > EMA100", "stacking strict", "Le tre EMA devono essere perfettamente allineate in ordine decrescente: trend strutturato su timeframe multipli."],
        ["3", "Prezzo ≥ EMA65", "supporto intatto", "Il prezzo non deve essere sceso sotto il supporto principale dell'EMA65."],
        ["4", "Dist. da EMA65 ≤ 8%", "< 8% (tipico < 6%)", "Il prezzo non deve essere troppo esteso sopra il supporto. I match reali S&P1500 sono quasi sempre sotto il 6%."],
        ["5", "StochRSI(14,14,3) ≤ 30", "Wilder RMA", "Il momentum a breve termine deve essere in zona ipervenduto. Usa la formula Wilder identica ad AskLivermore."],
        ["6", "Volume 50gg ≥ 200.000", "liquidità minima", "Filtro di liquidità: evita titoli difficili da tradare con spread elevati."],
    ]
    story.append(filter_table(filtri, s))
    story.append(Spacer(1, 12))

    # Bounce Score
    story.append(Paragraph("3. Il Bounce Score (0–100)", s["h1"]))
    story.append(Paragraph(
        "Per ordinare i risultati in base alla probabilità di rimbalzo, viene calcolato un punteggio "
        "composito che combina quattro dimensioni:", s["body"]))
    story.append(Spacer(1, 6))

    score_data = [
        ["Componente", "Peso Max", "Formula", "Logica"],
        ["StochRSI Score", "40 pt", "(30 - StochRSI) / 30 × 40", "Più è basso lo StochRSI, più il titolo è oversold"],
        ["Distanza EMA65", "30 pt", "(8 - dist%) / 8 × 30", "Più vicino al supporto = migliore risk/reward"],
        ["Trend Strength", "20 pt", "min(gap EMA65/EMA100 / 10%) × 20", "Un trend solido regge meglio il pullback"],
        ["Volume Score", "10 pt", "min(vol_50gg / 5.000.000) × 10", "Più liquidità = meno manipolabilità"],
        ["TOTALE", "100 pt", "Somma delle 4 componenti", "Ordinamento principale dei risultati"],
    ]
    tbl = score_table(score_data[1:], score_data[0], s)
    story.append(tbl)
    story.append(Spacer(1, 10))

    story.append(info_box(
        "Colorazione Excel per Bounce Score",
        "🟢 Verde = score ≥ 70 (setup ottimale, tutte e 4 le componenti alte)  |  "
        "🟡 Giallo = score ≥ 50 (setup interessante)  |  ⚪ Bianco = score &lt; 50 (setup marginale)",
        s, bg=LIGHT_GRAY))
    story.append(Spacer(1, 12))

    # StochRSI Wilder
    story.append(Paragraph("4. Note Tecniche — StochRSI con Wilder RMA", s["h1"]))
    story.append(Paragraph(
        "La differenza critica rispetto all'implementazione standard è l'uso della <b>Wilder RMA</b> "
        "(Relative Moving Average) invece della SMA per il calcolo dell'RSI. Questa formula è identica "
        "a quella usata dal portale AskLivermore, verificata su 6 ticker campione con differenze &lt; 0.5 punti.",
        s["body"]))

    story.append(Paragraph("Formula RSI Wilder:", s["h2"]))
    story.append(Paragraph(
        "alpha = 1/14\n"
        "gain  = variazioni positive smoothate con ewm(alpha=alpha, adjust=False)\n"
        "loss  = variazioni negative smoothate con ewm(alpha=alpha, adjust=False)\n"
        "RS    = gain / loss\n"
        "RSI   = 100 - (100 / (1 + RS))",
        s["mono"]))

    story.append(Paragraph("Formula StochRSI:", s["h2"]))
    story.append(Paragraph(
        "min_rsi  = rolling min di RSI su 14 periodi\n"
        "max_rsi  = rolling max di RSI su 14 periodi\n"
        "StochRSI = (RSI - min_rsi) / (max_rsi - min_rsi) × 100\n"
        "Smooth   = SMA(3) dello StochRSI  →  questo è il valore filtrato ≤ 30",
        s["mono"]))

    story.append(Paragraph(
        "Perché StochRSI invece di RSI classico? In un uptrend strutturale, l'RSI classico scende "
        "raramente sotto 30 — i titoli forti rimbalzano prima. Lo StochRSI è molto più sensibile: "
        "applica la formula stocastica sull'RSI stesso, raggiungendo livelli estremi anche quando "
        "l'RSI è ancora a 45–55. Questo permette di identificare i pullback a breve all'interno "
        "degli uptrend di medio periodo.", s["body"]))
    story.append(Spacer(1, 12))

    # Output e Scheduling
    story.append(Paragraph("5. Output e Scheduling", s["h1"]))

    sched_rows = [
        ["Frequenza", "Ogni sabato alle 06:00 (automatico via macOS launchd)"],
        ["Universo", "S&P 500 + S&P 400 + S&P 600 = ~1.500 titoli"],
        ["Risultati tipici", "70–90 ticker per settimana"],
        ["File HTML", "livermore_dip_YYYY-MM-DD.html — tabella visiva ordinata per Bounce Score con link TradingView"],
        ["File Excel", "livermore_dip_YYYY-MM-DD.xlsx — Bounce Score, Ticker, Nome, Settore, Descrizione, Prezzo, StochRSI, Dist.EMA65%, EMA65/88/100, SMA200, Vol50gg, MktCap, TradingView"],
        ["Email", "Invio automatico a dodo.ebayer@gmail.com con HTML inline e Excel allegato"],
    ]
    tbl2 = Table(sched_rows, colWidths=[4*cm, PAGE_W - 4*cm - 4*cm])
    tbl2.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [LIGHT_GRAY, WHITE]),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("FONTNAME",  (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",  (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE",  (0,0), (-1,-1), 9),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TEXTCOLOR", (0,0), (0,-1), ACCENT),
    ]))
    story.append(tbl2)
    story.append(Spacer(1, 20))

    story.append(Paragraph(
        "AskDodo Trading Systems — Livermore Buy the Dip Scanner v1.0 — 2025",
        s["footer"]))

    doc.build(story)
    print(f"  ✓ {path}")
    return path


# ═══════════════════════════════════════════════════════════════════════════════
#  PDF 2: Momentum Sean Trades
# ═══════════════════════════════════════════════════════════════════════════════
def build_momentum_pdf(s):
    path = OUTPUT_DIR / "Momentum_Sean_Trades.pdf"
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2.5*cm,
        title="Momentum Focus List Scanner",
        author="AskDodo Trading Systems",
    )
    story = []

    story.append(header_block(
        "Momentum Focus List Scanner",
        "Scanner settimanale ispirato alla metodologia di Sean Trades — Universo S&amp;P 1500",
        color=colors.HexColor("#065f46")
    ))
    story.append(Spacer(1, 20))

    # Intro
    story.append(Paragraph("1. Cos'è il Momentum Scanner", s["h1"]))
    story.append(Paragraph(
        "Il <b>Momentum Scanner</b> identifica i titoli con le migliori caratteristiche per un'operatività "
        "swing trading di breve-medio periodo. La logica si basa sul framework di <b>Sean Trades</b>: "
        "trovare titoli che hanno già fatto un forte movimento direzionale (<i>gamba</i>), stanno "
        "consolidando in una base stretta con contrazione di volume (<i>coiling</i>), e sono pronti "
        "a riprendere il trend con un breakout.", s["body"]))
    story.append(Paragraph(
        "Il concetto chiave è che i titoli migliori non si comprano quando sono già esplosi, ma quando "
        "stanno 'caricando la molla' — volume che si secca, range che si stringe, EMA che si avvicinano. "
        "Quando il breakout avviene, la molla si scarica con forza.", s["body"]))

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 8))

    # Filtri
    story.append(Paragraph("2. Filtri di Qualificazione", s["h1"]))
    story.append(Paragraph(
        "I filtri vengono applicati in sequenza. L'ordine è importante: i filtri più rapidi "
        "(liquidità, trend) vengono prima per ridurre il dataset il più velocemente possibile.",
        s["body"]))
    story.append(Spacer(1, 6))

    filtri = [
        ["1", "EMA Alignment", "P > EMA8 > EMA21 > EMA50", "Tutto allineato in uptrend su breve, medio e lungo termine."],
        ["2", "Prezzo > MA200", "uptrend long", "Conferma strutturale di lungo periodo."],
        ["3", "ADR(20) ≥ 2%", "volatilità minima", "Average Daily Range 20gg: il titolo deve muoversi abbastanza per il swing trading."],
        ["4", "Volume 50gg ≥ 500.000", "liquidità", "Liquidità minima per operare senza slippage eccessivo."],
        ["5", "Prior Move ≥ 10%", "gamba di impulso", "Nei 40 giorni precedenti la base, il titolo deve aver fatto almeno +10%."],
        ["6", "Base Range ≤ 12%", "consolidamento", "Range high-low degli ultimi 20 giorni inferiore al 12%: base stretta."],
        ["7", "Volume Contraction < 90%", "coiling", "Il volume nella base (ultimi 10gg) deve essere sotto il 90% del periodo precedente."],
        ["8", "Market Cap ≥ 300M USD", "micro-cap filter", "Elimina le micro-cap difficili da tradare e soggette a manipolazione."],
    ]
    story.append(filter_table(filtri, s))
    story.append(Spacer(1, 12))

    # Quality Score
    story.append(Paragraph("3. Quality Score (0–100)", s["h1"]))
    story.append(Paragraph(
        "Tutti i candidati che superano i filtri vengono ordinati per volume medio (più liquidi in cima). "
        "Il <b>Quality Score</b> è un punteggio composito che misura la qualità del setup:", s["body"]))
    story.append(Spacer(1, 6))

    score_data = [
        ["Componente", "Peso Max", "Formula", "Logica"],
        ["Tightness", "30 pt", "max(0, 1 - base_range%/12) × 30", "Base più stretta = più coiled = breakout più esplosivo"],
        ["Volume Contraction", "20 pt", "max(0, 1 - vol_ratio/0.90) × 20", "Volume più secco = pressione compressa"],
        ["Prior Move", "20 pt", "min(1, (move% - 10)/40) × 20", "+10% = 0pt, +50% = 20pt"],
        ["ADR", "15 pt", "min(1, (ADR% - 2)/4) × 15", "2% = 0pt, 6%+ = 15pt"],
        ["EMA Spacing", "15 pt", "min(dist P/EMA50 / 20%) × 15", "Prezzo non troppo esteso dalle medie"],
        ["TOTALE", "100 pt", "Somma delle 5 componenti", "—"],
    ]
    tbl = score_table(score_data[1:], score_data[0], s)
    story.append(tbl)
    story.append(Spacer(1, 12))

    # Breakout Alert
    story.append(Paragraph("4. Alert Giornaliero di Breakout", s["h1"]))
    story.append(Paragraph(
        "Ogni sera dal lunedì al venerdì alle <b>22:30 ora italiana</b>, il sistema controlla "
        "automaticamente se uno dei titoli in watchlist (tutti i candidati della focus list settimanale) "
        "ha fatto un breakout durante la sessione.", s["body"]))

    story.append(Paragraph("Condizioni di Breakout:", s["h2"]))
    story.append(Paragraph("• Chiusura > massimo delle ultime 20 sedute (base ceiling) + almeno +1%", s["bullet"]))
    story.append(Paragraph("• Volume giornaliero ≥ 1.05× la media del base period", s["bullet"]))
    story.append(Paragraph("• Prezzo ancora sopra EMA21 e EMA50 (no false breakdown)", s["bullet"]))

    story.append(Spacer(1, 8))
    story.append(info_box(
        "Colorazione Volume nell'Email di Breakout",
        "🟢 Verde = volume ≥ 2× media (istituzionale)  |  🟠 Arancione = volume ≥ 1.5× (forte)  |  🔵 Blu = volume ≥ 1.05× (minimo valido)",
        s, bg=LIGHT_GRAY))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "Se non ci sono breakout, l'email NON viene inviata (silenzio totale). "
        "Questo evita rumore nella casella e rende ogni email un segnale significativo.",
        s["body"]))
    story.append(Spacer(1, 12))

    # Output
    story.append(Paragraph("5. Output e Scheduling", s["h1"]))

    sched_rows = [
        ["Frequenza settimanale", "Ogni sabato alle 06:00 (automatico via macOS launchd)"],
        ["Frequenza giornaliera", "Lun–Ven alle 22:30 ora italiana (20:30 UTC)"],
        ["Universo", "S&P 500 + S&P 400 + S&P 600 = ~1.500 titoli"],
        ["Risultati tipici", "Tutti i candidati senza cap (tipicamente 20–80 titoli)"],
        ["Nessun cap settoriale", "Tutti i settori inclusi senza limite massimo per settore"],
        ["File HTML", "momentum_YYYY-MM-DD.html — report visivo con card per ogni ticker"],
        ["File Excel", "momentum_YYYY-MM-DD.xlsx — Ticker, Settore, Score, Prezzo, EMA8/21/50, Prior Move%, Base Range%, Vol Ratio, ADR%, Fatturato, Mkt Cap, TradingView"],
        ["Email settimanale", "HTML inline + Excel allegato"],
        ["Email giornaliera", "Solo se breakout rilevato — include vol ratio colorato"],
    ]
    tbl2 = Table(sched_rows, colWidths=[4.5*cm, PAGE_W - 4*cm - 4.5*cm])
    tbl2.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [LIGHT_GRAY, WHITE]),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("FONTNAME",  (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",  (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE",  (0,0), (-1,-1), 9),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TEXTCOLOR", (0,0), (0,-1), colors.HexColor("#065f46")),
    ]))
    story.append(tbl2)
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "AskDodo Trading Systems — Momentum Focus List Scanner v1.0 — 2025",
        s["footer"]))

    doc.build(story)
    print(f"  ✓ {path}")
    return path


# ═══════════════════════════════════════════════════════════════════════════════
#  PDF 3: Market Structure Scanner
# ═══════════════════════════════════════════════════════════════════════════════
def build_market_structure_pdf(s):
    path = OUTPUT_DIR / "Market_Structure_Scanner.pdf"
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2.5*cm,
        title="Market Structure Scanner",
        author="AskDodo Trading Systems",
    )
    story = []

    story.append(header_block(
        "Market Structure Scanner",
        "Analisi della struttura di mercato su timeframe settimanale — Metodologia Mac (@MacnBTC)",
        color=colors.HexColor("#4c1d95")
    ))
    story.append(Spacer(1, 20))

    # Intro
    story.append(Paragraph("1. Cos'è il Market Structure Scanner", s["h1"]))
    story.append(Paragraph(
        "Il <b>Market Structure Scanner</b> analizza la struttura di mercato di ogni titolo dell'S&P 1500 "
        "su timeframe settimanale. Il principio fondamentale, descritto da <b>Mac (@MacnBTC)</b>, è semplice: "
        "un grafico in uptrend (Higher Highs + Higher Lows) è comprabile; uno in downtrend (Lower Lows + "
        "Lower Highs) non lo è.", s["body"]))
    story.append(Paragraph(
        "L'opportunità migliore si presenta quando la struttura passa da ribassista a rialzista "
        "(<b>Break of Market Structure bullish</b>) o quando il prezzo fa un pullback al Higher Low "
        "in un uptrend confermato. La regola d'oro: <i>non fare l'eroe</i> cercando di comprare il "
        "bottom di un downtrend — aspettare il BMS confermato.", s["body"]))

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 8))

    # Concetti fondamentali
    story.append(Paragraph("2. Concetti Fondamentali", s["h1"]))

    concetti = [
        ["Concetto", "Definizione"],
        ["Swing High", "Massimo locale: il prezzo è più alto dei 3 candles settimanali a sinistra E dei 3 a destra (N=3)"],
        ["Swing Low", "Minimo locale: il prezzo è più basso dei 3 candles settimanali a sinistra E dei 3 a destra"],
        ["Uptrend (HH+HL)", "Ogni swing high è più alto del precedente E ogni swing low è più alto del precedente"],
        ["Downtrend (LH+LL)", "Ogni swing high è più basso del precedente E ogni swing low è più basso del precedente"],
        ["BMS Bullish", "Il prezzo chiude SOPRA l'ultimo Lower High: i compratori prendono il controllo"],
        ["Higher Low (HL)", "Swing low più alto del precedente: il mercato difende livelli crescenti di supporto"],
    ]
    tbl = Table(concetti, colWidths=[4.5*cm, PAGE_W - 4*cm - 4.5*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#4c1d95")),
        ("TEXTCOLOR", (0,0), (-1,0), WHITE),
        ("FONTNAME",  (0,0), (-1,0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, LIGHT_GRAY]),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("FONTNAME",  (0,1), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",  (1,1), (1,-1), "Helvetica"),
        ("FONTSIZE",  (0,0), (-1,-1), 9),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TEXTCOLOR", (0,1), (0,-1), colors.HexColor("#4c1d95")),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 12))

    # Segnali
    story.append(Paragraph("3. Segnali di Ingresso", s["h1"]))
    story.append(Paragraph(
        "Il sistema classifica ogni titolo in uno dei seguenti segnali, dalla priorità più alta alla più bassa:",
        s["body"]))
    story.append(Spacer(1, 6))

    segnali = [
        ["Segnale", "Condizione", "Priorità"],
        ["BMS_FRESH", "BMS bullish avvenuto nelle ultime 4 settimane. Struttura appena cambiata.", "Massima"],
        ["BMS_RECENT", "BMS avvenuto 4–12 settimane fa. Ancora valido se pochi HH stampati.", "Alta"],
        ["BMS_OLD", "BMS avvenuto 12–24 settimane fa.", "Media"],
        ["UPTREND_HL", "Uptrend confermato e prezzo vicino all'ultimo swing low (Higher Low). Entry pulita con stop stretto.", "Alta (entry)"],
        ["Esclusi", "Downtrend senza BMS recente, oppure 4+ HH già stampati dal BMS (crazy late).", "Non mostrati"],
    ]
    tbl2 = Table(segnali, colWidths=[3.5*cm, 10.5*cm, 3*cm])
    tbl2.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#4c1d95")),
        ("TEXTCOLOR", (0,0), (-1,0), WHITE),
        ("FONTNAME",  (0,0), (-1,0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, LIGHT_GRAY]),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("FONTNAME",  (0,1), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",  (1,1), (-1,-1), "Helvetica"),
        ("FONTSIZE",  (0,0), (-1,-1), 9),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TEXTCOLOR", (0,1), (0,-1), colors.HexColor("#4c1d95")),
    ]))
    story.append(tbl2)
    story.append(Spacer(1, 12))

    # MS Score
    story.append(Paragraph("4. MS Score (0–100)", s["h1"]))
    story.append(Paragraph(
        "L'MS Score valuta la qualità del setup in base alla freschezza del BMS e alla distanza "
        "dall'estensione:", s["body"]))
    story.append(Spacer(1, 6))

    ms_data = [
        ["Componente", "Peso Max", "Formula"],
        ["Signal Base", "50 pt", "BMS_FRESH=50 | BMS_RECENT=35 | BMS_OLD=20 | UPTREND=15"],
        ["Recency Bonus", "20 pt", "max(0, 1 - settimane_fa/24) × 20 — più fresco il BMS, meglio"],
        ["Not Extended", "20 pt", "max(0, 1 - HH_dal_BMS/3) × 20 — meno HH già stampati = meno in ritardo"],
        ["HL Proximity", "10 pt", "max(0, 1 - dist_HL%/8) × 10 — più vicino al supporto = entry migliore"],
        ["TOTALE", "100 pt", "Somma delle 4 componenti"],
    ]
    story.append(score_table(ms_data[1:], ms_data[0], s))
    story.append(Spacer(1, 12))

    # Accumulation Score
    story.append(Paragraph("5. Accumulation Score (0–100)", s["h1"]))
    story.append(Paragraph(
        "L'<b>Accumulation Score</b> misura la firma istituzionale: le 'mani forti' tendono ad "
        "accumulare silenziosamente durante la fase discendente e a spingere con volume esplosivo "
        "sulla rottura. È composto da tre componenti:", s["body"]))
    story.append(Spacer(1, 6))

    acc_data = [
        ["Componente", "Peso Max", "Formula", "Interpretazione"],
        ["Volume BMS", "40 pt",
         "BMS_vol / avg_12w_prima × scala",
         "≥3× = 40pt | ≥2× = 30pt | ≥1.5× = 18pt | ≥1.2× = 8pt"],
        ["Base Contraction", "30 pt",
         "Calo volume 8w prima BMS vs 8w ancora precedenti",
         "Contrazione ≥40% → 30pt. Il volume si secca prima dell'esplosione."],
        ["RS vs SPY 12w", "30 pt",
         "(close[-1]/close[-13]) / (spy[-1]/spy[-13])",
         "RS ≥1.20 = 30pt | ≥1.10 = 20pt | ≥1.05 = 10pt. Outperformance relativa."],
        ["TOTALE", "100 pt", "Somma delle 3 componenti", "—"],
    ]
    story.append(score_table(acc_data[1:], acc_data[0], s))
    story.append(Spacer(1, 8))

    story.append(info_box(
        "Ordinamento Finale",
        "I risultati vengono ordinati per (MS Score + Accumulation Score) decrescente. "
        "Un titolo con BMS_FRESH + volume esplosivo + RS forte ottiene il punteggio massimo combinato.",
        s, bg=LIGHT_GRAY))
    story.append(Spacer(1, 12))

    # Output
    story.append(Paragraph("6. Output e Scheduling", s["h1"]))

    sched_rows = [
        ["Frequenza", "Ogni sabato alle 07:00 (un'ora dopo lo scanner Momentum)"],
        ["Universo", "S&P 500 + S&P 400 + S&P 600 = ~1.500 titoli, timeframe settimanale (W-FRI)"],
        ["Swing detection", "N=3: ogni swing point richiede 3 barre di conferma per lato"],
        ["File HTML", "market_structure_YYYY-MM-DD.html — due colonne score affiancate, badge colorati per segnale"],
        ["Colonne HTML", "MS Score | Acc. Score | Ticker | Segnale | Settore | Prezzo | BMS (settimane fa) | HH dal BMS | Dist.HL | Vol BMS | Base Contr. | RS vs SPY | Vol Settim. | Mkt Cap"],
        ["Email", "Oggetto con conteggio BMS freschi e recenti — HTML inline"],
        ["Badge colori", "🟢 BMS_FRESH | 🔵 BMS_RECENT | 🟣 BMS_OLD | 🟡 UPTREND_HL | ⚫ UPTREND"],
    ]
    tbl3 = Table(sched_rows, colWidths=[4.5*cm, PAGE_W - 4*cm - 4.5*cm])
    tbl3.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [LIGHT_GRAY, WHITE]),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("FONTNAME",  (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",  (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE",  (0,0), (-1,-1), 9),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TEXTCOLOR", (0,0), (0,-1), colors.HexColor("#4c1d95")),
    ]))
    story.append(tbl3)
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "AskDodo Trading Systems — Market Structure Scanner v1.0 — 2025",
        s["footer"]))

    doc.build(story)
    print(f"  ✓ {path}")
    return path


if __name__ == "__main__":
    print("Generazione PDF in corso...")
    s = make_styles()
    build_livermore_pdf(s)
    build_momentum_pdf(s)
    build_market_structure_pdf(s)
    print("Done. File salvati in:", OUTPUT_DIR)
