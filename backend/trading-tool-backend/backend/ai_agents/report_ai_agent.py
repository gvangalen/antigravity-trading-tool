import logging
import json
import re
from difflib import SequenceMatcher
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple

from backend.utils.db import get_db_connection
from backend.utils.openai_client import ask_gpt_text, ask_gpt_json, ask_gpt_text
from backend.ai_core.system_prompt_builder import build_system_prompt
from backend.engine.transition_detector import compute_transition_detector


# =====================================================
# Logging
# =====================================================
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# =====================================================
# REPORT AGENT ROLE
# =====================================================
REPORT_TASK = """
Je bent een senior Multi-Asset Portfolio Strategist.

Je schrijft GEEN daily snapshot voor één asset, maar een holistisch dagrapport dat de gehele watchlist van de gebruiker analyseert.

PRIMAIRE TAAK:
- Analyseer het algemene marktregime (globaal).
- Beoordeel de specifieke assets in de watchlist (BTC, SOL, ETH, etc.).
- Identificeer convergentie tussen verschillende assets.
- Bepaal welk asset momenteel de sterkste 'setup' of 'edge' heeft.

FOCUS:
- Intermarket relaties.
- Relatieve sterkte tussen assets in de watchlist.
- Signaalconvergentie per asset.
- Positioneel risico over het gehele portfolio.
"""

# =====================================================
# Helpers
# =====================================================
SYSTEM_PROMPT = build_system_prompt(
    agent="report",
    task=REPORT_TASK,
)


