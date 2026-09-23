# uyusmazlik_mcp_module/client.py
#
# Rewritten (Sept 2026): kararlar.uyusmazlik.gov.tr was rebuilt as a classic
# ASP.NET WebForms site. The old JSON endpoint `/Arama/Search` is gone.
# The new flow is:
#   1. GET /                      -> parse __VIEWSTATE/__EVENTVALIDATION and the
#                                  current page of the "GridView1" table.
#   2. POST /  with txtSearch + btnSearch (+ fresh ViewState fields) -> the same
#                                  table filtered by the search term.
#   3. GET Uploads/<YIL-NO>.pdf   -> decision content (PDF only now).
import asyncio
import html
import logging
import os
import re
import tempfile
from typing import List, Optional, Tuple
from urllib.parse import urlencode, urljoin

import httpx
from bs4 import BeautifulSoup
from markitdown import MarkItDown

from .models import (
    UyusmazlikSearchRequest,
    UyusmazlikApiDecisionEntry,
    UyusmazlikSearchResponse,
    UyusmazlikDocumentMarkdown,
)

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class UyusmazlikApiClient:
    """Client for the current kararlar.uyusmazlik.gov.tr (ASP.NET WebForms)."""

    BASE_URL = "https://kararlar.uyusmazlik.gov.tr"
    PAGE_PATH = "/"  # the search + grid live on Default.aspx (root)

    def __init__(self, request_timeout: float = 60.0):
        self.request_timeout = request_timeout

    # ---------- HTTP helpers ----------

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
            },
            timeout=self.request_timeout,
            verify=False,
            follow_redirects=True,
        )

    @staticmethod
    def _hidden_fields(soup: BeautifulSoup) -> dict:
        """Extract ASP.NET ViewState-ish hidden fields so the server accepts our postback."""
        fields = {}
        for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
            tag = soup.find("input", attrs={"name": name})
            if tag and tag.get("value"):
                fields[name] = tag["value"]
        return fields

    # ---------- Search ----------

    async def search_decisions(self, params: UyusmazlikSearchRequest) -> UyusmazlikSearchResponse:
        """
        Searches Uyuşmazlık Mahkemesi decisions.

        The site no longer exposes the old JSON API. We drive the ASP.NET WebForms
        search box (`txtSearch`/`btnSearch`) with a real ViewState postback, then
        parse the resulting `GridView1` table. One text term is supported
        (`icerik`); the legacy dropdown filters (bölüm, uyuşmazlık türü, karar
        sonucu, ...) no longer exist on the upstream site and are ignored.
        """
        term = (params.icerik or params.tumce or "").strip()

        async with self._new_client() as client:
            # 1) GET homepage to capture ViewState
            try:
                home_resp = await client.get(self.PAGE_PATH)
                home_resp.raise_for_status()
            except httpx.RequestError as e:
                logger.error(f"UyusmazlikApiClient: error fetching home page: {e}")
                raise

            soup = BeautifulSoup(home_resp.text, "html.parser")

            if term:
                form = self._hidden_fields(soup)
                # The search form controls (2026 markup)
                form["txtSearch"] = term
                form["btnSearch"] = "Ara"
                form["rblSearchScope"] = "All"  # All | EsasNo | KararNo
                # optional case-sensitivity checkbox left unchecked

                # Empty __doPostBack targets are required by WebForms validators
                form.setdefault("__EVENTTARGET", "")
                form.setdefault("__EVENTARGUMENT", "")

                try:
                    resp = await client.post(
                        self.PAGE_PATH,
                        data=form,
                        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                                 "Referer": self.BASE_URL + self.PAGE_PATH},
                    )
                    resp.raise_for_status()
                    soup = BeautifulSoup(resp.text, "html.parser")
                except httpx.RequestError as e:
                    logger.error(f"UyusmazlikApiClient: error posting search form: {e}")
                    raise
            # else: no term -> browse the default (latest) listing

        return self._parse_results_page(soup, term=term)

    def _parse_results_page(self, soup: BeautifulSoup, term: str = "") -> UyusmazlikSearchResponse:
        """Turns the GridView1 HTML table into our response model."""
        decisions: List[UyusmazlikApiDecisionEntry] = []

        table = soup.find("table", id="GridView1")
        if not table:
            logger.warning("UyusmazlikApiClient: GridView1 table not found in response HTML.")
            return UyusmazlikSearchResponse(decisions=[], total_records_found=0)

        rows = table.find_all("tr")
        for row in rows[1:]:  # skip header
            # pager/footer rows contain only <td> with colspan / js postbacks
            row_text = row.get_text(strip=True)
            if not row_text or "__doPostBack" in str(row):
                # page numbers row
                continue

            tds = row.find_all("td")
            if len(tds) < 4:
                continue

            try:
                esas_no = tds[0].get_text(strip=True)
                karar_no = tds[1].get_text(strip=True)
                karar_tarihi = tds[2].get_text(strip=True)

                pdf_href = None
                a = tds[3].find("a", href=re.compile(r"\.pdf$", re.IGNORECASE))
                if a and a.has_attr("href"):
                    pdf_href = urljoin(self.BASE_URL, a["href"])
                elif len(tds) > 3:
                    # fallback: any pdf link in the row
                    a = row.find("a", href=re.compile(r"\.pdf$", re.IGNORECASE))
                    if a and a.has_attr("href"):
                        pdf_href = urljoin(self.BASE_URL, a["href"])

                if not pdf_href:
                    continue

                decisions.append(
                    UyusmazlikApiDecisionEntry(
                        karar_sayisi=karar_no,
                        esas_sayisi=esas_no,
                        bolum=None,
                        uyusmazlik_konusu=karar_tarihi,  # site's table column is "Karar Tarihi"
                        karar_sonucu=None,
                        popover_content=None,
                        document_url=pdf_href,
                        pdf_url=pdf_href,
                    )
                )
            except Exception as e:
                logger.warning(f"UyusmazlikApiClient: skipping unparsable row ({row_text[:80]}): {e}")

        # The site displays one page (10 rows) per postback; total count isn't
        # shown anymore, so we expose `None` when we can't compute it.
        return UyusmazlikSearchResponse(decisions=decisions, total_records_found=None)

    # ---------- Document (PDF) ----------

    def _convert_pdf_to_markdown_uyusmazlik(self, pdf_bytes: bytes) -> Optional[str]:
        if not pdf_bytes:
            return None
        temp_path = None
        try:
            md = MarkItDown(enable_plugins=False)
            with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".pdf") as tmp:
                tmp.write(pdf_bytes)
                temp_path = tmp.name
            return md.convert(temp_path).text_content
        except Exception as e:
            logger.error(f"UyusmazlikApiClient: PDF->Markdown conversion error: {e}")
            return None
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    async def get_decision_document_as_markdown(self, document_url: str) -> UyusmazlikDocumentMarkdown:
        """
        Downloads a decision from its (new) URL. The site now serves decision text
        only as PDF files under /Uploads/. HTML URLs from search results are
        resolved to their PDF counterpart automatically where possible.
        """
        document_url = str(document_url)  # pydantic v2 HttpUrl is not a str
        logger.info(f"UyusmazlikApiClient: fetching document {document_url}")
        async with self._new_client() as client:
            try:
                resp = await client.get(document_url, headers={"Accept": "application/pdf,*/*"})
                resp.raise_for_status()
            except httpx.RequestError as e:
                logger.error(f"UyusmazlikApiClient: error fetching {document_url}: {e}")
                raise

        content_type = (resp.headers.get("content-type") or "").lower()
        if "pdf" in content_type or document_url.lower().endswith(".pdf"):
            markdown = self._convert_pdf_to_markdown_uyusmazlik(resp.content)
        else:
            # Unexpected: old-style HTML page
            markdown = self._convert_html_to_markdown_uyusmazlik(resp.text)

        return UyusmazlikDocumentMarkdown(source_url=document_url, markdown_content=markdown)

    # kept for backwards compatibility / HTML fallback
    def _convert_html_to_markdown_uyusmazlik(self, full_decision_html_content: str) -> Optional[str]:
        if not full_decision_html_content:
            return None
        processed = html.unescape(full_decision_html_content)
        temp_path = None
        try:
            md = MarkItDown(enable_plugins=False)
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".html", encoding="utf-8") as tmp:
                tmp.write(processed)
                temp_path = tmp.name
            return md.convert(temp_path).text_content
        except Exception as e:
            logger.error(f"UyusmazlikApiClient: HTML->Markdown conversion error: {e}")
            return None
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    async def close_client_session(self):
        logger.info("UyusmazlikApiClient: no persistent session to close.")
