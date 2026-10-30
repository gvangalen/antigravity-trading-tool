import logging
import os
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

# Lock to ensure only 1 Playwright render happens concurrently to save RAM
_render_lock = asyncio.Lock()

# Constants
DEFAULT_TIMEOUT_MS = 60000


def _frontend_base_url() -> str:
    # Use the same deployed frontend origin as the other PDF/report paths.
    # FRONTEND_BASE_URL remains an explicit override for local render jobs.
    configured = os.getenv("FRONTEND_BASE_URL") or os.getenv("FRONTEND_URL")
    return (configured or "http://localhost:3000").split(",", 1)[0].strip().rstrip("/")

async def render_report_pdf_via_playwright(token: str) -> bytes:
    """
    Render report PDF via frontend print route.
    Token komt uit report_snapshots tabel.
    """

    url = f"{_frontend_base_url()}/print/daily?token={token}"
    
    logger.info("🧾 Playwright PDF render starting | Token: %s", token[:8] + "...")

    async with _render_lock:
        logger.info("🔒 Playwright lock acquired for Token: %s", token[:8] + "...")
        try:
            async with async_playwright() as p:

                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--js-flags=--max-old-space-size=512",
                    ],
                )

                try:
                    context = await browser.new_context(
                        viewport={"width": 1280, "height": 900},
                        device_scale_factor=2,
                    )

                    page = await context.new_page()

                    await page.goto(
                        url,
                        wait_until="networkidle",
                        timeout=DEFAULT_TIMEOUT_MS,
                    )

                    # wacht tot print klaar (attached ipv visible omdat hij hidden is)
                    await page.wait_for_selector(
                        "#print-ready",
                        state="attached",
                        timeout=DEFAULT_TIMEOUT_MS,
                    )

                    await page.wait_for_timeout(500)

                    pdf_bytes = await page.pdf(
                        format="A4",
                        print_background=True,
                        prefer_css_page_size=True,
                        margin={
                            "top": "12mm",
                            "right": "12mm",
                            "bottom": "12mm",
                            "left": "12mm",
                        },
                    )

                    logger.info("✅ PDF render OK (%d bytes)", len(pdf_bytes))
                    return pdf_bytes

                finally:
                    await browser.close()

        except PlaywrightTimeout:
            logger.error("❌ PDF render timeout — print marker (#print-ready) niet gevonden binnen 60s")
            raise Exception("PDF render timeout — print marker (#print-ready) ontbreekt")

        except Exception as e:
            logger.exception("❌ Playwright crash")
            raise Exception(f"PDF render error: {str(e)}")
