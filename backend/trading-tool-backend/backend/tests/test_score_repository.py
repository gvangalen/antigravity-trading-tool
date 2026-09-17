import asyncio

from backend.infrastructure.repositories.score_repository import ScoreRepository


def test_fetch_active_setups_casts_json_breakdown_before_coalesce():
    import inspect

    source = inspect.getsource(ScoreRepository.fetch_active_setups)

    assert "ds.breakdown::jsonb" in source
    assert "'{}'::jsonb" in source


class _Mappings:
    def mappings(self):
        return []


class _Session:
    def __init__(self):
        self.statement = ""

    async def execute(self, statement, _params):
        self.statement = str(statement)
        return _Mappings()


def test_active_setup_score_casts_legacy_json_breakdown_to_jsonb():
    session = _Session()

    assert asyncio.run(ScoreRepository(session).fetch_active_setups(7)) == []
    assert "COALESCE(ds.breakdown::jsonb, '{}'::jsonb)" in session.statement
