"""Owner-scoped GET readback for protected trader QA; never return a token to artifacts."""

from __future__ import annotations

from urllib.parse import urlsplit


def read_json(*, owner_id: int, path: str) -> dict:
    """Read one same-origin product GET with a short-lived in-memory owner token."""
    if (not isinstance(owner_id, int) or owner_id <= 0 or not path.startswith("/api/")
            or path.startswith("//") or urlsplit(path).scheme or urlsplit(path).netloc):
        raise RuntimeError("qa_readback_scope_invalid")
    from backend.utils.auth_utils import create_access_token
    import httpx

    token = create_access_token({"sub": str(owner_id), "role": "user"})
    try:
        with httpx.Client(base_url="https://tradamind.com", timeout=20.0,
                          follow_redirects=False) as client:
            response = client.get(path, headers={"authorization": f"Bearer {token}"})
        if response.status_code != 200:
            raise RuntimeError("qa_readback_http_unavailable")
        value = response.json()
        if not isinstance(value, dict):
            raise RuntimeError("qa_readback_shape_invalid")
        return value
    except RuntimeError:
        raise
    except Exception:
        raise RuntimeError("qa_readback_transport_failed") from None
    finally:
        token = None
