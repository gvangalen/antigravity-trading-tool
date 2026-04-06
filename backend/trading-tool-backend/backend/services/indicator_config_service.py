from backend.infrastructure.repositories.indicator_config_repository import IndicatorConfigRepository
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

    def _rules_to_fixed_buckets(self, rules_objects):
        active = [r for r in rules_objects if getattr(r, 'is_active', True) is not False]

        by_bucket = {}
        for r in active:
            k = _bucket_key(r.range_min, r.range_max)
            if k not in by_bucket:
                by_bucket[k] = r

        out = []
        for (bmin, bmax) in FIXED_BUCKETS:
            k = _bucket_key(bmin, bmax)
            if k in by_bucket:
                r = by_bucket[k]
                out.append(IndicatorBucketRule(
                    range_min=float(bmin),
                    range_max=float(bmax),
                    score=_clamp_score(r.score),
                    trend=r.trend,
                    interpretation=r.interpretation,
                    action=r.action,
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

    async def get_indicator_config(self, category: str, indicator: str, user_id: int) -> IndicatorConfigResponse:
        rules_objs, is_override = await self.repository.get_indicator_rules(category, indicator, user_id)
        
        if not rules_objs:
            return IndicatorConfigResponse(
                indicator=indicator,
                category=category,
                score_mode="standard",
                weight=1.0,
                rules=self._rules_to_fixed_buckets([])
            )
            
        first = rules_objs[0]
        score_mode = getattr(first, 'score_mode', "standard") or "standard"
        weight = _clamp_weight(getattr(first, 'weight', 1.0) or 1.0)
        
        rules = self._rules_to_fixed_buckets(rules_objs)
        
        return IndicatorConfigResponse(
            indicator=indicator,
            category=category,
            score_mode=score_mode.strip().lower(),
            weight=weight,
            rules=rules
        )

    async def update_indicator_settings(self, category: str, indicator: str, user_id: int, score_mode: str, weight: float):
        score_mode = (score_mode or "").strip().lower()
        weight = _clamp_weight(weight)
        
        rules_objs, is_override = await self.repository.get_indicator_rules(category, indicator, user_id)
        
        if is_override:
            await self.repository.update_settings(category, indicator, user_id, score_mode, weight)
        else:
            # Kopieer template rules naar user override!
            rules_to_insert = []
            for r in rules_objs:
                rules_to_insert.append({
                    "range_min": r.range_min,
                    "range_max": r.range_max,
                    "score": r.score,
                    "trend": r.trend,
                    "interpretation": r.interpretation,
                    "action": r.action,
                })
            
            if not rules_objs:
                for bmin, bmax in FIXED_BUCKETS:
                    rules_to_insert.append({
                        "range_min": bmin, "range_max": bmax, "score": 50, "trend": None,
                        "interpretation": "Empty", "action": "None"
                    })
                    
            await self.repository.insert_user_rules(category, indicator, user_id, rules_to_insert, score_mode, weight)
            
        await self.repository.db.commit()

    async def save_custom_rules(self, category: str, indicator: str, user_id: int, rules: list, weight: float):
        weight = _clamp_weight(weight)
        if len(rules) != 5:
            raise ValueError("Exact 5 buckets verplicht")
            
        await self.repository.delete_user_rules(category, indicator, user_id)
        
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
            
        await self.repository.insert_user_rules(category, indicator, user_id, rules_to_insert, "custom", weight)
        await self.repository.db.commit()

    async def reset_indicator_rules(self, category: str, indicator: str, user_id: int):
        await self.repository.delete_user_rules(category, indicator, user_id)
        await self.repository.db.commit()
