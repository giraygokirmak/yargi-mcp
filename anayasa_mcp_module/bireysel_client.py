# anayasa_mcp_module/bireysel_client.py
# Bireysel Başvuru client — rewritten for the new React SPA at
# https://kararlarbilgibankasi.anayasa.gov.tr/kbb/
#
# The old form-based `/Ara?KararBulteni=1` report is gone. The site now serves a
# public JSON API (same shape as the norm-denetimi site):
#   POST /api/core/public/search                       -> search results
#   GET  /api/core/public/kararlar/{id}/dosyalar       -> list of attachments (UDF)
#   GET  /api/core/public/files/download-attachment/…  -> the UDF file (a DOCX zip)

import html
import logging
import math
import os
import tempfile
from typing import List, Optional
from urllib.parse import quote

import httpx
from markitdown import MarkItDown

from .models import (
    AnayasaBireyselReportSearchRequest,
    AnayasaBireyselReportDecisionSummary,
    AnayasaBireyselReportSearchResult,
    AnayasaBireyselBasvuruDocumentMarkdown,
)

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class AnayasaBireyselBasvuruApiClient:
    BASE_URL = "https://kararlarbilgibankasi.anayasa.gov.tr"
    API_SEARCH = "/api/core/public/search"
    API_DOSYALAR = "/api/core/public/kararlar/{id}/dosyalar"
    API_ATTACHMENT = "/api/core/public/files/download-attachment/{folder}/{filename}"
    DECISION_TYPE = "BireyselBasvuru"
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

    def _build_payload(self, params: AnayasaBireyselReportSearchRequest) -> dict:
        keywords = [k.strip() for k in (params.keywords or []) if k and k.strip()]
        return {
            "query": " ".join(keywords),
            "kararTipi": self.DECISION_TYPE,
            "page": max(1, params.page_to_fetch or 1),
            "size": 10,
        }

    async def search_bireysel_basvuru_report(
        self, params: AnayasaBireyselReportSearchRequest
    ) -> AnayasaBireyselReportSearchResult:
        payload = self._build_payload(params)
        logger.info(f"AnayasaBireysel: POST {self.API_SEARCH} payload={payload}")

        try:
            resp = await self.http_client.post(self.API_SEARCH, json=payload)
            resp.raise_for_status()
        except httpx.RequestError as e:
            logger.error(f"AnayasaBireysel: search request error: {e}")
            raise

        body = resp.json() or {}
        raw = body.get("data") or []
        total = body.get("total", len(raw))
        page = body.get("page", payload["page"])

        decisions: List[AnayasaBireyselReportDecisionSummary] = []
        for d in raw:
            if d.get("kararTipi") not in (None, self.DECISION_TYPE):
                continue
            decisions.append(
                AnayasaBireyselReportDecisionSummary(
                    title=d.get("basvuruAdi"),
                    decision_reference_no=d.get("basvuruNo"),
                    # The SPA route requires the decision id; consumers pass this to
                    # get_anayasa_bireysel_basvuru_document_markdown.
                    decision_page_url=d.get("id"),
                    decision_type_summary=d.get("kararTuruDosyaSonucuLabel") or d.get("kararTuruDosyaSonucu"),
                    decision_making_body=d.get("karariVerenBirim"),
                    application_date_summary=d.get("basvuruTarihi"),
                    decision_date_summary=d.get("kararTarihi"),
                    application_subject_summary=d.get("kararKonusu"),
                )
            )

        return AnayasaBireyselReportSearchResult(
            decisions=decisions,
            total_records_found=total,
            retrieved_page_number=page,
        )

    # ---------- Document ----------

    async def _fetch_decision_udf_url(self, decision_id: str) -> Optional[str]:
        url = self.API_DOSYALAR.format(id=decision_id)
        resp = await self.http_client.get(url, params={"kararTipi": self.DECISION_TYPE})
        resp.raise_for_status()
        items = (resp.json() or {}).get("data") or []
        for it in items:
            href = it.get("url") or ""
            if href.lower().endswith(".udf"):
                return href
        # fallback: return whatever file exists
        return items[0]["url"] if items else None

    async def _download_attachment(self, relative_url: str) -> bytes:
        """``relative_url`` looks like ``/files/<folder>/<filename>.udf``."""
        parts = relative_url.lstrip("/").split("/", 2)
        if len(parts) < 3:
            raise ValueError(f"Unexpected UDF url: {relative_url}")
        folder, filename = parts[1], parts[2]
        url = self.API_ATTACHMENT.format(folder=quote(folder, safe=""), filename=quote(filename, safe=""))
        resp = await self.http_client.get(url)
        resp.raise_for_status()
        return resp.content

    def _convert_udf_to_markdown(self, udf_bytes: bytes) -> Optional[str]:
        """UDF files are zip archives; most UYAP/AYM UDFs store the decision body as
        plain text inside ``content.xml``. We try a direct plain-text extraction
        first (cheap & robust), and fall back to MarkItDown-on-docx only if that
        yields nothing.
        """
        import re
        import zipfile
        import io

        if not udf_bytes:
            return None

        # --- fast path: extract CDATA/plain text from content.xml ---
        try:
            zf = zipfile.ZipFile(io.BytesIO(udf_bytes))
            if "content.xml" in zf.namelist():
                raw = zf.read("content.xml").decode("utf-8", errors="replace")
                # CDATA sections carry the user-visible decision text.
                cdata_parts = re.findall(r"<!\[CDATA\[(.*?)\]\]>", raw, flags=re.S)
                if cdata_parts:
                    raw = "\n\n".join(cdata_parts)
                else:
                    raw = re.sub(r"<[^>]+>", " ", raw)  # generic XML strip fallback
                text = re.sub(r"[ \t]+", " ", raw)
                text = re.sub(r"\n{3,}", "\n\n", text)
                text = text.strip()
                if len(text) > 50:
                    return text
        except (zipfile.BadZipFile, KeyError, UnicodeDecodeError):
            pass

        # --- fallback: DOCX interpretation via MarkItDown ---
        try:
            md = MarkItDown(enable_plugins=False)
            with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".docx") as tmp:
                tmp.write(udf_bytes)
                temp_path = tmp.name
            try:
                return md.convert(temp_path).text_content
            finally:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
        except Exception as e:
            logger.error(f"AnayasaBireysel: UDF->markdown fallback error: {e}")
            return None

    def _convert_bytes_to_markdown(self, blob: bytes, suffix: str) -> Optional[str]:
        """Use MarkItDown for real binary documents (pdf/docx/html). Kept for
        backwards compat; PDF output type is not exposed upstream yet."""
        if not blob:
            return None
        temp_path = None
        try:
            md = MarkItDown(enable_plugins=False)
            with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=suffix) as tmp:
                tmp.write(blob)
                temp_path = tmp.name
            return md.convert(temp_path).text_content
        except Exception as e:
            logger.error(f"AnayasaBireysel: bytes->markdown error: {e}")
            return None
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    async def get_decision_document_as_markdown(
        self, document_url_path: str, page_number: int = 1
    ) -> AnayasaBireyselBasvuruDocumentMarkdown:
        """
        Retrieves a Bireysel Başvuru decision as paginated markdown.

        ``document_url_path`` may be a bare decision id (preferred, taken from
        ``search_bireysel_basvuru_report`` output) or a URL/path containing
        ``id=<uuid>``. The old ``/BB/YYYY/NNN`` paths are no longer meaningful
        upstream.
        """
        import re

        decision_id = document_url_path
        m = re.search(r"[?&]id=([A-Za-z0-9\-]{20,})", document_url_path or "")
        if m:
            decision_id = m.group(1)
        if not decision_id or "/" in decision_id:
            raise ValueError(
                "AYM artık eski /BB/… yollarını desteklemiyor. "
                "search_anayasa_bireysel_basvuru_report çıktısındaki 'decision_page_url' (id) kullanın."
            )

        udf_url = await self._fetch_decision_udf_url(decision_id)
        if not udf_url:
            raise ValueError(f"Bireysel başvuru kararı için dosya bulunamadı (id={decision_id}).")

        blob = await self._download_attachment(udf_url)
        full_md = self._convert_udf_to_markdown(blob) or ""

        total = len(full_md)
        chunk = self.DOCUMENT_MARKDOWN_CHUNK_SIZE
        total_pages = max(1, math.ceil(total / chunk))
        current = max(1, min(page_number, total_pages))
        start = (current - 1) * chunk

        return AnayasaBireyselBasvuruDocumentMarkdown(
            source_url=f"{self.BASE_URL}{udf_url}",
            markdown_chunk=full_md[start : start + chunk],
            current_page=current,
            total_pages=total_pages,
            is_paginated=total_pages > 1,
        )

    async def close_client_session(self):
        if self.http_client and not self.http_client.is_closed:
            await self.http_client.aclose()
