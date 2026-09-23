# danistay_mcp_module/client.py

import httpx
from bs4 import BeautifulSoup 
from typing import Dict, Any, List, Optional
import logging
import html
import re
import tempfile
import os
from markitdown import MarkItDown

from .models import (
    DanistayKeywordSearchRequest,
    DanistayDetailedSearchRequest,
    DanistayApiResponse,
    DanistayDocumentMarkdown,
    DanistayKeywordSearchRequestData,
    DanistayDetailedSearchRequestData
)

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class DanistayApiClient:
    BASE_URL = "https://karararama.danistay.gov.tr"
    KEYWORD_SEARCH_ENDPOINT = "/aramalist"
    DETAILED_SEARCH_ENDPOINT = "/aramadetaylist"
    DOCUMENT_ENDPOINT = "/getDokuman"

    def __init__(self, request_timeout: float = 60.0):
        self.http_client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Content-Type": "application/json; charset=UTF-8", # Arama endpoint'leri için
                "Accept": "application/json, text/plain, */*",    # Arama endpoint'leri için
                # /getDokuman HTML döndürdüğü için Accept header'ı GET isteğinde farklı olabilir
                # ama httpx genellikle bunu yönetir. Gerekirse özel header eklenebilir.
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=request_timeout,
            verify=False 
        )

    def _prepare_keywords_for_api(self, keywords: List[str]) -> List[str]:
        return [f'"{k.strip("\"")}"' for k in keywords if k and k.strip()]

    async def search_keyword_decisions(
        self,
        params: DanistayKeywordSearchRequest
    ) -> DanistayApiResponse:
        data_for_payload = DanistayKeywordSearchRequestData(
            andKelimeler=self._prepare_keywords_for_api(params.andKelimeler),
            orKelimeler=self._prepare_keywords_for_api(params.orKelimeler),
            notAndKelimeler=self._prepare_keywords_for_api(params.notAndKelimeler),
            notOrKelimeler=self._prepare_keywords_for_api(params.notOrKelimeler),
            pageSize=params.pageSize,
            pageNumber=params.pageNumber
        )
        final_payload = {"data": data_for_payload.model_dump(exclude_none=True)}
        logger.info(f"DanistayApiClient: Performing KEYWORD search via {self.KEYWORD_SEARCH_ENDPOINT} with payload: {final_payload}")
        return await self._execute_api_search(self.KEYWORD_SEARCH_ENDPOINT, final_payload)

    async def search_detailed_decisions(
        self,
        params: DanistayDetailedSearchRequest
    ) -> DanistayApiResponse:
        data_for_payload = DanistayDetailedSearchRequestData(
            daire=params.daire or "",
            esasYil=params.esasYil or "",
            esasIlkSiraNo=params.esasIlkSiraNo or "",
            esasSonSiraNo=params.esasSonSiraNo or "",
            kararYil=params.kararYil or "",
            kararIlkSiraNo=params.kararIlkSiraNo or "",
            kararSonSiraNo=params.kararSonSiraNo or "",
            baslangicTarihi=params.baslangicTarihi or "",
            bitisTarihi=params.bitisTarihi or "",
            mevzuatNumarasi=params.mevzuatNumarasi or "",
            mevzuatAdi=params.mevzuatAdi or "",
            madde=params.madde or "",
            siralama=params.siralama,
            siralamaDirection=params.siralamaDirection,
            pageSize=params.pageSize,
            pageNumber=params.pageNumber
        )
        final_payload = {"data": data_for_payload.model_dump(exclude_defaults=False, exclude_none=False)}
        logger.info(f"DanistayApiClient: Performing DETAILED search via {self.DETAILED_SEARCH_ENDPOINT} with payload: {final_payload}")
        return await self._execute_api_search(self.DETAILED_SEARCH_ENDPOINT, final_payload)

    async def _execute_api_search(self, endpoint: str, payload: Dict) -> DanistayApiResponse:
        try:
            response = await self.http_client.post(endpoint, json=payload)
            response.raise_for_status()
            response_json_data = response.json()
            logger.debug(f"DanistayApiClient: Raw API response from {endpoint}: {response_json_data}")

            # The Danıştay API returns HTTP 200 with a `metadata.FMC` business error
            # (e.g. when no search criteria were supplied). Surface that instead of
            # failing Pydantic validation on the empty `data` payload.
            metadata = response_json_data.get("metadata") or {}
            if metadata.get("FMC") == "ADALET_RUNTIME_EXCEPTION":
                message = metadata.get("FMTE") or metadata.get("FMU") or "Danistay API hatası"
                raise ValueError(f"Danistay API hatası: {message}")

            api_response_parsed = DanistayApiResponse(**response_json_data)
            if api_response_parsed.data and api_response_parsed.data.data:
                for decision_item in api_response_parsed.data.data:
                    if decision_item.id:
                        decision_item.document_url = f"{self.BASE_URL}{self.DOCUMENT_ENDPOINT}?id={decision_item.id}"
            return api_response_parsed
        except httpx.RequestError as e:
            logger.error(f"DanistayApiClient: HTTP request error during search to {endpoint}: {e}")
            raise
        except Exception as e:
            logger.error(f"DanistayApiClient: Error processing or validating search response from {endpoint}: {e}")
            raise

    def _convert_html_to_markdown_danistay(self, direct_html_content: str) -> Optional[str]:
        """
        Converts direct HTML content (assumed from Danıştay /getDokuman) to Markdown.
        """
        if not direct_html_content:
            return None

        # Basic HTML unescaping and fixing common escaped characters
        # This step might be less critical if MarkItDown handles them, but good for pre-cleaning.
        processed_html = html.unescape(direct_html_content)
        processed_html = processed_html.replace('\\"', '"') # If any such JS-escaped strings exist
        # Danistay HTML doesn't seem to have \\r\\n etc. from the example, but keeping for robustness
        processed_html = processed_html.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\t', '\t')
        
        # For simplicity and to leverage MarkItDown's capability to handle full docs,
        # we pass the pre-processed full HTML.
        html_input_for_markdown = processed_html

        markdown_text = None
        temp_file_path = None
        try:
            md_converter = MarkItDown(enable_plugins=False) # Basic conversion
            
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".html", encoding="utf-8") as tmp_file:
                tmp_file.write(html_input_for_markdown) # Write the full HTML string
                temp_file_path = tmp_file.name
            
            conversion_result = md_converter.convert(temp_file_path)
            markdown_text = conversion_result.text_content
            logger.info("DanistayApiClient: HTML to Markdown conversion successful.")
        except Exception as e:
            logger.error(f"DanistayApiClient: Error during MarkItDown HTML to Markdown conversion: {e}")
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
        
        return markdown_text

    async def get_decision_document_as_markdown(self, document_id: str) -> DanistayDocumentMarkdown:
        """
        Retrieves a specific Danıştay decision by ID and returns its content as Markdown.
        The /getDokuman endpoint for Danıştay returns direct HTML.
        """
        document_api_url = f"{self.DOCUMENT_ENDPOINT}?id={document_id}"
        source_url = f"{self.BASE_URL}{document_api_url}"
        logger.info(f"DanistayApiClient: Fetching Danistay document for Markdown (ID: {document_id}) from {source_url}")

        try:
            # For direct HTML response, we might want different headers if the API is sensitive,
            # but httpx usually handles basic GET requests well.
            response = await self.http_client.get(document_api_url)
            response.raise_for_status()
            
            # Danıştay /getDokuman directly returns HTML text
            html_content_from_api = response.text

            if not isinstance(html_content_from_api, str) or not html_content_from_api.strip():
                logger.warning(f"DanistayApiClient: Received empty or non-string HTML content for ID {document_id}.")
                # Return with None markdown_content if HTML is effectively empty
                return DanistayDocumentMarkdown(
                    document_id=document_id,
                    markdown_content=None,
                    source_url=source_url
                )

            markdown_content = self._convert_html_to_markdown_danistay(html_content_from_api)

            return DanistayDocumentMarkdown(
                document_id=document_id,
                markdown_content=markdown_content,
                source_url=source_url
            )
        except httpx.RequestError as e:
            logger.error(f"DanistayApiClient: HTTP error fetching Danistay document (ID: {document_id}): {e}")
            raise
        # Removed ValueError for JSON as Danistay /getDokuman returns direct HTML
        except Exception as e: # Catches other errors like MarkItDown issues if they propagate
            logger.error(f"DanistayApiClient: General error processing Danistay document (ID: {document_id}): {e}")
            raise

    async def close_client_session(self):
        """Closes the HTTPX client session."""
        if self.http_client and not self.http_client.is_closed:
            await self.http_client.aclose()
        logger.info("DanistayApiClient: HTTP client session closed.")