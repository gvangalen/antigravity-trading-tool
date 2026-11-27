"""Deterministic FINN conversation contract for one-off Paper market buys.

The chat only collects explicit terms and prepares a short-lived quote. It
never submits a trade. Execution is a separate owner-bound card action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.services.asset_catalog_service import resolve_catalog_symbol_mention
from backend.services.paper_discretionary_order_service import PaperDiscretionaryOrderService


DRAFT_KEY = "paper_discretionary_order_draft"
_START = re.compile(
    r"\b(?:eenmalig(?:e)?|los(?:se)?|handmatig(?:e)?|paper)\b"
    r".{0,100}\b(?:koop|kopen|kooporder|order|trade)\b|"
    r"\b(?:maak|zet|bereid|plaats)\b.{0,80}\b(?:paper|handmatig|eenmalig)\b"
    r".{0,70}\b(?:koop|order|trade)\b",
    re.I,
)
_DENY = re.compile(r"\b(?:live|echt(?:e)?\s+geld|broker|verkoop|sell|short)\b", re.I)
_READ_ONLY = re.compile(r"\b(?:moet\s+ik|zou\s+ik|waarom|hoe\s+werkt|leg\s+uit|"
                        r"wat\s+is|niet\s+kopen|geen\s+order|zonder\s+order)\b", re.I)
_CANCEL = re.compile(r"^\s*(?:annuleer|stop|cancel|laat\s+maar)\s*[.!]?\s*$", re.I)
_REVISE = re.compile(r"\b(?:wijzig|verander|corrigeer|opnieuw|nieuwe\s+preview|probeer\s+opnieuw)\b", re.I)
_QUOTES = re.compile(r"(?<![A-Z])(?:EUR|USDT)(?![A-Z])", re.I)
_MONEY = (r"(?:\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?"
          r"|\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?"
          r"|\d{1,9}(?:[.,]\d{1,2})?)")
_AMOUNT = re.compile(rf"(?<![\w.,])(?:€\s*)?({_MONEY})\s*(EUR|USDT|€)(?![A-Z])", re.I)


@dataclass(frozen=True)
class PaperOrderChatTurn:
    text: str
    draft: dict[str, Any] | None
    preview: dict[str, Any] | None = None


class PaperOrderConversationService:
    @staticmethod
    def applies(message: str, prior: dict[str, Any] | None) -> bool:
        if prior and prior.get("status") == "collecting":
            return bool(_CANCEL.fullmatch(message) or not _READ_ONLY.search(message))
        if prior and prior.get("status") in {"preview_ready", "needs_reserve"}:
            return bool(_CANCEL.fullmatch(message) or _REVISE.search(message)
                        or _AMOUNT.search(message) or _START.search(message))
        return bool(_START.search(message) and not _READ_ONLY.search(message))

    @staticmethod
    def _amount(message: str, quote_currency: str | None) -> str | None:
        matches = list(_AMOUNT.finditer(message))
        valid = []
        for match in matches:
            # Never accept the numeric suffix of a space/apostrophe-grouped
            # amount (for example, "1 234,56" must not become "234.56").
            if re.search(r"\d[\s'’]+$", message[:match.start()]):
                continue
            currency = "EUR" if match.group(2) == "€" else match.group(2).upper()
            if quote_currency is None or currency == quote_currency:
                raw = match.group(1)
                if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", raw):
                    normalized = raw.replace(".", "").replace(",", ".")
                elif re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?", raw):
                    normalized = raw.replace(",", "")
                else:
                    normalized = raw.replace(",", ".")
                valid.append(normalized)
        return valid[0] if len(valid) == 1 else None

    @classmethod
    async def advance(
        cls, *, message: str, prior: dict[str, Any] | None,
        session, user_id: int, run_id: str,
    ) -> PaperOrderChatTurn:
        if _CANCEL.fullmatch(message):
            return PaperOrderChatTurn("Het Paper-orderconcept is geannuleerd. Er is niets gekocht.", None)
        if _DENY.search(message):
            return PaperOrderChatTurn(
                "Deze kaart is uitsluitend voor een losse Paper-koop. Voor Live of verkoop maak ik hier geen order.",
                None,
            )
        draft = dict(prior or {})
        if draft.get("status") not in {"collecting", "preview_ready", "needs_reserve"}:
            draft = {"status": "collecting"}
        else:
            # Any new order turn invalidates the prior card before collecting
            # corrections or issuing a fresh, uniquely keyed preview.
            draft["status"] = "collecting"
            draft.pop("preview_token", None)
            draft.pop("idempotency_key", None)
        asset = resolve_catalog_symbol_mention(message)
        if asset:
            draft["asset"] = asset
            # A new asset invalidates any old quote and amount.
            if prior and asset != prior.get("asset"):
                draft.pop("quote_currency", None)
                draft.pop("amount_quote", None)
        quotes = {item.upper() for item in _QUOTES.findall(message)}
        if len(quotes) > 1:
            return PaperOrderChatTurn("Kies één handelspaar: EUR of USDT?", draft)
        if len(quotes) == 1:
            quote = next(iter(quotes))
            if quote != draft.get("quote_currency"):
                draft.pop("amount_quote", None)
            draft["quote_currency"] = quote
        if not draft.get("asset"):
            return PaperOrderChatTurn("Voor welk asset wil je een losse Paper-koop voorbereiden?", draft)
        if not draft.get("quote_currency"):
            return PaperOrderChatTurn(
                f"Welk exact handelspaar bedoel je: {draft['asset']}/EUR of {draft['asset']}/USDT?",
                draft,
            )
        amount = cls._amount(message, draft["quote_currency"])
        if amount is not None:
            draft["amount_quote"] = amount
        elif _AMOUNT.search(message):
            # The user attempted to change the amount, but its formatting is
            # ambiguous. Retire the prior preview instead of silently reusing
            # its old amount.
            draft.pop("amount_quote", None)
        if not draft.get("amount_quote"):
            return PaperOrderChatTurn(
                f"Hoeveel {draft['quote_currency']} wil je éénmalig aan {draft['asset']} besteden? "
                "Ik toon eerst een Paper-preview; een tekstbericht plaatst nooit een order.",
                draft,
            )
        preview = await PaperDiscretionaryOrderService(session).preview(
            user_id=user_id, asset=draft["asset"], quote_currency=draft["quote_currency"],
            amount_quote=draft["amount_quote"], idempotency_key=f"paper-order-{run_id}",
        )
        draft.update({
            "status": "preview_ready" if preview["ok"] else "needs_reserve",
            "idempotency_key": f"paper-order-{run_id}",
            "preview_token": preview.get("preview_token"),
        })
        text = (
            f"Dit is een eenmalige Paper-marktkoop voor {preview['pair']} ter waarde van "
            f"{preview['amount_quote']} {draft['quote_currency']}. "
            "Controleer de actuele koers, kosten en kas op de kaart. Alleen de knop Bevestig Paper-koop kan uitvoeren."
            if preview["ok"] else
            f"Ik heb {preview['pair']} en {preview['amount_quote']} {draft['quote_currency']} onthouden. "
            "De vrije Paper-reserve is onvoldoende voor deze koop. Boek eerst bestaande Paper-kas "
            "van een bot over naar de reserve; er is geen order geplaatst."
        )
        return PaperOrderChatTurn(text, draft, preview)