def to_float(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except Exception:
        return None


def _flatten_text(obj) -> List[str]:
    out: List[str] = []
    if obj is None:
        return out

    if isinstance(obj, str):
        t = obj.strip()
        if t:
            out.append(t)
        return out

    if isinstance(obj, dict):
        for v in obj.values():
            out.extend(_flatten_text(v))
        return out

    if isinstance(obj, list):
        for v in obj:
            out.extend(_flatten_text(v))
        return out

    return out

def get_regime_memory(user_id: int):

    conn = get_db_connection()

    try:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT regime_label, confidence, signals_json, narrative
                FROM regime_memory
                WHERE user_id = %s
                ORDER BY date DESC
                LIMIT 1;
            """, (user_id,))

            row = cur.fetchone()

            if not row:
                return None

            return {
                "label": row[0],
                "confidence": float(row[1]) if row[1] else None,
                "signals": row[2],
                "narrative": row[3],
            }

    finally:
        conn.close()


def _safe_json(obj):
    """
    JSON-safe serialization (Decimal/date/datetime-safe).
    """
    from datetime import date, datetime

    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _safe_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_json(v) for v in obj]
    return obj


def _score_bucket(score: Optional[float]) -> str:
    value = to_float(score)
    if value is None:
        return "onduidelijk"
    if value >= 75:
        return "sterk"
    if value >= 60:
        return "constructief"
    if value >= 45:
        return "gemengd"
    if value >= 30:
        return "kwetsbaar"
    return "defensief"


def _format_pct(value: Optional[float], digits: int = 1) -> str:
    number = to_float(value)
    if number is None:
        return "onbekend"
    return f"{number:.{digits}f}%"


def _format_price(value: Optional[float]) -> str:
    number = to_float(value)
    if number is None:
        return "onbekend"
    rounded = int(round(number))
    return f"${rounded:,.0f}".replace(",", ".")


def _format_volume(value: Optional[float]) -> str:
    number = to_float(value)
    if number is None:
        return "onbekend"
    rounded = int(round(number))
    return f"{rounded:,.0f}".replace(",", ".")


def _join_symbols(symbols: List[str], max_items: int = 3) -> str:
    cleaned = [str(symbol).upper() for symbol in symbols if symbol]
    if not cleaned:
        return "de watchlist"
    subset = cleaned[:max_items]
    if len(subset) == 1:
        return subset[0]
    if len(subset) == 2:
        return f"{subset[0]} en {subset[1]}"
    return f"{', '.join(subset[:-1])} en {subset[-1]}"


def _watchlist_focus_summary(watchlist_data: Optional[List[Dict[str, Any]]]) -> Tuple[str, Optional[Dict[str, Any]]]:
    if not watchlist_data:
        return "De watchlist geeft vandaag geen duidelijke relatieve voorsprong tussen assets.", None

    ranked = []
    for item in watchlist_data:
        scores = item.get("scores") or {}
        ranked.append(
            {
                "symbol": item.get("symbol"),
                "technical": to_float(scores.get("technical_score")) or 0.0,
                "market": to_float(scores.get("market_score")) or 0.0,
                "setup": to_float(scores.get("setup_score")) or 0.0,
            }
        )

    ranked.sort(key=lambda entry: (entry["setup"], entry["technical"], entry["market"]), reverse=True)
    leader = ranked[0] if ranked else None
    if not leader:
        return "De watchlist geeft vandaag geen duidelijke relatieve voorsprong tussen assets.", None

    summary = (
        f"Binnen de watchlist trekt {leader['symbol']} nu de meeste aandacht, "
        f"met een setupscore van {int(round(leader['setup']))} en een technische score van "
        f"{int(round(leader['technical']))}."
    )
    return summary, leader


def _first_indicator_narrative(items: Optional[List[Dict[str, Any]]], category_label: str) -> str:
    if not items:
        return f"De {category_label}-indicatoren geven vandaag geen extra uitschieter."
    top = items[0]
    name = top.get("indicator") or top.get("name") or f"{category_label}-indicator"
    interpretation = (top.get("interpretation") or "").strip()
    score = to_float(top.get("score"))
    if interpretation:
        return f"Binnen de {category_label}-laag springt {name} eruit: {interpretation}."
    if score is not None:
        return f"Binnen de {category_label}-laag springt {name} eruit met een score van {int(round(score))}."
    return f"Binnen de {category_label}-laag springt {name} eruit als richtinggevend signaal."


def _build_executive_summary_fallback(
    watchlist_data: List[Dict[str, Any]],
    market: Dict[str, Any],
    scores: Dict[str, Any],
    deltas: Dict[str, Any],
    regime: Optional[Dict[str, Any]],
    transition: Optional[Dict[str, Any]],
    best_setup: Optional[Dict[str, Any]],
) -> str:
    symbols = _join_symbols([item.get("symbol") for item in watchlist_data])
    leader_summary, leader = _watchlist_focus_summary(watchlist_data)
    regime_label = (regime or {}).get("label") or "het huidige regime"
    transition_state = None
    if isinstance(transition, dict):
        transition_state = transition.get("state") or transition.get("label") or transition.get("regime_shift")
    market_delta = deltas.get("market_delta")
    delta_phrase = (
        f"Ten opzichte van gisteren verschoof de market score met {market_delta:+.1f} punt."
        if market_delta is not None
        else "Ten opzichte van gisteren bleef het samengestelde marktbeeld grotendeels in dezelfde bandbreedte."
    )
    setup_name = (best_setup or {}).get("name")
    setup_phrase = (
        f"De best bruikbare setup is nu {setup_name}, maar alleen zolang de interne bevestiging in de watchlist overeind blijft."
        if setup_name
        else "Er springt nog geen setup uit die direct om actie vraagt, wat discipline belangrijker maakt dan snelheid."
    )
    transition_phrase = (
        f"De transitie-indicator wijst op {transition_state}, wat aangeeft dat we vooral moeten letten op bevestiging in plaats van op los momentum."
        if transition_state
        else "Er is geen harde regimebreuk zichtbaar, waardoor bevestiging belangrijker blijft dan anticiperen."
    )
    return (
        f"Het dagrapport voor {symbols} opent in {regime_label}, met een marktpostuur dat nu "
        f"{_score_bucket(scores.get('market_score'))} aanvoelt bij een 24-uurs verandering van {_format_pct(market.get('change_24h'))}. "
        f"{delta_phrase} {leader_summary} {transition_phrase} {setup_phrase}"
    )


def _build_market_analysis_fallback(
    watchlist_data: List[Dict[str, Any]],
    market: Dict[str, Any],
    scores: Dict[str, Any],
    deltas: Dict[str, Any],
) -> str:
    symbols = _join_symbols([item.get("symbol") for item in watchlist_data])
    leader_summary, _ = _watchlist_focus_summary(watchlist_data)
    price = _format_price(market.get("price"))
    volume = _format_volume(market.get("volume"))
    market_delta = deltas.get("market_delta")
    delta_phrase = (
        f"De market score verschoof met {market_delta:+.1f} punt, wat laat zien dat de breedte van de beweging veranderde en niet alleen de headlineprijs."
        if market_delta is not None
        else "De market score bleef dicht bij het vorige niveau, wat betekent dat de beweging vooral bevestiging zoekt in plaats van versnelling."
    )
    return (
        f"De markt handelt rond {price} met een 24-uurs mutatie van {_format_pct(market.get('change_24h'))} en volume van {volume}. "
        f"Dat zet {symbols} in een context die {_score_bucket(scores.get('market_score'))} oogt, maar nog niet vanzelf duurzaam is. "
        f"{delta_phrase} {leader_summary} Zolang volume en relatieve sterkte niet breder meelopen, blijft dit eerder een gecontroleerde beweging dan een overtuigende expansie."
    )


def _build_macro_context_fallback(
    scores: Dict[str, Any],
    macro_ind: List[Dict[str, Any]],
    regime: Optional[Dict[str, Any]],
) -> str:
    regime_label = (regime or {}).get("label") or "het huidige regime"
    indicator_phrase = _first_indicator_narrative(macro_ind, "macro")
    return (
        f"Macro blijft vandaag {_score_bucket(scores.get('macro_score'))} en ondersteunt daarmee {regime_label} zonder al een nieuw risicoklimaat af te dwingen. "
        f"{indicator_phrase} Dat betekent dat de speelruimte voor agressie nog steeds afhangt van bevestiging op markt- en technieklaag, niet alleen van een macro-meewind. "
        f"Zolang macro niet duidelijk versnelt of verslechtert, is de juiste lezing dat de markt vooral moet bewijzen dat de recente beweging meer is dan tijdelijke opluchting."
    )


def _build_technical_analysis_fallback(
    watchlist_data: List[Dict[str, Any]],
    scores: Dict[str, Any],
    tech_ind: List[Dict[str, Any]],
) -> str:
    leader_summary, leader = _watchlist_focus_summary(watchlist_data)
    leader_symbol = leader["symbol"] if leader else "de sterkste asset"
    indicator_phrase = _first_indicator_narrative(tech_ind, "technische")
    return (
        f"Technisch oogt het beeld {_score_bucket(scores.get('technical_score'))}, maar de kwaliteit van de bevestiging zit nog niet overal gelijkmatig in de watchlist. "
        f"{leader_summary} {indicator_phrase} Voor {leader_symbol} is dat constructief zolang de rest van de watchlist niet achterblijft, want anders krijg je relatieve sterkte zonder brede bevestiging. "
        f"De praktische conclusie is dat techniek nu meer richting geeft dan harde vrijbrief: bruikbaar voor review, nog niet automatisch voor agressieve uitbreiding."
    )


def _build_setup_validation_fallback(
    best_setup: Optional[Dict[str, Any]],
    watchlist_data: List[Dict[str, Any]],
    scores: Dict[str, Any],
) -> str:
    if not best_setup:
        return (
            f"De setup-laag blijft {_score_bucket(scores.get('setup_score'))}, maar zonder één duidelijke kandidaat die breed genoeg wordt gedragen door markt en techniek. "
            "Dat betekent dat selectiviteit hier een feature is in plaats van een gemis: de data dwingt nog geen nieuwe positie af. "
            "De juiste vervolgstap is daarom setups blijven reviewen op bevestiging, niet op haast."
        )

    leader_summary, _ = _watchlist_focus_summary(watchlist_data)
    return (
        f"De best scorende setup is {best_setup.get('name')} op {best_setup.get('timeframe')}, met een score van {int(round(to_float(best_setup.get('score')) or 0))}. "
        f"{leader_summary} Dat maakt deze setup bruikbaar als focuspunt, maar alleen als de huidige relatieve sterkte overeind blijft en niet terugvalt naar een gemengd marktbeeld. "
        "Kort gezegd: dit is een kandidaat om strak te reviewen, niet iets om blind als voldongen feit te behandelen."
    )


def _build_strategy_implication_fallback(
    active_strategy: Optional[Dict[str, Any]],
    scores: Dict[str, Any],
    best_setup: Optional[Dict[str, Any]],
) -> str:
    if not active_strategy:
        return (
            f"Er ligt nu geen actieve strategie die vanzelf logisch wordt vanuit een {_score_bucket(scores.get('market_score'))} marktlaag en een "
            f"{_score_bucket(scores.get('technical_score'))} technische laag. "
            "Dat is geen tekortkoming maar een signaal dat de context nog niet scherp genoeg samenvalt. "
            "De juiste discipline is daarom wachten op extra bevestiging voordat strategie weer voorrang krijgt boven observatie."
        )

    setup_name = active_strategy.get("setup_name") or (best_setup or {}).get("name") or "de actieve setup"
    confidence = active_strategy.get("confidence_score")
    confidence_phrase = (
        f"De huidige confidence rond deze strategie ligt op {int(round(confidence))}."
        if confidence is not None
        else "De huidige confidence vraagt om contextuele bevestiging."
    )
    return (
        f"De actieve strategie rond {setup_name} blijft valide zolang markt, techniek en setup niet uit elkaar beginnen te lopen. "
        f"{confidence_phrase} Dat betekent dat de strategie vooral robuust is als bevestiging doorzet, maar fragiel wordt zodra de marktlaag terugvalt zonder dat techniek mee verbetert. "
        "Operationeel is dit dus een omgeving om aannames te toetsen en niet om de risicobandbreedte onnodig te verbreden."
    )


def _build_bot_strategy_fallback(
    bot_snapshot: Dict[str, Any],
    portfolio_health: Optional[Dict[str, Any]],
    best_setup: Optional[Dict[str, Any]],
) -> str:
    action = (bot_snapshot or {}).get("action") or "hold"
    setup_match = (bot_snapshot or {}).get("setup_match") or (best_setup or {}).get("name")
    equity = (portfolio_health or {}).get("equity_eur")
    invested = (portfolio_health or {}).get("invested_eur")
    portfolio_phrase = ""
    if equity is not None and invested is not None:
        portfolio_phrase = (
            f" Binnen de portefeuille staat ongeveer EUR {int(round(invested))} aan kapitaal aan het werk op een equitybasis van EUR {int(round(equity))}, "
            "waardoor position sizing en follow-through zwaarder wegen dan alleen signaalsterkte."
        )
    if action == "hold":
        return (
            "De bot blijft vandaag bewust in hold-modus, wat aangeeft dat de drempels voor uitvoering nog niet schoon genoeg zijn doorlopen. "
            f"De meest waarschijnlijke kandidaat blijft {setup_match or 'de huidige reviewcontext'}, maar de data geeft nog geen vrijbrief om die mechanisch om te zetten naar actie."
            f"{portfolio_phrase} Dat is precies het soort terughoudendheid dat je wilt zien wanneer bevestiging nog niet breed genoeg is."
        )

    return (
        f"De bot heeft vandaag een {action}-beslissing genomen vanuit een context waarin {setup_match or 'de best scorende setup'} het dichtst bij uitvoerbare bevestiging lag. "
        f"De waarde daarvan zit niet alleen in de actie zelf, maar in het feit dat markt, techniek en setup voldoende samenvielen om uitvoering te rechtvaardigen.{portfolio_phrase} "
        "De juiste lezing is daarom dat de bot hier risicobeheer volgt, niet dat hij een vrijbrief geeft voor meer agressie buiten hetzelfde kader."
    )


def _build_outlook_fallback(
    transition: Optional[Dict[str, Any]],
    scores: Dict[str, Any],
    watchlist_data: List[Dict[str, Any]],
) -> str:
    _, leader = _watchlist_focus_summary(watchlist_data)
    leader_symbol = leader["symbol"] if leader else "de leidende asset"
    transition_state = None
    if isinstance(transition, dict):
        transition_state = transition.get("state") or transition.get("label") or transition.get("regime_shift")
    shift_phrase = (
        f"Als de transitie-indicator verder doorschuift richting {transition_state}, dan moet de markt dat bevestigen via bredere meebeweging buiten alleen {leader_symbol}."
        if transition_state
        else f"Als de leidende signalen verder aantrekken, dan moet de markt dat bevestigen via bredere meebeweging buiten alleen {leader_symbol}."
    )
    return (
        f"Voor de komende 24 tot 48 uur ligt de focus op bevestiging van een {_score_bucket(scores.get('market_score'))} marktlaag en een "
        f"{_score_bucket(scores.get('technical_score'))} technische laag. {shift_phrase} "
        "Als die bevestiging uitblijft, dan blijft het basisscenario dat de markt terugvalt naar selectie en review in plaats van expansie. "
        "Als ze wel samen optrekken, ontstaat juist ruimte om setups en strategie met meer vertrouwen opnieuw te wegen."
    )


# =====================================================
# Delta helpers (today vs previous report_date)
# =====================================================


def _get_latest_market_row_for_date(cur, report_date) -> Optional[Tuple]:
    """
    Haal de meest recente market_data snapshot voor een bepaalde datum.
    Verwacht: (price, change_24h, volume)
    """
    cur.execute(
        """
        SELECT price, change_24h, volume
        FROM market_data
        WHERE DATE(timestamp) = %s
        ORDER BY timestamp DESC
        LIMIT 1;
        """,
        (report_date,),
    )
    return cur.fetchone()


def get_daily_deltas(user_id: int) -> Dict[str, Any]:
    """
    Berekent veranderingen t.o.v. de vorige beschikbare report_date.
    Deze deltas zijn analytische brandstof en reduceren herhaling,
    omdat elke sectie begint vanuit verandering (of juist het uitblijven daarvan).

    Output keys:
    - macro_delta, technical_delta, market_delta, setup_delta
    - price_delta, change_delta, volume_delta
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Pak laatste 2 dagen scores (beschikbaar voor user)
            cur.execute(
                """
                SELECT report_date, macro_score, technical_score, market_score, setup_score
                FROM daily_scores
                WHERE user_id = %s
                ORDER BY report_date DESC
                LIMIT 2;
                """,
                (user_id,),
            )
            rows = cur.fetchall()

            if not rows or len(rows) < 2:
                return {}

            today_date, today_macro, today_tech, today_market, today_setup = rows[0]
            prev_date, prev_macro, prev_tech, prev_market, prev_setup = rows[1]

            # Markt snapshots per datum (laatste snapshot die dag)
            today_m = _get_latest_market_row_for_date(cur, today_date)
            prev_m = _get_latest_market_row_for_date(cur, prev_date)

            # Deltas scores
            macro_delta = to_float(today_macro) - to_float(prev_macro) if (today_macro is not None and prev_macro is not None) else None
            technical_delta = to_float(today_tech) - to_float(prev_tech) if (today_tech is not None and prev_tech is not None) else None
            market_delta = to_float(today_market) - to_float(prev_market) if (today_market is not None and prev_market is not None) else None
            setup_delta = to_float(today_setup) - to_float(prev_setup) if (today_setup is not None and prev_setup is not None) else None

            # Deltas market (price/change/volume)
            price_delta = None
            change_delta = None
            volume_delta = None

            if today_m and prev_m:
                t_price, t_change, t_vol = today_m
                p_price, p_change, p_vol = prev_m

                if t_price is not None and p_price is not None:
                    price_delta = to_float(t_price) - to_float(p_price)
                if t_change is not None and p_change is not None:
                    change_delta = to_float(t_change) - to_float(p_change)
                if t_vol is not None and p_vol is not None:
                    volume_delta = to_float(t_vol) - to_float(p_vol)

            return {
                "macro_delta": macro_delta,
                "technical_delta": technical_delta,
                "market_delta": market_delta,
                "setup_delta": setup_delta,
                "price_delta": price_delta,
                "change_delta": change_delta,
                "volume_delta": volume_delta,
                "today_date": today_date.isoformat() if today_date else None,
                "prev_date": prev_date.isoformat() if prev_date else None,
            }
    finally:
        conn.close()


# =====================================================
# BOT DAILY SNAPSHOT (BACKEND = TRUTH)
# =====================================================
def get_bot_daily_snapshot(user_id: int) -> Dict[str, Any]:
    """
    Leest de botbeslissing van vandaag.

    CONTRACT (frontend + report + pdf):
    {
      bot_name: str,
      action: "buy" | "sell" | "hold",
      confidence: float | str | None,
      amount_eur: float | None,
      setup_match: str | None,
      reason: str | None
    }

    BELANGRIJK:
    - Deze functie retourneert ALTIJD een dict
    - HOLD is een geldige, bewuste beslissing
    - setup_match is ALTIJD string of None (NOOIT object)
    """

    conn = get_db_connection()
    if not conn:
        return {
            "bot_name": "Bot",
            "action": "hold",
            "confidence": None,
            "amount_eur": None,
            "setup_match": None,
            "reason": "Geen databaseverbinding — bot snapshot niet beschikbaar.",
        }

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  b.name AS bot_name,
                  d.action,
                  d.confidence,
                  d.amount_eur,
                  d.scores_json,
                  d.reason_json,
                  o.status AS order_status,
                  o.estimated_price_eur AS executed_price
                FROM bot_decisions d
                JOIN bot_configs b ON b.id = d.bot_id
                LEFT JOIN bot_orders o ON o.decision_id = d.id
                WHERE d.user_id = %s
                  AND d.decision_date = CURRENT_DATE
                ORDER BY d.updated_at DESC
                LIMIT 1;
                """,
                (user_id,),
            )
            row = cur.fetchone()

        # ─────────────────────────────────────────────
        # Geen bot decision vandaag → expliciete HOLD
        # ─────────────────────────────────────────────
        if not row:
            return {
                "bot_name": "Bot",
                "action": "hold",
                "confidence": None,
                "amount_eur": None,
                "setup_match": None,
                "reason": "Geen botbeslissing vandaag — drempels of voorwaarden niet gehaald.",
                "order_status": None,
                "executed_price": None,
            }

        bot_name, action, confidence, amount_eur, scores_json, reason_json, order_status, executed_price = row

        # ─────────────────────────────────────────────
        # Action normaliseren
        # ─────────────────────────────────────────────
        normalized_action = (action or "hold").lower()
        if normalized_action not in ("buy", "sell", "hold"):
            normalized_action = "hold"

        # ─────────────────────────────────────────────
        # scores_json veilig parsen
        # ─────────────────────────────────────────────
        if scores_json is None:
            scores_json = {}
        elif isinstance(scores_json, str):
            try:
                scores_json = json.loads(scores_json)
            except Exception:
                scores_json = {}

        # ─────────────────────────────────────────────
        # setup_match NORMALISEREN → STRING
        # ─────────────────────────────────────────────
        raw_match = scores_json.get("setup_match")
        setup_match = None

        if isinstance(raw_match, dict):
            setup_match = raw_match.get("name") or raw_match.get("label") or raw_match.get("id")
        elif isinstance(raw_match, list):
            setup_match = ", ".join(
                str(x.get("name") if isinstance(x, dict) and x.get("name") else x) for x in raw_match
            )
        elif isinstance(raw_match, (str, int, float)):
            setup_match = str(raw_match)

        # ─────────────────────────────────────────────
        # reason_json → nette tekst
        # ─────────────────────────────────────────────
        reason_text = None

        if reason_json is not None:
            if isinstance(reason_json, str):
                try:
                    parsed = json.loads(reason_json)
                    reason_json = parsed
                except Exception:
                    reason_text = reason_json

            if reason_text is None:
                if isinstance(reason_json, list):
                    reason_text = "; ".join(str(x) for x in reason_json if str(x).strip())
                elif isinstance(reason_json, dict):
                    if "reason" in reason_json:
                        reason_text = str(reason_json["reason"])
                    elif "reasons" in reason_json and isinstance(reason_json["reasons"], list):
                        reason_text = "; ".join(str(x) for x in reason_json["reasons"] if str(x).strip())
                    else:
                        reason_text = str(reason_json)

        if normalized_action == "hold" and not reason_text:
            reason_text = "Geen trade: voorwaarden of risicodrempels niet gehaald."

        # ─────────────────────────────────────────────
        # amount / confidence veilig
        # ─────────────────────────────────────────────
        amount_val = None
        try:
            if amount_eur is not None:
                amount_val = float(amount_eur)
        except Exception:
            amount_val = None

        conf_val = confidence
        try:
            if isinstance(confidence, str) and confidence.strip().replace(".", "", 1).isdigit():
                conf_val = float(confidence)
        except Exception:
            conf_val = confidence

        return {
            "bot_name": bot_name or "Bot",
            "action": normalized_action,
            "confidence": conf_val,
            "amount_eur": amount_val,
            "setup_match": setup_match,
            "reason": reason_text,
            "order_status": order_status,
            "executed_price": to_float(executed_price),
        }

    finally:
        conn.close()


# =====================================================
# Text generation (AI) + defensive parsing
# =====================================================
def generate_text(prompt: str, fallback: str) -> str:
    """
    Verantwoordelijk voor:
    - AI-call
    - opschonen output
    - JSON-defensieve parsing
    - fail-safe fallback (voorkomt report crash)
    """

    # 🔥 voorkomt context explosions in logs
    if len(prompt) > 12000:
        logger.warning("⚠️ Large AI prompt detected (%s chars)", len(prompt))

    try:
        # ✅ FIX: keyword-only arguments gebruiken
        raw = ask_gpt_text(
            prompt=prompt,
            system_role=SYSTEM_PROMPT,
        )
    except Exception as e:
        logger.exception("❌ AI call failed")
        return fallback

    # lege response → fallback
    if not raw:
        logger.warning("⚠️ AI gaf lege response — fallback gebruikt.")
        return fallback

    # 1️⃣ Strip markdown/code fences
    text = raw.replace("```json", "").replace("```", "").strip()

    # 2️⃣ gewone tekst → direct terug
    if not text.lstrip().startswith("{"):
        return text if len(text) > 5 else fallback

    # 3️⃣ JSON parsing defensief
    try:
        parsed = json.loads(text)
        parts = _flatten_text(parsed)

        blacklist = {
            "GO",
            "NO-GO",
            "STATUS",
            "RISICO",
            "IMPACT",
            "ACTIE",
            "ONVOLDOENDE DATA",
            "CONDITIONAL",
        }

        cleaned = [
            p for p in parts
            if p.strip() and p.strip().upper() not in blacklist
        ]

        if cleaned:
            return "\n\n".join(cleaned)

        if parts:
            return "\n\n".join(parts)

    except Exception as e:
        logger.warning("⚠️ JSON parsing mislukt — ruwe tekst gebruikt. Error=%s", e)

    return text if len(text) > 5 else fallback


# =====================================================
# Repetition control (cross-section deduplication)
# =====================================================
def _normalize_sentence(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s]", "", s)
    return s


def _is_too_similar(a: str, b: str, threshold: float = 0.82) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= threshold


def reduce_repetition(text: str, seen: List[str]) -> str:
    """
    Verwijdert zinnen die semantisch te sterk lijken
    op eerder geschreven zinnen in andere secties.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text)
    output: List[str] = []

    for s in sentences:
        norm = _normalize_sentence(s)

        if not norm or len(norm) < 20:
            output.append(s)
            continue

        if any(_is_too_similar(norm, prev) for prev in seen):
            continue

        output.append(s)
        seen.append(norm)

    return " ".join(output)


