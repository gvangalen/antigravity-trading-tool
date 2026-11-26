"""Ground a broad profile/Paper-bot comparison in the selected bot's parents."""

from __future__ import annotations

import re
from typing import Any

from backend.services.finn_v2_paper_position_answer import _money, _read_moment


def _requested_bot_name(message: str) -> str | None:
    match = re.search(
        r"\bpaper[-\s]?bot(?:\s+(?:genaamd|met\s+naam))?\s+"
        r"(?!(?:bij|en|met|in|voor|die|waarvan)\b)"
        r"([^?.!,;]{1,80}?)(?=\s+\b(?:bij|en|met|in|voor|die|waarvan)\b|[?.!,;]|$)",
        message, re.I,
    )
    return match.group(1).strip(" ‘'\"”") if match else None


def render_profile_paper_fit_answer(
    message: str, tool_trace: tuple[dict[str, Any], ...], *, asset: str,
    locale: str, user_time_zone: str | None = None,
) -> str | None:
    """Use one owner-scoped profile and account-wide Paper portfolio snapshot.

    The portfolio bot row carries its exact setup and strategy parents. A
    separate latest-setup read can select a different plan for the same asset.
    """
    if (not locale.lower().startswith("nl") or not asset
            or not re.search(r"\b(?:profiel|traderstijl|traderprofiel)\b", message, re.I)
            or not re.search(r"\bpaper[-\s]?bot\b", message, re.I)
            or not re.search(r"\b(?:past|beoordeel\w*|vergelijk\w*)\b", message, re.I)
            or not re.search(r"\b(?:portefeuille|portfolio)\b", message, re.I)
            or re.search(r"\b(?:besluit|beslissing|hold|order)\b", message, re.I)):
        return None

    profiles: list[dict[str, Any]] = []
    portfolios: list[dict[str, Any]] = []
    for call in tool_trace:
        # A later model-selected evaluate_bot call may repeat the profile and
        # portfolio and fail an unrelated latest-setup read. The required
        # account bundle is the coherent source for this comparison.
        if not isinstance(call, dict) or call.get("name") != "get_profile_portfolio_and_bots":
            continue
        for item in (call.get("result") or {}).get("results") or []:
            if not isinstance(item, dict) or item.get("status") != "completed":
                continue
            data = item.get("data")
            if not isinstance(data, dict):
                continue
            if item.get("scope") == "read_profile":
                profiles.append(data)
            elif item.get("scope") == "read_portfolio" and not item.get("asset"):
                portfolios.append(data)
    if len(profiles) != 1 or len(portfolios) != 1:
        return None
    profile = profiles[0].get("trader_profile")
    portfolio = portfolios[0]
    if (profiles[0].get("has_profile") is not True or not isinstance(profile, dict)
            or portfolio.get("environment") != "paper"):
        return None
    rows = [row for row in portfolio.get("bots") or []
            if isinstance(row, dict) and row.get("is_live") is False
            and str(row.get("symbol") or "").upper() == asset.upper()]
    if len(rows) != 1:
        return (f"Ik kan de bedoelde {asset.upper()} Paper-bot uit deze "
                "portefeuilleread niet eenduidig bepalen. Ik heb niets gewijzigd.")
    bot = rows[0]
    # PortfolioBotData exposes the base symbol, but no verified trading pair.
    # Never resolve an explicit BTC/EUR or BTC/USDT request from just BTC.
    if re.search(rf"\b{re.escape(asset)}\s*/\s*[A-Z0-9]{{2,12}}\b", message, re.I):
        return (f"Ik kan het gevraagde {asset.upper()}-handelspaar niet aan "
                "de gelezen Paper-bot koppelen. Controleer de botdetails; ik heb niets gewijzigd.")
    requested_name = _requested_bot_name(message)
    stored_name = str(bot.get("name") or "").strip().casefold()
    allowed_names = ({requested_name.casefold(),
                      f"{asset.upper()} Paper-bot {requested_name}".casefold()}
                     if requested_name else set())
    if requested_name and stored_name not in allowed_names:
        return ("De genoemde Paper-botnaam komt niet overeen met de gelezen "
                "botrij. Ik kan deze vergelijking niet betrouwbaar maken en heb niets gewijzigd.")
    setup_name = str(bot.get("setup_name") or "").strip()
    strategy_name = str(bot.get("strategy_name") or "").strip()
    if (not setup_name or not strategy_name
            or not all(type(bot.get(key)) is int and bot[key] > 0
                       for key in ("bot_id", "setup_id", "strategy_id"))):
        return None
    budget = _money(bot.get("budget_total_eur"))
    bot_invested = _money(bot.get("invested_eur"))
    bot_cash = _money(bot.get("paper_cash_eur"))
    global_data = portfolio.get("global") or {}
    total_cash = _money(global_data.get("cash_balance"))
    total_invested = _money(global_data.get("invested_value"))
    if any(value is None for value in (budget, bot_invested, bot_cash, total_cash, total_invested)):
        return None

    styles = profile.get("trader_types") or []
    focus = profile.get("asset_focus") or []
    risks = profile.get("risk_profiles") or []
    behaviors = profile.get("behavior_flags") or []
    if not all(isinstance(values, list) for values in (styles, focus, risks, behaviors)):
        return None
    profile_parts = []
    if "bitcoin" in focus:
        profile_parts.append("Bitcoin als focus")
    if "dca_investor" in styles:
        profile_parts.append("DCA als stijl")
    if "balanced" in risks:
        profile_parts.append("een normaal risicoprofiel")
    elif "conservative" in risks:
        profile_parts.append("een conservatief risicoprofiel")
    elif "aggressive" in risks:
        profile_parts.append("een agressief risicoprofiel")
    if not profile_parts:
        return None
    profile_text = ", ".join(profile_parts)
    alignment = (
        "De BTC-markt sluit aan bij je gekozen focus. Of de opgeslagen "
        "botregels bij je DCA-stijl en risicogrens passen, volgt niet uit de namen alleen."
        if "bitcoin" in focus and "dca_investor" in styles else
        "De opgeslagen voorkeuren bewijzen op zichzelf niet dat deze botregels bij je risico passen."
    )
    behavior = (
        " Dit is extra relevant omdat je FOMO en overtraden als aandachtspunten hebt opgeslagen."
        if "fomo" in behaviors and "overtrades" in behaviors else
        " Dit is extra relevant omdat je FOMO als aandachtspunt hebt opgeslagen."
        if "fomo" in behaviors else
        " Dit is extra relevant omdat je overtraden als aandachtspunt hebt opgeslagen."
        if "overtrades" in behaviors else ""
    )
    moment = _read_moment(portfolio, user_time_zone)
    cap_enabled = bot.get("budget_limit_enabled") is not False and budget != "0"
    cap_text = (
        f"De botbudgetlimiet is €{budget}; dat is een grens, geen belegde positie of kas."
        if cap_enabled else
        "Er is geen botbudgetlimiet ingeschakeld; €0 is hier geen ingestelde grens of belegde positie."
    )
    cap_check = (
        f"de botbudgetlimiet van €{budget}" if cap_enabled else
        "of je een botbudgetlimiet wilt instellen"
    )
    return (
        f"Je profiel noemt {profile_text}. Je {asset.upper()} Paper-bot is volgens de "
        f"opgeslagen botrelatie gekoppeld aan setup ‘{setup_name}’ en strategie "
        f"‘{strategy_name}’. {alignment}\n\n"
        f"{cap_text} In deze bot is €{bot_invested} werkelijk belegd en staat "
        f"€{bot_cash} botkas. De totale Paper-portefeuille heeft €{total_invested} "
        f"belegd en €{total_cash} totale Paper-kas."
        + (f" Portefeuille uitgelezen op {moment}." if moment else "")
        + f"\n\nControlepunt: toets de instapregels van ‘{strategy_name}’ en {cap_check} "
        f"aan je eigen risicogrens.{behavior}"
    )
