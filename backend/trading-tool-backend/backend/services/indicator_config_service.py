from backend.infrastructure.repositories.indicator_config_repository import IndicatorConfigRepository
from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository
from backend.schemas.indicator_config_schema import IndicatorConfigResponse, IndicatorBucketRule

FIXED_BUCKETS = [
    (0.0, 20.0),
    (20.0, 40.0),
    (40.0, 60.0),
    (60.0, 80.0),
    (80.0, 100.0),
]

def _clamp_weight(w) -> float:
    try:
        v = float(w)
    except Exception:
        v = 1.0
    return max(0.0, min(3.0, v))

def _clamp_score(s) -> int:
    try:
        v = int(float(s))
    except Exception:
        v = 50
    return max(10, min(100, v))

def _bucket_key(a: float, b: float):
    return (round(float(a), 4), round(float(b), 4))

class IndicatorConfigService:
    def __init__(self, repository: IndicatorConfigRepository):
        self.repository = repository
        self.product_repository = TechnicalDataRepository(repository.db)

    @staticmethod
    def _rule_value(rule, name, default=None):
        if isinstance(rule, dict):
            return rule.get(name, default)
        return getattr(rule, name, default)

    def _rules_to_fixed_buckets(self, rules_objects):
        active = [
            rule
            for rule in rules_objects
            if self._rule_value(rule, "is_active", True) is not False
        ]

        by_bucket = {}
        for rule in active:
            k = _bucket_key(
                self._rule_value(rule, "range_min"),
                self._rule_value(rule, "range_max"),
            )
            if k not in by_bucket:
                by_bucket[k] = rule

        out = []
        for (bmin, bmax) in FIXED_BUCKETS:
            k = _bucket_key(bmin, bmax)
            if k in by_bucket:
                rule = by_bucket[k]
                out.append(IndicatorBucketRule(
                    range_min=float(bmin),
                    range_max=float(bmax),
                    score=_clamp_score(self._rule_value(rule, "score")),
                    trend=self._rule_value(rule, "trend"),
                    interpretation=self._rule_value(rule, "interpretation"),
                    action=self._rule_value(rule, "action"),
                ))
            else:
                out.append(IndicatorBucketRule(
                    range_min=float(bmin),
                    range_max=float(bmax),
                    score=50,
                    trend=None,
                    interpretation="Bucket ontbreekt in DB (fallback).",
                    action="Geen actie."
                ))
        return out

    async def get_indicator_config(self, category: str, indicator: str, user_id: int, symbol: str) -> IndicatorConfigResponse:
        rules_objs = await self.repository.get_system_indicator_rules(category, indicator)
        configured = await self.product_repository.get_user_configs(user_id, category, symbol=symbol)
        row = next((item for item in configured if item.indicator == indicator), None)
        metadata = dict(getattr(row, "config_json", {}) or {})
        score_mode = str(metadata.get("score_mode") or "standard").strip().lower()
        weight = _clamp_weight(metadata.get("weight", getattr(row, "priority", 100) / 100 if row else 1.0))
        # A personal canonical configuration remains readable even when the
        # optional system bucket template has not been seeded yet.
        rules = self._rules_to_fixed_buckets(metadata.get("rules") or rules_objs)
        
        return IndicatorConfigResponse(
            indicator=indicator,
            category=category,
            score_mode=score_mode.strip().lower(),
            weight=weight,
            rules=rules
        )

    async def update_indicator_settings(self, category: str, indicator: str, user_id: int, symbol: str, score_mode: str, weight: float):
        score_mode = (score_mode or "").strip().lower()
        weight = _clamp_weight(weight)
        
        await self.product_repository.set_indicator_config_metadata(
            user_id,
            indicator,
            category,
            symbol=symbol,
            config_json={"score_mode": score_mode, "weight": weight},
        )
        await self.repository.db.commit()

    async def save_custom_rules(self, category: str, indicator: str, user_id: int, symbol: str, rules: list, weight: float):
        weight = _clamp_weight(weight)
        if len(rules) != 5:
            raise ValueError("Exact 5 buckets verplicht")
            
        rules_to_insert = []
        for idx, (bmin, bmax) in enumerate(FIXED_BUCKETS):
            r = rules[idx]
            rules_to_insert.append({
                "range_min": bmin,
                "range_max": bmax,
                "score": r.get('score', 50) if isinstance(r, dict) else getattr(r, 'score', 50),
                "trend": r.get('trend') if isinstance(r, dict) else getattr(r, 'trend', None),
                "interpretation": r.get('interpretation') if isinstance(r, dict) else getattr(r, 'interpretation', None),
                "action": r.get('action') if isinstance(r, dict) else getattr(r, 'action', None)
            })
            
        await self.product_repository.set_indicator_config_metadata(
            user_id,
            indicator,
            category,
            symbol=symbol,
            config_json={"score_mode": "custom", "weight": weight, "rules": rules_to_insert},
        )
        await self.repository.db.commit()

    async def reset_indicator_rules(self, category: str, indicator: str, user_id: int, symbol: str):
        await self.product_repository.set_indicator_config_metadata(
            user_id,
            indicator,
            category,
            symbol=symbol,
            config_json={},
        )
        await self.repository.db.commit()