# =====================================================
# SCORES & MARKET
# =====================================================
def get_daily_scores(user_id: int, symbol: str = "BTC") -> Dict[str, Any]:
    conn = get_db_connection()
    if not conn:
        return {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT macro_score, technical_score, market_score, setup_score
                FROM daily_scores
                WHERE user_id = %s AND symbol = %s
                ORDER BY report_date DESC
                LIMIT 1;
                """,
                (user_id, symbol),
            )
            row = cur.fetchone()

        return {
            "macro_score": to_float(row[0]) if row else None,
            "technical_score": to_float(row[1]) if row else None,
            "market_score": to_float(row[2]) if row else None,
            "setup_score": to_float(row[3]) if row else None,
        }
    finally:
        conn.close()


def get_market_snapshot() -> Dict[str, Any]:
    conn = get_db_connection()
    if not conn:
        return {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT price, change_24h, volume
                FROM market_data
                ORDER BY timestamp DESC
                LIMIT 1;
                """
            )
            row = cur.fetchone()

        return {
            "price": to_float(row[0]) if row else None,
            "change_24h": to_float(row[1]) if row else None,
            "volume": to_float(row[2]) if row else None,
        }
    finally:
        conn.close()


def _indicator_list(cur, sql, user_id):
    cur.execute(sql, (user_id,))
    rows = cur.fetchall()
    return [
        {
            "indicator": r[0],
            "value": to_float(r[1]),
            "score": to_float(r[2]),
            "interpretation": r[3],
        }
        for r in rows
    ]


