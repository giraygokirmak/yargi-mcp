# anayasa_mcp_module/client.py
# Norm Denetimi client — rewritten for the new (Sept 2024+) React SPA at
# https://normkararlarbilgibankasi.anayasa.gov.tr/kbb/
#
# The old form-based endpoint `/Ara` is gone. The site now exposes a public JSON
# API under /api/core/public/* that we drive directly:
#   POST /api/core/public/search                    -> decision list
#   GET  /api/core/public/merge-html/{id}           -> full decision HTML
#   GET  /api/core/public/download-decision         -> pdf/docx (requires captcha token)

import html
import logging
import math
import os
import tempfile
import asyncio
from typing import List, Optional

import httpx
from markitdown import MarkItDown

from .models import (
    AnayasaNormDenetimiSearchRequest,
    AnayasaDecisionSummary,
    AnayasaSearchResult,
    AnayasaDocumentMarkdown,
)

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class AnayasaMahkemesiApiClient:
    BASE_URL = "https://normkararlarbilgibankasi.anayasa.gov.tr"
    API_SEARCH = "/api/core/public/search"
    API_MERGE_HTML = "/api/core/public/merge-html/{id}"
    DECISION_TYPE = "NormDenetimi"
    DOCUMENT_MARKDOWN_CHUNK_SIZE = 5000

    def __init__(self, request_timeout: float = 60.0):
        self.http_client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Accept": "application/json, text/html, */*",
                "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
            },
            timeout=request_timeout,
            verify=True,
            follow_redirects=True,
        )

    # ---------- Search ----------

    def _build_search_payload(self, params: AnayasaNormDenetimiSearchRequest) -> dict:
        """Maps the MCP-facing search request onto the KBB JSON API payload.

        The new API accepts a single free-text ``query`` plus a type filter
        (``kararTipi``). The old structured filters (başvuran, raportör, norm
        türü, ...) are not part of the public schema yet, so we degrade them to
        plain free-text keywords to keep the tool useful.
        """
        queries: List[str] = []
        queries.extend(k for k in (params.keywords_all or []) if k)
        queries.extend(k for k in (params.keywords_any or []) if k)
        if params.case_number_esas:
            queries.append(params.case_number_esas)
        if params.decision_number_karar:
            queries.append(params.decision_number_karar)
        query_text = " ".join(q.strip() for q in queries if q and q.strip())

        size = params.results_per_page or 10
        return {
            "query": query_text,
            "kararTipi": self.DECISION_TYPE,
            "page": max(1, params.page_to_fetch or 1),
            "size": max(1, min(size, 50)),
        }

    async def search_norm_denetimi_decisions(
        self, params: AnayasaNormDenetimiSearchRequest
    ) -> AnayasaSearchResult:
        payload = self._build_search_payload(params)
        logger.info(f"AnayasaNormDenetimi: POST {self.API_SEARCH} payload={payload}")

        try:
            resp = await self.http_client.post(self.API_SEARCH, json=payload)
            resp.raise_for_status()
        except httpx.RequestError as e:
            logger.error(f"AnayasaNormDenetimi: search request error: {e}")
            raise

        body = resp.json() or {}
        raw = body.get("data") or []
        total = body.get("total", len(raw))
        page = body.get("page", payload["page"])

        decisions: List[AnayasaDecisionSummary] = []
        for d in raw:
            if d.get("kararTipi") not in (None, self.DECISION_TYPE):
                continue
            esas_no = d.get("esasNo") or ""
            karar_no = d.get("kararNo") or ""
            ref = f"E.{esas_no}, K.{karar_no}" if esas_no or karar_no else d.get("id")
            decisions.append(
                AnayasaDecisionSummary(
                    decision_reference_no=ref,
                    decision_page_url=d.get("id"),  # resolve with get_decision_document_as_markdown(id)
                    application_type_summary=d.get("basvuruTuru"),
                    applicant_summary=d.get("basvuranOzel") or d.get("basvuranGenel"),
                    decision_date_summary=d.get("kararTarihi"),
                    decision_outcome_summary=d.get("kararTuruDosyaSonucuLabel")
                    or d.get("kararTuruDosyaSonucu"),
                )
            )

        return AnayasaSearchResult(
            decisions=decisions,
            total_records_found=total,
            retrieved_page_number=page,
        )

    # ---------- Document ----------

    async def _fetch_decision_html(self, decision_id: str) -> str:
        """Fetches the rendered HTML body of a decision via merge-html."""
        url = self.API_MERGE_HTML.format(id=decision_id)
        resp = await self.http_client.get(url, headers={"Accept": "text/html"})
        resp.raise_for_status()
        text = resp.text or ""
        if "<body></body>" in text and len(text) < 200:
            raise ValueError(f"Empty decision HTML for id={decision_id}")
        return text

    def _convert_html_to_markdown(self, html_content: str) -> Optional[str]:
        if not html_content:
            return None
        processed = html.unescape(html_content)
        temp_path = None
        try:
            md = MarkItDown(enable_plugins=False)
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".html", encoding="utf-8") as tmp:
                tmp.write(processed)
                temp_path = tmp.name
            return md.convert(temp_path).text_content
        except Exception as e:
            logger.error(f"AnayasaNormDenetimi: HTML->markdown error: {e}")
            return None
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    async def _convert_html_async(self, html_content: str) -> Optional[str]:
        return await asyncio.to_thread(self._convert_html_to_markdown, html_content)

    async def get_decision_document_as_markdown(
        self, document_url: str, page_number: int = 1
    ) -> AnayasaDocumentMarkdown:
        """
        Retrieves a Norm Denetimi decision as paginated markdown.

        ``document_url`` accepts either a bare decision id (preferred, from
        ``search_norm_denetimi_decisions``) or a full URL containing the ``id=``
        query param, which the SPA produces.
        """
        decision_id = document_url
        if "id=" in document_url:
            # accept SPA URLs of the form .../kbb/pages/search/NormDenetimi?id=<id>&type=...
            import re

            m = re.search(r"[?&]id=([A-Za-z0-9\-]+)", document_url)
            if m:
                decision_id = m.group(1)
        # Old MCP clients pass paths like /ND/2024/123 — those are no longer
        # meaningful, instruct the caller to re-search.
        if not decision_id or "/" in decision_id:
            raise ValueError(
                "AYM artık eski /ND/… URL'lerini desteklemiyor. "
                "search_anayasa_norm_denetimi_decisions çıktısındaki 'decision_page_url' (id) kullanın."
            )

        html_content = await self._fetch_decision_html(decision_id)
        full_md = await self._convert_html_async(html_content) or ""
        source_url = f"{self.BASE_URL}{self.API_MERGE_HTML.format(id=decision_id)}"

        # Paginate the markdown so an MCP tool can safely return it.
        total = len(full_md)
        chunk = self.DOCUMENT_MARKDOWN_CHUNK_SIZE
        total_pages = max(1, math.ceil(total / chunk))
        current = max(1, min(page_number, total_pages))
        start = (current - 1) * chunk
        chunk_text = full_md[start : start + chunk]

        return AnayasaDocumentMarkdown(
            source_url=source_url,
            decision_reference_no_from_page=None,
            decision_date_from_page=None,
            official_gazette_info_from_page=None,
            markdown_chunk=chunk_text,
            current_page=current,
            total_pages=total_pages,
            is_paginated=total_pages > 1,
        )

    async def close_client_session(self):
        if self.http_client and not self.http_client.is_closed:
            await self.http_client.aclose()
