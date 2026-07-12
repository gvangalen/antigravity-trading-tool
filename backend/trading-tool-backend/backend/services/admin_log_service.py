import logging
import json
from typing import List, Optional, Dict, Any
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.infrastructure.models import SystemLog
from backend.services.ai_usage_observability_service import ai_usage_context
from backend.utils.openai_client import ask_gpt_json_async

logger = logging.getLogger(__name__)

class AdminLogService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_logs(
        self, 
        limit: int = 100, 
        level: Optional[str] = None, 
        source: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Haalt de nieuwste logs op met optionele filters.
        """
        stmt = select(SystemLog).order_by(desc(SystemLog.created_at)).limit(limit)
        
        if level:
            stmt = stmt.where(SystemLog.level == level)
        if source:
            stmt = stmt.where(SystemLog.source == source)
        if search:
            stmt = stmt.where(SystemLog.message.ilike(f"%{search}%"))
            
        result = await self.db.execute(stmt)
        logs = result.scalars().all()
        
        return [
            {
                "id": log.id,
                "level": log.level,
                "message": log.message,
                "source": log.source,
                "endpoint": log.endpoint,
                "user_id": log.user_id,
                "metadata": log.metadata_json,
                "created_at": log.created_at
            }
            for log in logs
        ]

    async def analyze_errors_with_ai(self) -> Dict[str, Any]:
        """
        Haalt de laatste 30 errors op en analyseert ze met AI.
        """
        stmt = select(SystemLog).where(SystemLog.level.in_(['error', 'critical'])).order_by(desc(SystemLog.created_at)).limit(30)
        result = await self.db.execute(stmt)
        error_logs = result.scalars().all()
        
        if not error_logs:
            return {
                "root_cause": "Geen foutmeldingen gevonden om te analyseren.",
                "what_is_broken": "N.v.t.",
                "suggested_fix": "Systeem lijkt gezond.",
                "severity": "low",
                "category": "SYSTEM",
                "action_type": "unknown",
                "affected_system": "none",
                "explanation": "Er zijn momenteel geen fouten in de logs aanwezig."
            }

        # Format logs for AI context
        log_context = []
        for log in error_logs:
            log_context.append({
                "ts": log.created_at.isoformat(),
                "src": log.source,
                "msg": log.message,
                "end": log.endpoint,
                "meta": log.metadata_json
            })

        system_role = (
            "You are an expert system reliability engineer. Analyze the following application logs for Tradamind. "
            "Identify the root cause of recent errors and suggest clear, actionable fixes. "
            "Return a structured JSON report."
        )
        
        prompt = f"""Analyze the following application logs and provide a structured debug report:
        
{json.dumps(log_context, indent=2)}

Guidelines:
- severity: 'low', 'medium', 'high', 'critical'
- category: 'AUTH', 'API', 'DATABASE', 'AI', 'EXTERNAL'
- action_type: 'retry', 'validation_fix', 'schema_fix', 'rate_limit_fix', 'missing_data', 'unknown'
- Return only the JSON object.
"""

        with ai_usage_context(
            user_id=None,
            purpose="admin_log_analysis",
            symbol="GLOBAL",
            request_source="system",
            run_kind="interactive",
            entry_point="admin_log_service:analyze_errors_with_ai",
            completion_status="success",
        ):
            analysis = await ask_gpt_json_async(prompt=prompt, system_role=system_role)
        
        # Ensure it has all required fields for our schema
        return {
            "root_cause": analysis.get("root_cause", "Onbekend"),
            "what_is_broken": analysis.get("what_is_broken", "Systeem vertoont onregelmatige fouten"),
            "suggested_fix": analysis.get("suggested_fix", "Onderzoek de logs handmatig"),
            "severity": analysis.get("severity", "medium"),
            "category": analysis.get("category", "API"),
            "action_type": analysis.get("action_type", "unknown"),
            "affected_system": analysis.get("affected_system", "backend"),
            "explanation": analysis.get("explanation", "Analyse van AI op basis van beschikbare logdata.")
        }