# =====================================================
# INDICATOR HIGHLIGHTS (UNIFORM STRUCTUUR – GEEN DUPLICATEN)
# =====================================================
def get_market_indicator_highlights(user_id: int) -> List[dict]:
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            return _indicator_list(
                cur,
                """
                SELECT DISTINCT ON (name)
                    name,
                    value,
                    score,
                    interpretation
                FROM market_data_indicators
                WHERE user_id = %s
                  AND score IS NOT NULL
                  AND DATE(timestamp) = CURRENT_DATE
                ORDER BY name, timestamp DESC
                LIMIT 5;
                """,
                user_id,
            )
    finally:
        conn.close()


# =====================================================
# Macro indicator highlights
# =====================================================
def get_macro_indicator_highlights(user_id: int) -> List[dict]:
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            return _indicator_list(
                cur,
                """
                SELECT DISTINCT ON (name)
                    name,
                    value,
                    score,
                    COALESCE(interpretation, action)
                FROM macro_data
                WHERE user_id = %s
                  AND score IS NOT NULL
                  AND DATE(timestamp) = CURRENT_DATE
                ORDER BY name, timestamp DESC
                LIMIT 5;
                """,
                user_id,
            )
    finally:
        conn.close()


# =====================================================
# Technical indicator highlights
# =====================================================
def get_technical_indicator_highlights(user_id: int, symbol: str = "BTC") -> List[dict]:
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            return _indicator_list(
                cur,
                f"""
                SELECT DISTINCT ON (indicator)
                    indicator,
                    value,
                    score,
                    COALESCE(uitleg, advies)
                FROM technical_indicators
                WHERE user_id = %s
                  AND symbol = '{symbol}'
                  AND score IS NOT NULL
                  AND DATE(timestamp) = CURRENT_DATE
                ORDER BY indicator, timestamp DESC
                LIMIT 5;
                """,
                user_id,
            )
    finally:
        conn.close()

