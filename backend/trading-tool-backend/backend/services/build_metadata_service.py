import os
from typing import Dict


def build_metadata_snapshot(*, service: str) -> Dict[str, str]:
    return {
        "service": service,
        "commit_sha": os.getenv("TRADAMIND_BUILD_COMMIT_SHA", "unknown"),
        "build_time": os.getenv("TRADAMIND_BUILD_TIME", "unknown"),
    }
