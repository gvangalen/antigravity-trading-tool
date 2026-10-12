"""Persist verified FINN updates. Reading the feed never generates text."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text

from backend.utils.openai_client import StructuredOutputSpec, ask_gpt_structured_response_async

logger = logging.getLogger(__name__)
VISIBLE = ("unread", "read")
LOCALES = ("nl", "en", "de")
def _verified_lead(value: Any, subject: str, locale: str) -> str | None:
    """Positive grammar: no model-added claim can precede the verified facts."""
    if not isinstance(value, str) or not subject or len(subject) > 120:
        return None
    choices = {
        "nl": (f"Er is een update over {subject}.", f"Jouw plan {subject} heeft een update."),
        "en": (f"There is an update about {subject}.", f"Your plan {subject} has an update."),
        "de": (f"Es gibt ein Update zu {subject}.", f"Dein Plan {subject} hat ein Update."),
    }
    lead = value.strip()
    return lead if lead in choices.get(locale, ()) else None


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _amount_phrase(evidence: dict, locale: str) -> str:
    if evidence.get("amount_kind") not in {"base_amount", "budget_total_eur"}:
        return ""
    try:
        value = Decimal(str(evidence.get("amount_eur")))
    except (InvalidOperation, ValueError, TypeError):
        return ""
    if not value.is_finite() or value < 0 or value > 1_000_000_000:
        return ""
    number = f"{value:.2f}"
    if locale in {"nl", "de"}:
        number = number.replace(".", ",")
    label = {
        "base_amount": {"nl": "Basisbedrag", "en": "Base amount", "de": "Grundbetrag"},
        "budget_total_eur": {"nl": "Botbudgetlimiet", "en": "Bot budget limit", "de": "Bot-Budgetlimit"},
    }[evidence["amount_kind"]][locale]
    return f" {label}: €{number}."


def _move_phrase(evidence: dict, locale: str) -> str:
    try:
        change = Decimal(str(evidence.get("change_24h")))
    except (InvalidOperation, ValueError, TypeError):
        return ""
    if not change.is_finite() or abs(change) > 10000:
        return ""
    number = f"{change:+.1f}"
    if locale in {"nl", "de"}:
        number = number.replace(".", ",")
    return {
        "nl": f" Gemeten koersverandering over 24 uur: {number}%.",
        "en": f" Measured 24-hour price change: {number}%.",
        "de": f" Gemessene Kursänderung über 24 Stunden: {number}%.",
    }[locale]


def _fallback(kind: str, subject: str, evidence: dict, *, focus: str = "brief") -> dict:
    name = str(subject or "").strip()[:120]
    if kind == "plan_match":
        body = {
            "nl": f"De opgeslagen scorevoorwaarden van {name} passen bij de gemeten benchmark. Dit is geen instapsignaal.",
            "en": f"The saved score conditions for {name} match the measured benchmark. This is not an entry signal.",
            "de": f"Die gespeicherten Scorebedingungen für {name} passen zur gemessenen Benchmark. Dies ist kein Einstiegssignal.",
        }
        title = {"nl": "Planvoorwaarden passen", "en": "Plan conditions match", "de": "Planbedingungen passen"}
    elif kind == "data_blocked":
        body = {
            "nl": f"Voor {name} ontbreken complete, actuele markt-, macro- of technische scores. FINN kan de planvoorwaarden nu niet beoordelen.",
            "en": f"Complete, current market, macro or technical scores are missing for {name}. FINN cannot assess the plan conditions yet.",
            "de": f"Für {name} fehlen vollständige, aktuelle Markt-, Makro- oder technische Scores. FINN kann die Planbedingungen noch nicht beurteilen.",
        }
        title = {"nl": "Beoordeling beperkt", "en": "Assessment limited", "de": "Bewertung eingeschränkt"}
    elif kind == "proposal_pending":
        body = {
            "nl": f"Een voorstel voor {name} wacht op jouw afzonderlijke bevestiging. Er is nog niets uitgevoerd.",
            "en": f"A proposal for {name} awaits your separate confirmation. Nothing has been executed.",
            "de": f"Ein Vorschlag für {name} wartet auf deine gesonderte Bestätigung. Es wurde noch nichts ausgeführt.",
        }
        title = {"nl": "Voorstel wacht op jou", "en": "Proposal awaits you", "de": "Vorschlag wartet auf dich"}
    elif kind == "market_move":
        body = {
            "nl": f"De koers van {name} bewoog sterk. Controleer wat dit betekent voor je opgeslagen plan; de beweging alleen is geen koopsignaal.",
            "en": f"The price of {name} moved sharply. Check what this means for your saved plan; the move alone is not a buy signal.",
            "de": f"Der Kurs von {name} hat sich stark bewegt. Prüfe die Bedeutung für deinen gespeicherten Plan; die Bewegung allein ist kein Kaufsignal.",
        }
        title = {"nl": "Marktbeweging", "en": "Market move", "de": "Marktbewegung"}
    elif kind == "bot_decision":
        body = {
            "nl": f"Voor {name} is een Paper-beslissing vastgelegd. Bekijk de botdetails; dit is geen live order.",
            "en": f"A Paper decision was recorded for {name}. Review the bot details; this is not a live order.",
            "de": f"Für {name} wurde eine Paper-Entscheidung gespeichert. Prüfe die Botdetails; dies ist keine Live-Order.",
        }
        title = {"nl": "Paper-beslissing", "en": "Paper decision", "de": "Paper-Entscheidung"}
    else:
        body = {
            "nl": f"Er is een nieuwe opgeslagen gebeurtenis voor {name}. Bespreek de actuele gegevens met FINN.",
            "en": f"There is a new saved event for {name}. Discuss the current facts with FINN.",
            "de": f"Es gibt ein neues gespeichertes Ereignis für {name}. Besprich die aktuellen Fakten mit FINN.",
        }
        title = {"nl": "Update van FINN", "en": "Update from FINN", "de": "Update von FINN"}
    if focus == "context":
        context_bodies = {
            "plan_match": {
                "nl": f"De opgeslagen scoregrenzen van {name} passen bij de gemeten benchmark. Controleer je aparte instapregel; dit is geen instapsignaal.",
                "en": f"The saved score bounds for {name} match the measured benchmark. Check your separate entry rule; this is not an entry signal.",
                "de": f"Die gespeicherten Scoregrenzen für {name} passen zur gemessenen Benchmark. Prüfe deine separate Einstiegsregel; dies ist kein Einstiegssignal.",
            },
            "data_blocked": {
                "nl": f"Voor {name} kan FINN je planvoorwaarden nu niet toetsen omdat complete, actuele scores ontbreken.",
                "en": f"For {name}, FINN cannot check your plan conditions now because complete, current scores are missing.",
                "de": f"Für {name} kann FINN deine Planbedingungen derzeit nicht prüfen, weil vollständige aktuelle Scores fehlen.",
            },
            "proposal_pending": {
                "nl": f"Je voorstel voor {name} staat klaar om te beoordelen. Alleen een afzonderlijke bevestiging kan het opslaan; er is nog niets uitgevoerd.",
                "en": f"Your proposal for {name} is ready to review. Only a separate confirmation can save it; nothing has been executed.",
                "de": f"Dein Vorschlag für {name} steht zur Prüfung bereit. Erst eine gesonderte Bestätigung kann ihn speichern; noch wurde nichts ausgeführt.",
            },
            "market_move": {
                "nl": f"De koers van {name} bewoog sterk. Leg de gemeten beweging naast je opgeslagen plan; zij wijzigt het plan niet en is geen koopsignaal.",
                "en": f"The price of {name} moved sharply. Compare the measured move with your saved plan; it does not change the plan or signal a buy.",
                "de": f"Der Kurs von {name} bewegte sich stark. Vergleiche die gemessene Bewegung mit deinem Plan; sie ändert ihn nicht und ist kein Kaufsignal.",
            },
            "bot_decision": {
                "nl": f"Voor {name} staat een opgeslagen Paper-beslissing in de botdetails. Er is geen live order geplaatst.",
                "en": f"A saved Paper decision for {name} is in the bot details. No live order was placed.",
                "de": f"Für {name} liegt eine gespeicherte Paper-Entscheidung in den Botdetails vor. Es wurde keine Live-Order platziert.",
            },
        }
        body = context_bodies.get(kind, body)
    return {locale: {"title": title[locale],
                     "body": body[locale]
                     + (_amount_phrase(evidence, locale) if kind == "proposal_pending" else "")
                     + (_move_phrase(evidence, locale) if kind == "market_move" else "")}
            for locale in LOCALES}


class FinnCoachFeedService:
    def __init__(self, session):
        self.session = session

    async def _proposal_target(self, proposal, *, user_id: int) -> tuple[str | None, int | None, str | None]:
        """Resolve an existing proposal target by owner, not by asset alone."""
        operation = str(getattr(proposal, "operation_type", "") or "")
        kind = next((part for part in ("setup", "strategy", "bot")
                     if operation.endswith(f"_{part}")), None)
        if kind is None or operation.startswith("create_"):
            return None, None, None
        payload = getattr(proposal, "payload_json", None) or {}
        change = payload.get("change") or {}
        target = payload.get("target") or {}
        try:
            target_id = int(target.get("target_id") or change.get(f"{kind}_id"))
        except (TypeError, ValueError):
            return kind, None, None
        table = {"setup": "setups", "strategy": "strategies", "bot": "bot_configs"}[kind]
        row = (await self.session.execute(text(
            f"SELECT name FROM {table} WHERE id = :target_id AND user_id = :user_id"
        ), {"target_id": target_id, "user_id": user_id})).mappings().one_or_none()
        if not row:
            return kind, None, None
        return kind, target_id, str(row["name"]) if row.get("name") else None

    async def publish_pending_proposal(self, proposal, *, user_id: int) -> str | None:
        """A persisted draft already awaits a distinct user confirmation."""
        payload = getattr(proposal, "payload_json", None) or {}
        change = payload.get("change") or {}
        fields = (change.get("setup_fields") or change.get("strategy_fields")
                  or change.get("bot_fields") or change.get("changed_fields") or {})
        target_type, target_id, target_name = await self._proposal_target(proposal, user_id=user_id)
        subject = str(fields.get("name") or target_name or proposal.asset or proposal.operation_type)
        amount_kind = next((key for key in ("base_amount", "budget_total_eur")
                            if fields.get(key) is not None), None)
        return await self.publish(
            user_id=user_id, event_key=f"proposal:{proposal.id}",
            event_type="proposal_pending", subject_type="proposal",
            subject_id=proposal.id, subject=subject, symbol=proposal.asset,
            priority=5, expires_at=proposal.expires_at,
            evidence={"status": "pending_confirmation", "operation_type": proposal.operation_type,
                      "proposal_id": proposal.id, "payload_hash": proposal.payload_hash,
                      "target_type": target_type, "target_id": target_id,
                      "target_name": target_name,
                      "amount_kind": amount_kind,
                      "amount_eur": fields.get(amount_kind) if amount_kind else None},
            revision=proposal.payload_hash,
        )

    async def publish(self, *, user_id: int, event_key: str, event_type: str,
                      subject_type: str, subject_id: str | None, subject: str,
                      symbol: str | None, evidence: dict, priority: int = 1,
                      source_observed_at: datetime | None = None,
                      expires_at: datetime | None = None,
                      revision: str | None = None) -> str | None:
        """One row per owner/event. Unchanged evidence never reopens or regenerates."""
        if not event_key or event_type not in {"plan_match", "data_blocked", "proposal_pending", "market_move", "bot_decision"}:
            raise ValueError("feed_event_invalid")
        facts = {**evidence, "subject": str(subject or "")[:120]}
        digest = hashlib.sha256(str(revision or _json(facts)).encode()).hexdigest()
        item_id = str(uuid.uuid4())
        # Serialize one owner's logical event, then close an earlier occurrence.
        # A new revision gets a new row so handled items retain their history.
        await self.session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {
            "key": f"finn-feed:{user_id}:{event_key}",
        })
        previous = await self.session.execute(text("""
            SELECT id, fingerprint, status FROM finn_coach_feed_items
            WHERE user_id=:user_id AND event_key=:event_key
            ORDER BY created_at DESC, id DESC LIMIT 1 FOR UPDATE
        """), {"user_id": user_id, "event_key": event_key})
        current = previous.mappings().first()
        if current:
            # A handled, archived or expired observation remains acknowledged.
            # Only changed facts, or a prior condition-cleared transition, reopens it.
            if current["fingerprint"] == digest:
                return None
            if current["status"] in VISIBLE:
                await self.resolve(user_id=user_id, event_key=event_key)
        result = await self.session.execute(text("""
            INSERT INTO finn_coach_feed_items
              (id, user_id, event_key, event_type, subject_type, subject_id, symbol,
               priority, status, fingerprint, evidence, source_observed_at,
               copy_json, expires_at)
            VALUES (CAST(:id AS UUID), :user_id, :event_key, :event_type,
                    :subject_type, :subject_id, :symbol, :priority, 'unread',
                    :fingerprint, CAST(:evidence AS JSONB), :source_observed_at,
                    CAST(:copy_json AS JSONB), :expires_at)
            RETURNING id
        """), {
            "id": item_id, "user_id": user_id, "event_key": event_key,
            "event_type": event_type, "subject_type": subject_type,
            "subject_id": subject_id, "symbol": symbol, "priority": priority,
            "fingerprint": digest, "evidence": _json(facts),
            "source_observed_at": source_observed_at,
            "copy_json": _json(_fallback(event_type, subject, facts)),
            "expires_at": expires_at,
        })
        row = result.first()
        return str(row[0]) if row else None

    async def resolve(self, *, user_id: int, event_key: str) -> None:
        await self.session.execute(text("""
            WITH latest AS (
              SELECT id FROM finn_coach_feed_items
              WHERE user_id=:user_id AND event_key=:event_key
              ORDER BY created_at DESC, id DESC LIMIT 1 FOR UPDATE
            )
            UPDATE finn_coach_feed_items f
            SET status=CASE WHEN f.status IN ('unread','read') THEN 'resolved' ELSE f.status END,
                fingerprint=CONCAT('resolved:', f.fingerprint), updated_at=NOW()
            FROM latest WHERE f.id=latest.id AND f.fingerprint NOT LIKE 'resolved:%'
        """), {"user_id": user_id, "event_key": event_key})

    async def reconcile_score_asset(self, *, user_id: int, symbol: str) -> list[str]:
        """Emit transitions from the same verified assessment as Analyse and FINN."""
        from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
        from backend.services.setup_market_match_service import SetupMarketMatchService
        from backend.utils.scoring_utils import score_source_is_fresh

        asset = str(symbol or "").strip().upper()
        assessment = await SetupMarketMatchService(self.session).for_asset(user_id, asset)
        matches = assessment.get("matches") or []
        existing = await self.session.execute(text("""
            SELECT event_key, subject_id FROM finn_coach_feed_items
            WHERE user_id=:user_id AND symbol=:symbol AND event_type='plan_match'
              AND status IN ('unread','read')
        """), {"user_id": user_id, "symbol": asset})
        active_ids = {str(match["setup_id"]) for match in matches}
        for row in existing.mappings().all():
            if str(row["subject_id"]) not in active_ids:
                await self.resolve(user_id=user_id, event_key=row["event_key"])
        created: list[str] = []
        if not matches:
            await self.resolve(user_id=user_id, event_key=f"score-blocked:{asset}")
            await self.resolve(user_id=user_id, event_key=f"market-move:{asset}")
            return created
        status = assessment.get("source_status")
        moments = assessment.get("component_source_observed_at") or {}
        # A positive match is a dated observation, not an evergreen signal.
        # The next completed score run can create a new revision; without one,
        # the active feed stops displaying the match after an hour.
        positive_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        if status != "available":
            item = await self.publish(
                user_id=user_id, event_key=f"score-blocked:{asset}",
                event_type="data_blocked", subject_type="asset", subject_id=asset,
                subject=asset, symbol=asset, priority=4,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                evidence={"status": status,
                          "component_source_status": assessment.get("component_source_status"),
                          "source_observed_at": moments,
                          "setup_ids": [str(match["setup_id"]) for match in matches]},
                revision=_json({"status": status,
                                "components": assessment.get("component_source_status"),
                                "setup_ids": [str(match["setup_id"]) for match in matches]}),
            )
            if item:
                created.append(item)
        else:
            await self.resolve(user_id=user_id, event_key=f"score-blocked:{asset}")
        for match in matches:
            key = f"plan-match:{match['setup_id']}"
            if status != "available" or match.get("status") != "matches":
                await self.resolve(user_id=user_id, event_key=key)
                continue
            item = await self.publish(
                user_id=user_id, event_key=key, event_type="plan_match",
                subject_type="setup", subject_id=str(match["setup_id"]),
                subject=match.get("name") or asset, symbol=asset, priority=3,
                expires_at=positive_expiry,
                evidence={"status": "matches", "match_status": match["status"],
                          "setup_id": match["setup_id"], "conditions": match.get("conditions"),
                          "components": match.get("components"),
                          "benchmark_score": assessment.get("benchmark_score"),
                          "score_as_of": assessment.get("as_of"),
                          "source_observed_at": moments},
                revision=_json({"status": "matches", "setup_id": match["setup_id"],
                                "name": match.get("name"), "conditions": match.get("conditions"),
                                "components": match.get("components"),
                                "benchmark_score": assessment.get("benchmark_score")}),
            )
            if item:
                created.append(item)
        # A market move is informational and tied to at least one owned plan.
        # It is never interpreted as a plan condition or order eligibility.
        snapshot = await MarketDataRepository(self.session).get_latest_snapshot(asset)
        changed = float(snapshot.change_24h) if snapshot and snapshot.change_24h is not None else None
        observed = getattr(snapshot, "source_observed_at", None) if snapshot else None
        if (changed is not None and abs(changed) >= 10
                and score_source_is_fresh("market", "price", observed, symbol=asset)):
            item = await self.publish(
                user_id=user_id, event_key=f"market-move:{asset}", event_type="market_move",
                subject_type="asset", subject_id=asset, subject=asset, symbol=asset,
                priority=1, source_observed_at=observed,
                expires_at=positive_expiry,
                evidence={"status": "measured_move", "change_24h": changed,
                          "source_observed_at": observed, "setup_ids": [str(m["setup_id"]) for m in matches]},
                revision=_json({"direction": "up" if changed > 0 else "down",
                                "band": int(abs(changed) // 5),
                                "plans": [(str(m["setup_id"]), m.get("name")) for m in matches]}),
            )
            if item:
                created.append(item)
        else:
            await self.resolve(user_id=user_id, event_key=f"market-move:{asset}")
        return created

    async def list(self, *, user_id: int, locale: str = "nl", history: bool = False,
                   limit: int = 50) -> list[dict]:
        result = await self.session.execute(text("""
            SELECT id, event_key, event_type, subject_type, subject_id, symbol, fingerprint,
                   priority, CASE WHEN expires_at <= NOW() OR
                     (event_type='proposal_pending' AND NOT EXISTS (
                       SELECT 1 FROM finn_v2_proposals p
                       WHERE p.id=finn_coach_feed_items.subject_id
                         AND p.user_id=:user_id
                         AND p.status IN ('draft','pending_confirmation')
                         AND p.expires_at > NOW()))
                     THEN 'resolved' ELSE status END AS status,
                   evidence, source_observed_at, copy_json,
                   copy_source, expires_at, created_at, updated_at
            FROM finn_coach_feed_items
            WHERE user_id=:user_id
              AND (:history OR status IN ('unread','read'))
              AND (:history OR expires_at IS NULL OR expires_at > NOW())
              AND (:history OR event_type <> 'proposal_pending' OR EXISTS (
                    SELECT 1 FROM finn_v2_proposals p
                    WHERE p.id=finn_coach_feed_items.subject_id
                      AND p.user_id=:user_id AND p.status IN ('draft','pending_confirmation')
                      AND p.expires_at > NOW()))
            ORDER BY priority DESC, updated_at DESC LIMIT :limit
        """), {"user_id": user_id, "history": history, "limit": min(max(limit, 1), 100)})
        return [self._serialize(dict(row), locale) for row in result.mappings().all()]

    async def detail(self, *, user_id: int, item_id: str, locale: str = "nl",
                     include_internal: bool = False) -> dict | None:
        try:
            uuid.UUID(item_id)
        except (ValueError, TypeError):
            return None
        result = await self.session.execute(text("""
            SELECT id, event_key, event_type, subject_type, subject_id, symbol, fingerprint,
                   priority, CASE WHEN expires_at <= NOW() OR
                     (event_type='proposal_pending' AND NOT EXISTS (
                       SELECT 1 FROM finn_v2_proposals p
                       WHERE p.id=finn_coach_feed_items.subject_id
                         AND p.user_id=:user_id
                         AND p.status IN ('draft','pending_confirmation')
                         AND p.expires_at > NOW()))
                     THEN 'resolved' ELSE status END AS status,
                   evidence, source_observed_at, copy_json,
                   copy_source, expires_at, created_at, updated_at
            FROM finn_coach_feed_items WHERE id=CAST(:id AS UUID) AND user_id=:user_id
        """), {"id": item_id, "user_id": user_id})
        row = result.mappings().first()
        item = self._serialize(dict(row), locale) if row else None
        if item and include_internal:
            item["fingerprint"] = row["fingerprint"]
            item["copy_source"] = row["copy_source"]
        return item

    async def set_status(self, *, user_id: int, item_id: str, status: str) -> bool:
        if status not in {"read", "handled", "archived"}:
            raise ValueError("feed_status_invalid")
        try:
            uuid.UUID(item_id)
        except (ValueError, TypeError):
            return False
        result = await self.session.execute(text("""
            UPDATE finn_coach_feed_items SET status=:status, updated_at=NOW()
            WHERE id=CAST(:id AS UUID) AND user_id=:user_id
              AND status IN ('unread','read')
              AND (expires_at IS NULL OR expires_at > NOW())
              AND (event_type <> 'proposal_pending' OR EXISTS (
                SELECT 1 FROM finn_v2_proposals p
                WHERE p.id=finn_coach_feed_items.subject_id
                  AND p.user_id=:user_id
                  AND p.status IN ('draft','pending_confirmation')
                  AND p.expires_at > NOW()))
            RETURNING id
        """), {"id": item_id, "user_id": user_id, "status": status})
        return result.first() is not None

    @staticmethod
    def _serialize(row: dict, locale: str) -> dict:
        copy = row.pop("copy_json") or {}
        row.pop("fingerprint", None)
        row.pop("copy_source", None)
        if isinstance(copy, str):
            copy = json.loads(copy)
        row["id"] = str(row["id"])
        row["locale"] = locale if locale in LOCALES else "nl"
        row["title"] = (copy.get(row["locale"]) or copy.get("nl") or {}).get("title", "")
        row["description"] = (copy.get(row["locale"]) or copy.get("nl") or {}).get("body", "")
        for key in ("created_at", "updated_at", "source_observed_at", "expires_at"):
            if row.get(key) is not None:
                row[key] = row[key].isoformat()
        return row

    async def generate_copy(self, *, user_id: int, item_id: str) -> bool:
        """One asynchronous Luna/Responses call for one persisted revision."""
        item = await self.detail(user_id=user_id, item_id=item_id, include_internal=True)
        if not item or item["copy_source"] != "fact_fallback" or item["status"] == "resolved":
            return False
        claimed = await self.session.execute(text("""
            UPDATE finn_coach_feed_items SET copy_attempts=copy_attempts+1,
                copy_last_attempt_at=NOW()
            WHERE id=CAST(:id AS UUID) AND user_id=:user_id
              AND copy_source='fact_fallback' AND copy_attempts < 3
              AND (copy_last_attempt_at IS NULL OR copy_last_attempt_at < NOW() - INTERVAL '10 minutes')
            RETURNING id
        """), {"id": item_id, "user_id": user_id})
        if claimed.first() is None:
            return False
        await self.session.commit()
        subject = str((item["evidence"] or {}).get("subject") or "")
        # Luna writes a short personal lead in three languages. Exact facts,
        # amounts and the action boundary remain server-rendered and verified.
        schema = StructuredOutputSpec(name="finn_coach_feed_copy", schema={
            "type": "object", "additionalProperties": False,
            "properties": {
                "focus": {"type": "string", "enum": ["brief", "context"]},
                "lead_nl": {"type": "string"},
                "lead_en": {"type": "string"},
                "lead_de": {"type": "string"},
            },
            "required": ["focus", "lead_nl", "lead_en", "lead_de"],
        })
        result = await ask_gpt_structured_response_async(
            prompt=_json({"type": item["event_type"], "subject": subject,
                          "subject_type": item["subject_type"],
                          "status": (item["evidence"] or {}).get("status"),
                          "match_status": (item["evidence"] or {}).get("match_status"),
                          "score_conditions": (item["evidence"] or {}).get("conditions"),
                          "benchmark_score": (item["evidence"] or {}).get("benchmark_score"),
                          "amount_kind": (item["evidence"] or {}).get("amount_kind"),
                          "amount_eur": (item["evidence"] or {}).get("amount_eur"),
                          "change_24h": (item["evidence"] or {}).get("change_24h"),
                          "source_observed_at": item.get("source_observed_at")}),
            system_role=(
                "You are FINN writing one short personal feed lead in Dutch, English and German "
                "about a verified event. Use the exact subject supplied in the prompt. "
                "Only these sentence forms are valid, with SUBJECT replaced by that exact subject: "
                "NL 'Er is een update over SUBJECT.' or 'Jouw plan SUBJECT heeft een update.'; "
                "EN 'There is an update about SUBJECT.' or 'Your plan SUBJECT has an update.'; "
                "DE 'Es gibt ein Update zu SUBJECT.' or 'Dein Plan SUBJECT hat ein Update.'. "
                "The server adds verified facts and action context. Choose context when useful, otherwise brief."
            ),
            output_spec=schema, model_override="gpt-6-luna", reasoning_effort="none",
            timeout_seconds=15, max_output_tokens=220, client_max_retries=0,
        )
        if not isinstance(result, dict) or result.get("error"):
            return False
        parsed = result.get("parsed") or {}
        focus = parsed.get("focus")
        if focus not in {"brief", "context"}:
            return False
        copy = _fallback(item["event_type"], subject, item["evidence"], focus=focus)
        for locale in LOCALES:
            lead = _verified_lead(parsed.get(f"lead_{locale}"), subject, locale)
            if lead is None:
                return False
            copy[locale]["body"] = f"{lead} {copy[locale]['body']}"
        await self.session.execute(text("""
            UPDATE finn_coach_feed_items SET copy_json=CAST(:copy AS JSONB),
                copy_source='luna_responses', updated_at=NOW()
            WHERE id=CAST(:id AS UUID) AND user_id=:user_id
              AND fingerprint=:fingerprint AND copy_source='fact_fallback'
        """), {"id": item_id, "user_id": user_id,
            "fingerprint": item["fingerprint"],
               "copy": _json(copy)})
        return True