def get_watchlist_summary(user_id: int) -> List[Dict[str, Any]]:
    """
    Verzamelt de essentie van alle assets in de watchlist voor het rapport.
    """
    conn = get_db_connection()
    if not conn:
        return []
        
    try:
        with conn.cursor() as cur:
            # 1. Haal alle unieke symbols van deze gebruiker op (die vandaag scores hebben)
            cur.execute("""
                SELECT DISTINCT symbol 
                FROM daily_scores 
                WHERE user_id = %s 
                AND report_date = CURRENT_DATE
            """, (user_id,))
            symbols = [r[0] for r in cur.fetchall()]
            
            if not symbols:
                # Fallback naar watchlist tabel of default
                cur.execute("SELECT symbol FROM watchlists WHERE user_id = %s", (user_id,))
                symbols = [r[0] for r in cur.fetchall()] or ["BTC"]

        watchlist_data = []
        for symbol in symbols:
            # Haal scores op
            scores = get_daily_scores(user_id, symbol=symbol)
            # Haal top indicators op
            tech = get_technical_indicator_highlights(user_id, symbol=symbol)
            
            watchlist_data.append({
                "symbol": symbol,
                "scores": scores,
                "top_indicators": tech
            })
            
        return watchlist_data
    finally:
        if conn:
            conn.close()


