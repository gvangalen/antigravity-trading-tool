import os


LEGACY_PERIODIC_AI_ENV = "ENABLE_LEGACY_PERIODIC_AI"


def legacy_periodic_ai_enabled() -> bool:
    """Keep legacy scheduled AI disabled unless operations explicitly opts in."""
    return str(os.getenv(LEGACY_PERIODIC_AI_ENV, "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