# =====================================================
# SETUP SNAPSHOT
# =====================================================
def get_setup_snapshot(user_id: int) -> Dict[str, Any]:
    conn = get_db_connection()
    if not conn:
        return {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.id, s.name, s.symbol, s.timeframe, d.score
                FROM daily_setup_scores d
                JOIN setups s ON s.id = d.setup_id
                WHERE d.user_id = %s
                ORDER BY d.report_date DESC, d.is_best DESC, d.score DESC
                LIMIT 1;
                """,
                (user_id,),
            )
            best = cur.fetchone()

            cur.execute(
                """
                SELECT s.id, s.name, d.score
                FROM daily_setup_scores d
                JOIN setups s ON s.id = d.setup_id
                WHERE d.user_id = %s
                ORDER BY d.report_date DESC, d.score DESC
                LIMIT 5;
                """,
                (user_id,),
            )
            rows = cur.fetchall()

        if not best:
            return {}

        return {
            "best_setup": {
                "id": best[0],
                "name": best[1],
                "symbol": best[2],
                "timeframe": best[3],
                "score": to_float(best[4]),
            },
            "top_setups": [{"id": r[0], "name": r[1], "score": to_float(r[2])} for r in rows],
        }
    finally:
        conn.close()


# =====================================================
# PORTFOLIO HEALTH SNAPSHOT
# =====================================================
def get_portfolio_health_snapshot(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT equity_eur, cash_eur, invested_eur, unrealized_pnl_eur
                FROM portfolio_balance_snapshots
                WHERE user_id = %s
                ORDER BY ts DESC
                LIMIT 1;
            """, (user_id,))
            row = cur.fetchone()
        
        if not row:
            return None
            
        equity, cash, invested, unrealized = row
        return {
            "equity_eur": to_float(equity),
            "cash_eur": to_float(cash),
            "invested_eur": to_float(invested),
            "unrealized_pnl_eur": to_float(unrealized)
        }
    finally:
        conn.close()

# =====================================================
# STRATEGY SNAPSHOT
# =====================================================
def get_active_strategy_snapshot(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    s.name, s.symbol, s.timeframe,
                    a.entry, a.targets, a.stop_loss,
                    a.adjustment_reason, a.confidence_score
                FROM active_strategy_snapshot a
                JOIN setups s ON s.id = a.setup_id
                WHERE a.user_id = %s
                ORDER BY a.snapshot_date DESC, a.created_at DESC
                LIMIT 1;
                """,
                (user_id,),
            )
            row = cur.fetchone()

        if not row:
            return None

        return {
            "setup_name": row[0],
            "symbol": row[1],
            "timeframe": row[2],
            "entry": to_float(row[3]),
            "targets": row[4],
            "stop_loss": to_float(row[5]),
            "adjustment_reason": row[6],
            "confidence_score": to_float(row[7]),
        }
    finally:
        conn.close()


# =====================================================
# PROMPTS (REPORT AGENT 2.0 — SAMENHANG & VERKLARING)
# =====================================================
def p_exec() -> str:
    return """
Formuleer één centrale markthypothese voor vandaag.

Verplicht:
- Begin met wat er veranderde t.o.v. de vorige dag (of benoem expliciet dat het beeld gelijk bleef)
- Geef de belangrijkste oorzaak/driver die uit de data volgt
- Maak duidelijk of dit een structurele verschuiving lijkt of een reactieve beweging

Schrijf als één analytisch en diepgaand openingsverhaal van minimaal 4 tot 6 zinnen.
Geen opsommingen, geen labels, geen herhaling van dezelfde zinstructuren.
""".strip()


def p_market() -> str:
    return """
Analyseer de marktbeweging van vandaag.

Verplicht:
- Start met de verandering t.o.v. gisteren (prijs/volume/market score)
- Verklaar waarom de market score bewoog of juist niet
- Leg uit wat volume zegt over de kwaliteit van de beweging
- Eindig met een kort oordeel over duurzaamheid (zonder prijsniveaus)

Schrijf een gedetailleerde alinea van minimaal 4 tot 6 zinnen. Geen lijstjes, geen herhaling van cijfers zonder causaliteit.
""".strip()


def p_macro() -> str:
    return """
Analyseer de macro-omgeving van vandaag.

Verplicht:
- Benoem welke macro-krachten dominant bleven en wat dat betekent voor het speelveld
- Leg uit waarom macro-indicatoren meebewegen of juist NIET meebewegen met de koers
- Maak de spanning concreet tussen veiligheid (Bitcoin) en risicobereidheid (market context)

Schrijf een gedetailleerde alinea van minimaal 4 tot 6 zinnen. Geen macro-boekjesuitleg, alleen interpretatie van de aangeleverde data.
""".strip()


def p_technical() -> str:
    return """
Analyseer de technische structuur van vandaag.

Verplicht:
- Leg uit of techniek bevestigt, achterblijft of tegenwerkt t.o.v. de beweging
- Noem welke signalen betrouwbaarheid ONDERMIJNEN of juist VERSTERKEN (alleen uit data)
- Beschrijf of dit herstel, consolidatie of ruis is, en waarom

Schrijf een gedetailleerde alinea van minimaal 4 tot 6 zinnen. Geen klassieke TA-uitleg, geen indicator-definities, geen prijsniveaus.
""".strip()


def p_setup(best_setup: Optional[Dict[str, Any]]) -> str:
    if not best_setup:
        return """
Er is vandaag geen setup die voldoende aansluit bij de huidige marktomstandigheden.

Verplicht:
- Leg uit waarom setups nu niet passen (koppel aan scorecombinatie + indicatorcontext)
- Benoem wat er in de data zou moeten veranderen voordat setups weer logisch worden

Geen aannames buiten de data.
""".strip()

    return f"""
De best scorende setup vandaag is "{best_setup.get('name')}" op timeframe {best_setup.get('timeframe')} (score {best_setup.get('score')}).

Verplicht:
- Verklaar waarom deze setup relatief beter scoort dan de rest (koppel aan actuele context)
- Beoordeel of de omstandigheden deze setup ondersteunen of slechts tolereren
- Maak duidelijk of dit iets is om actief te gebruiken of vooral te monitoren (zonder trade-instructies)

Schrijf een gedetailleerde alinea van minimaal 4 tot 6 zinnen. Geen herhaling van de setup-naam in elke zin.
""".strip()


def p_strategy(active_strategy: Optional[Dict[str, Any]]) -> str:
    if not active_strategy:
        return """
Er is momenteel geen actieve strategie.

Verplicht:
- Leg uit waarom de huidige scorecombinatie geen strategie rechtvaardigt
- Benoem welke voorwaarden in de data eerst moeten verbeteren/verslechteren voordat een strategie logisch wordt

Geen hypothetische trades, geen prijsniveaus.
""".strip()

    return """
Er is een actieve strategie aanwezig.

Verplicht:
- Plaats de strategie in de huidige macro-, market- en technische context
- Benoem de belangrijkste aannames die vandaag waar moeten blijven
- Beoordeel of de strategie robuust blijft of fragieler wordt (zonder aanpassingen voor te schrijven)

Schrijf een gedetailleerde alinea van minimaal 4 tot 6 zinnen. Geen herhaling van entries/targets/stop; die staan elders.
""".strip()


def p_bot_strategy(bot_snapshot: Dict[str, Any]) -> str:
    if bot_snapshot.get("action") == "hold":
        return """
De bot heeft vandaag bewust geen trade geplaatst.

Verplicht:
- Leg uit welke voorwaarden/drempels uit de botdata onvoldoende waren
- Plaats dit in de bredere context: waarom terughoudendheid vandaag logisch was
- Benoem wat er in de data moet veranderen voordat actie logisch wordt (algemeen, niet als tradeplan)

Gebruik uitsluitend de aangeleverde botdata. Geen aannames. Geen nieuwe beslissingen.
""".strip()

    return """
Er is vandaag een botbeslissing genomen.

BELANGRIJK:
- De feitelijke botactie, confidence en bedragen worden elders getoond
- Herhaal of parafraseer deze NIET

Verplicht:
- Geef context waarom de beslissing logisch is binnen de scorecombinatie
- Koppel de beslissing expliciet aan de persoonlijke portfolio-balans (equity vs invested). Bijv: als er sprake is van een drawdown, benadruk waarom risicobeheer cruciaal was
- Koppel aan het bredere marktkader (zonder prijsniveaus)

Schrijf een gedetailleerde alinea van minimaal 4 tot 6 zinnen. Gebruik uitsluitend de aangeleverde botdata. Geen aannames. Geen nieuwe beslissingen.
""".strip()


def p_outlook() -> str:
    return """
Schrijf een scenario-vooruitblik voor de komende 24-48 uur.

Verplicht:
- Benoem welke factoren bevestiging vereisen
- Benoem welke signalen een regime-shift zouden aangeven
- Houd het conditioneel (als/dan), zonder prijsniveaus

Schrijf een gedetailleerde alinea van minimaal 4 tot 6 zinnen. Geen opsommingen, één doorlopend stuk tekst.
""".strip()

def build_compact_context(
    regime,
    transition,
    prev_report,
    deltas,
    market,
    scores,
    market_ind,
    macro_ind,
    tech_ind,
    best_setup,
    active_strategy,
    bot_snapshot,
    portfolio_health,
    ai_insights,
    ai_reflections,
    watchlist_data = None
) -> str:
    """
    Compacte context builder voor Multi-Asset Rapport.
    """

    def short_indicators(lst, max_items=3):
        if not lst:
            return []
        output = []
        for i in lst[:max_items]:
            output.append({
                "name": i.get("indicator") or i.get("name"),
                "score": i.get("score"),
            })
        return output

    context = {
        "regime": {
            "label": regime.get("label") if regime else None,
            "confidence": regime.get("confidence") if regime else None,
        },
        "watchlist": [
            {
                "symbol": w["symbol"],
                "master_score": w["scores"].get("technical_score", 50),
                "indicators": short_indicators(w["top_indicators"])
            }
            for w in (watchlist_data or [])
        ],
        "deltas": {
            "macro": deltas.get("macro_delta"),
            "market": deltas.get("market_delta"),
            "technical": deltas.get("technical_delta"),
        },
        "scores": {
            "macro": scores.get("macro_score"),
            "technical": scores.get("technical_score"),
            "market": scores.get("market_score"),
        },
        "positioning": {
            "best_setup": best_setup.get("name") if best_setup else None,
            "bot_action": bot_snapshot.get("action"),
            "portfolio_health": portfolio_health
        },
        "memory": {
            "prev_summary": prev_report[1] if prev_report else None
        }
    }

    return json.dumps(context, ensure_ascii=False)


def generate_daily_report_sections(user_id: int) -> Dict[str, Any]:
    # -------------------------------------------------
    # 1) Basis data (Multi-Asset)
    # -------------------------------------------------
    watchlist_data = get_watchlist_summary(user_id)
    scores = get_daily_scores(user_id) # default BTC voor legacy keys
    market = get_market_snapshot()

    market_ind = get_market_indicator_highlights(user_id)
    macro_ind = get_macro_indicator_highlights(user_id)
    tech_ind = get_technical_indicator_highlights(user_id)

    setup_snapshot = get_setup_snapshot(user_id)
    best_setup = setup_snapshot.get("best_setup")
    active_strategy = get_active_strategy_snapshot(user_id)
    bot_snapshot = get_bot_daily_snapshot(user_id)
    portfolio_health = get_portfolio_health_snapshot(user_id)
    deltas = get_daily_deltas(user_id)

    # -------------------------------------------------
    # REGIME & TRANSITION
    # -------------------------------------------------
    regime = get_regime_memory(user_id)
    transition = compute_transition_detector(user_id)

    # -------------------------------------------------
    # COMPACT CONTEXT
    # -------------------------------------------------
    context_blob = build_compact_context(
        regime,
        transition,
        None,
        deltas,
        market,
        scores,
        market_ind,
        macro_ind,
        tech_ind,
        best_setup,
        active_strategy,
        bot_snapshot,
        portfolio_health,
        [],
        [],
        watchlist_data=watchlist_data
    )

    base_context = "CONTEXT:\n" + context_blob + "\n\n"

    # -------------------------------------------------
    # BATCHED AI GENERATION
    # -------------------------------------------------
    batched_prompt = f"""
{base_context}

Je bent een Multi-Asset Portfolio Strategist. Retourneer ALLEEN een JSON object met EXACT deze 8 keys.
Analyseer de gehele watchlist ({', '.join([w['symbol'] for w in watchlist_data])}).

Keys:
1. "executive_summary": {p_exec()} Focus op het dagrapport voor de gehele watchlist.
2. "market_analysis": {p_market()} Betrek relatieve sterkte van assets.
3. "macro_context": {p_macro()}
4. "technical_analysis": {p_technical()} Vergelijk technische signalen tussen de assets.
5. "setup_validation": {p_setup(best_setup)}
6. "strategy_implication": {p_strategy(active_strategy)}
7. "bot_strategy": {p_bot_strategy(bot_snapshot)}
8. "outlook": {p_outlook()}
"""

    batched_result = {}
    try:
        raw_json = ask_gpt_json(prompt=batched_prompt, system_role=SYSTEM_PROMPT, max_tokens=3000)
        if isinstance(raw_json, dict):
            batched_result = raw_json
    except Exception:
        logger.exception("❌ Batched AI generation failed")

    fallback_sections = {
        "executive_summary": _build_executive_summary_fallback(
            watchlist_data,
            market,
            scores,
            deltas,
            regime,
            transition,
            best_setup,
        ),
        "market_analysis": _build_market_analysis_fallback(
            watchlist_data,
            market,
            scores,
            deltas,
        ),
        "macro_context": _build_macro_context_fallback(
            scores,
            macro_ind,
            regime,
        ),
        "technical_analysis": _build_technical_analysis_fallback(
            watchlist_data,
            scores,
            tech_ind,
        ),
        "setup_validation": _build_setup_validation_fallback(
            best_setup,
            watchlist_data,
            scores,
        ),
        "strategy_implication": _build_strategy_implication_fallback(
            active_strategy,
            scores,
            best_setup,
        ),
        "bot_strategy": _build_bot_strategy_fallback(
            bot_snapshot,
            portfolio_health,
            best_setup,
        ),
        "outlook": _build_outlook_fallback(
            transition,
            scores,
            watchlist_data,
        ),
    }

    weak_defaults = {
        "regime intact.",
        "market steady.",
        "macro unchanged.",
        "technicals neutral.",
        "setups selective.",
        "strategy stable.",
        "bot inactive.",
        "await confirmation.",
    }

    seen_sentences: List[str] = []

    def get_section(key: str) -> str:
        fallback = fallback_sections[key]
        raw_text = batched_result.get(key)
        text = str(raw_text).strip() if raw_text not in (None, "") else fallback
        if text.lower() in weak_defaults or len(text) < 40:
            text = fallback
        return reduce_repetition(text, seen_sentences)

    # -------------------------------------------------
    # RESULT
    # -------------------------------------------------
    result = {
        "executive_summary": get_section("executive_summary"),
        "market_analysis": get_section("market_analysis"),
        "macro_context": get_section("macro_context"),
        "technical_analysis": get_section("technical_analysis"),
        "setup_validation": get_section("setup_validation"),
        "strategy_implication": get_section("strategy_implication"),
        "bot_strategy": get_section("bot_strategy"),
        "outlook": get_section("outlook"),
        "watchlist": watchlist_data,
        "best_setup": best_setup,
        "transition": transition,
        "price": market.get("price"),
        "change_24h": market.get("change_24h"),
        "volume": market.get("volume"),
        "macro_score": scores.get("macro_score"),
        "technical_score": scores.get("technical_score"),
        "market_score": scores.get("market_score"),
        "setup_score": scores.get("setup_score"),
        "market_indicator_highlights": market_ind,
        "macro_indicator_highlights": macro_ind,
        "technical_indicator_highlights": tech_ind,
        "active_strategy": active_strategy,
        "bot_snapshot": bot_snapshot,
    }

    logger.info("✅ Multi-Asset Report agent OK")
    return result
