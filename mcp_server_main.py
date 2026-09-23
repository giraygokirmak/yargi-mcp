# mcp_server_main.py

import asyncio
import atexit
import logging
import os
from pydantic import HttpUrl 
from typing import Optional

# --- Logging Configuration Start ---
LOG_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
if not os.path.exists(LOG_DIRECTORY):
    os.makedirs(LOG_DIRECTORY)
LOG_FILE_PATH = os.path.join(LOG_DIRECTORY, "mcp_server.log")

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG) 

log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(message)s')

file_handler = logging.FileHandler(LOG_FILE_PATH, mode='a', encoding='utf-8')
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.DEBUG) 
root_logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO) 
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)
# --- Logging Configuration End ---

from fastmcp import FastMCP
from pydantic import Field

# --- Module Imports ---
from yargitay_mcp_module.client import YargitayOfficialApiClient
from yargitay_mcp_module.models import (
    YargitayDetailedSearchRequest, YargitayDocumentMarkdown, CompactYargitaySearchResult
)
from danistay_mcp_module.client import DanistayApiClient
from danistay_mcp_module.models import (
    DanistayKeywordSearchRequest, DanistayDetailedSearchRequest,
    DanistayDocumentMarkdown, CompactDanistaySearchResult
)
from emsal_mcp_module.client import EmsalApiClient
from emsal_mcp_module.models import (
    EmsalSearchRequest, EmsalDocumentMarkdown, CompactEmsalSearchResult
)
from uyusmazlik_mcp_module.client import UyusmazlikApiClient
from uyusmazlik_mcp_module.models import (
    UyusmazlikSearchRequest, UyusmazlikSearchResponse, UyusmazlikDocumentMarkdown
)
from anayasa_mcp_module.client import AnayasaMahkemesiApiClient # Norm Denetimi Client
from anayasa_mcp_module.bireysel_client import AnayasaBireyselBasvuruApiClient # Bireysel Başvuru Client
from anayasa_mcp_module.models import (
    AnayasaNormDenetimiSearchRequest,
    AnayasaSearchResult,
    AnayasaDocumentMarkdown,                # For Norm Denetimi documents
    AnayasaBireyselReportSearchRequest,     # For Bireysel Başvuru reports
    AnayasaBireyselReportSearchResult,      # For Bireysel Başvuru reports
    AnayasaBireyselBasvuruDocumentMarkdown, # For Bireysel Başvuru documents
)

app = FastMCP(
    name="TurkishLawResearchAssistantMCP",
    instructions="MCP server for TR legal databases (Yargitay, Danistay, Emsal, Uyusmazlik, Anayasa-Norm, Anayasa-Bireysel).",
    dependencies=["httpx", "beautifulsoup4", "markitdown", "pydantic", "aiohttp"]
)

# --- API Client Instances ---
yargitay_client_instance = YargitayOfficialApiClient()
danistay_client_instance = DanistayApiClient()
emsal_client_instance = EmsalApiClient()
uyusmazlik_client_instance = UyusmazlikApiClient()
anayasa_norm_client_instance = AnayasaMahkemesiApiClient()
anayasa_bireysel_client_instance = AnayasaBireyselBasvuruApiClient()

# --- MCP Tools for Yargitay ---
@app.tool()
async def search_yargitay_detailed(search_query: YargitayDetailedSearchRequest) -> CompactYargitaySearchResult:
    """Searches Yargitay (Court of Cassation) decisions using detailed criteria."""
    logger.info(f"Tool 'search_yargitay_detailed' called: {search_query.model_dump_json(exclude_none=True, indent=2)}")
    try:
        api_response = await yargitay_client_instance.search_detailed_decisions(search_query)
        if api_response.data:
            return CompactYargitaySearchResult(
                decisions=api_response.data.data,
                total_records=api_response.data.recordsTotal,
                requested_page=search_query.pageNumber,
                page_size=search_query.pageSize)
        logger.warning("API response for Yargitay search did not contain expected data structure.")
        return CompactYargitaySearchResult(decisions=[], total_records=0, requested_page=search_query.pageNumber, page_size=search_query.pageSize)
    except Exception as e:
        logger.exception(f"Error in tool 'search_yargitay_detailed' with query: {search_query.model_dump_json(exclude_none=True, indent=2)}")
        raise

@app.tool()
async def get_yargitay_document_markdown(document_id: str) -> YargitayDocumentMarkdown:
    """Retrieves a specific Yargitay decision by its ID and returns its content as Markdown."""
    logger.info(f"Tool 'get_yargitay_document_markdown' called for ID: {document_id}")
    if not document_id or not document_id.strip(): raise ValueError("Document ID must be a non-empty string.")
    try:
        return await yargitay_client_instance.get_decision_document_as_markdown(document_id)
    except Exception as e:
        logger.exception(f"Error in tool 'get_yargitay_document_markdown' for ID: {document_id}")
        raise

# --- MCP Tools for Danistay ---
@app.tool()
async def search_danistay_by_keyword(search_query: DanistayKeywordSearchRequest) -> CompactDanistaySearchResult:
    """Searches Danıştay (Council of State) decisions using keywords."""
    logger.info(f"Tool 'search_danistay_by_keyword' called: {search_query.model_dump_json(exclude_none=True, indent=2)}")
    try:
        api_response = await danistay_client_instance.search_keyword_decisions(search_query)
        if api_response.data:
            return CompactDanistaySearchResult( 
                decisions=api_response.data.data,
                total_records=api_response.data.recordsTotal, 
                requested_page=search_query.pageNumber,
                page_size=search_query.pageSize)
        logger.warning("API response for Danistay keyword search did not contain expected data structure.")
        return CompactDanistaySearchResult(decisions=[], total_records=0, requested_page=search_query.pageNumber, page_size=search_query.pageSize)
    except Exception as e:
        logger.exception(f"Error in tool 'search_danistay_by_keyword': {search_query.model_dump_json(exclude_none=True, indent=2)}")
        raise

@app.tool()
async def search_danistay_detailed(search_query: DanistayDetailedSearchRequest) -> CompactDanistaySearchResult:
    """Performs a detailed search for Danıştay (Council of State) decisions."""
    logger.info(f"Tool 'search_danistay_detailed' called: {search_query.model_dump_json(exclude_none=True, indent=2)}")
    try:
        api_response = await danistay_client_instance.search_detailed_decisions(search_query)
        if api_response.data:
            return CompactDanistaySearchResult( 
                decisions=api_response.data.data,
                total_records=api_response.data.recordsTotal, 
                requested_page=search_query.pageNumber,
                page_size=search_query.pageSize)
        logger.warning("API response for Danistay detailed search did not contain expected data structure.")
        return CompactDanistaySearchResult(decisions=[], total_records=0, requested_page=search_query.pageNumber, page_size=search_query.pageSize)
    except Exception as e:
        logger.exception(f"Error in tool 'search_danistay_detailed': {search_query.model_dump_json(exclude_none=True, indent=2)}")
        raise

@app.tool()
async def get_danistay_document_markdown(document_id: str) -> DanistayDocumentMarkdown:
    """Retrieves a specific Danıştay decision by ID and returns its content as Markdown."""
    logger.info(f"Tool 'get_danistay_document_markdown' called for ID: {document_id}")
    if not document_id or not document_id.strip(): raise ValueError("Document ID must be a non-empty string for Danıştay.")
    try:
        return await danistay_client_instance.get_decision_document_as_markdown(document_id)
    except Exception as e:
        logger.exception(f"Error in tool 'get_danistay_document_markdown' for ID: {document_id}")
        raise

# --- MCP Tools for Emsal ---
@app.tool()
async def search_emsal_detailed_decisions(search_query: EmsalSearchRequest) -> CompactEmsalSearchResult:
    """Searches for Emsal (UYAP Precedent) decisions using detailed criteria."""
    logger.info(f"Tool 'search_emsal_detailed_decisions' called: {search_query.model_dump_json(exclude_none=True, indent=2)}")
    try:
        api_response = await emsal_client_instance.search_detailed_decisions(search_query)
        if api_response.data:
            return CompactEmsalSearchResult(
                decisions=api_response.data.data,
                total_records=api_response.data.totalRecords if api_response.data.totalRecords is not None else 0,
                requested_page=search_query.page_number,
                page_size=search_query.page_size
            )
        logger.warning("API response for Emsal search did not contain expected data structure.")
        return CompactEmsalSearchResult(decisions=[], total_records=0, requested_page=search_query.page_number, page_size=search_query.page_size)
    except Exception as e:
        logger.exception(f"Error in tool 'search_emsal_detailed_decisions': {search_query.model_dump_json(exclude_none=True, indent=2)}")
        raise

@app.tool()
async def get_emsal_document_markdown(document_id: str) -> EmsalDocumentMarkdown:
    """Retrieves a specific Emsal decision by ID and returns its content as Markdown."""
    logger.info(f"Tool 'get_emsal_document_markdown' called for ID: {document_id}")
    if not document_id or not document_id.strip(): raise ValueError("Document ID required for Emsal.")
    try:
        return await emsal_client_instance.get_decision_document_as_markdown(document_id)
    except Exception as e:
        logger.exception(f"Error in tool 'get_emsal_document_markdown' for ID: {document_id}")
        raise

# --- MCP Tools for Uyusmazlik ---
@app.tool()
async def search_uyusmazlik_decisions(
    search_params: UyusmazlikSearchRequest
) -> UyusmazlikSearchResponse:
    """Searches for Uyuşmazlık Mahkemesi decisions using various criteria from the form."""
    logger.info(f"Tool 'search_uyusmazlik_decisions' called with params: {search_params.model_dump_json(exclude_none=True, indent=2)}")
    try:
        return await uyusmazlik_client_instance.search_decisions(search_params)
    except Exception as e:
        logger.exception(f"Error in tool 'search_uyusmazlik_decisions': {search_params.model_dump_json(exclude_none=True, indent=2)}")
        raise

@app.tool()
async def get_uyusmazlik_document_markdown_from_url(document_url: HttpUrl) -> UyusmazlikDocumentMarkdown:
    """
    Retrieves a specific Uyuşmazlık Mahkemesi decision from its full URL
    and returns its content as Markdown.
    The URL is typically obtained from the 'search_uyusmazlik_decisions' tool results.
    """
    logger.info(f"Tool 'get_uyusmazlik_document_markdown_from_url' called for URL: {str(document_url)}")
    if not document_url:
        raise ValueError("Document URL (document_url) is required for Uyuşmazlık document retrieval.")
    try:
        return await uyusmazlik_client_instance.get_decision_document_as_markdown(str(document_url))
    except Exception as e:
        logger.exception(f"Error in tool 'get_uyusmazlik_document_markdown_from_url' for URL: {str(document_url)}")
        raise

# --- MCP Tools for Anayasa Mahkemesi (Norm Denetimi) ---
@app.tool()
async def search_anayasa_norm_denetimi_decisions(
    search_query: AnayasaNormDenetimiSearchRequest
) -> AnayasaSearchResult:
    """
    Searches Anayasa Mahkemesi (Constitutional Court) Norm Denetimi decisions
    using various criteria from the official search form. This is for https://normkararlarbilgibankasi.anayasa.gov.tr.
    """
    logger.info(f"Tool 'search_anayasa_norm_denetimi_decisions' called: {search_query.model_dump_json(exclude_none=True, indent=2)}")
    try:
        return await anayasa_norm_client_instance.search_norm_denetimi_decisions(search_query)
    except Exception as e:
        logger.exception(f"Error in tool 'search_anayasa_norm_denetimi_decisions': {search_query.model_dump_json(exclude_none=True, indent=2)}")
        raise

@app.tool()
async def get_anayasa_norm_denetimi_document_markdown(
    document_url: str = Field(..., description="The URL path of the AYM Norm Denetimi decision (e.g., /ND/YYYY/NN) or full https URL from normkararlarbilgibankasi.anayasa.gov.tr."),
    page_number: Optional[int] = Field(1, ge=1, description="Page number for paginated Markdown content, 1-indexed. Default is 1 for the first 5,000 characters.") # Corrected chunk size in description
) -> AnayasaDocumentMarkdown:
    """
    Retrieves a specific Anayasa Mahkemesi (Norm Denetimi) decision
    from its URL and returns its content as paginated Markdown. This is for https://normkararlarbilgibankasi.anayasa.gov.tr.
    Content is paginated if it exceeds 5,000 characters. Use 'page_number' to get subsequent pages.
    """
    logger.info(f"Tool 'get_anayasa_norm_denetimi_document_markdown' called for URL: {document_url}, Page: {page_number}")
    if not document_url or not document_url.strip():
        raise ValueError("Document URL is required for Anayasa Norm Denetimi document retrieval.")
    current_page_to_fetch = page_number if page_number is not None and page_number >= 1 else 1
    try:
        return await anayasa_norm_client_instance.get_decision_document_as_markdown(document_url, page_number=current_page_to_fetch)
    except Exception as e:
        logger.exception(f"Error in tool 'get_anayasa_norm_denetimi_document_markdown' for URL: {document_url}, Page: {current_page_to_fetch}")
        raise

# --- MCP Tools for Anayasa Mahkemesi (Bireysel Başvuru Karar Raporu & Belgeler) ---
@app.tool()
async def search_anayasa_bireysel_basvuru_report(
    search_query: AnayasaBireyselReportSearchRequest
) -> AnayasaBireyselReportSearchResult:
    """
    Searches Anayasa Mahkemesi (Constitutional Court) Bireysel Başvuru (Individual Application)
    decisions and generates a 'Karar Arama Raporu' (Decision Search Report).
    This is for https://kararlarbilgibankasi.anayasa.gov.tr and uses the KararBulteni=1 parameter.
    The report typically displays 10 decisions per page by default.
    """
    logger.info(f"Tool 'search_anayasa_bireysel_basvuru_report' called: {search_query.model_dump_json(exclude_none=True, indent=2)}")
    try:
        return await anayasa_bireysel_client_instance.search_bireysel_basvuru_report(search_query)
    except Exception as e:
        logger.exception(f"Error in tool 'search_anayasa_bireysel_basvuru_report': {search_query.model_dump_json(exclude_none=True, indent=2)}")
        raise

@app.tool()
async def get_anayasa_bireysel_basvuru_document_markdown(
    document_url_path: str = Field(..., description="The URL path of the AYM Bireysel Başvuru decision (e.g., /BB/YYYY/NNNN) from kararlarbilgibankasi.anayasa.gov.tr."),
    page_number: Optional[int] = Field(1, ge=1, description="Page number for paginated Markdown content, 1-indexed. Default is 1 for the first 5,000 characters.")
) -> AnayasaBireyselBasvuruDocumentMarkdown:
    """
    Retrieves a specific Anayasa Mahkemesi Bireysel Başvuru (Individual Application) decision
    from its URL path (e.g., /BB/YYYY/NNNN found in report results) and returns its content as paginated Markdown.
    This is for https://kararlarbilgibankasi.anayasa.gov.tr.
    Content is paginated if it exceeds 5,000 characters. Use 'page_number' to get subsequent pages.
    """
    logger.info(f"Tool 'get_anayasa_bireysel_basvuru_document_markdown' called for URL path: {document_url_path}, Page: {page_number}")
    if not document_url_path or not document_url_path.strip() or not document_url_path.startswith("/BB/"):
        raise ValueError("Document URL path (e.g., /BB/YYYY/NNNN) is required for Anayasa Bireysel Başvuru document retrieval.")
    
    current_page_to_fetch = page_number if page_number is not None and page_number >= 1 else 1
    
    try:
        return await anayasa_bireysel_client_instance.get_decision_document_as_markdown(document_url_path, page_number=current_page_to_fetch)
    except Exception as e:
        logger.exception(f"Error in tool 'get_anayasa_bireysel_basvuru_document_markdown' for URL path: {document_url_path}, Page: {current_page_to_fetch}")
        raise

# --- Application Shutdown Handling ---
def perform_cleanup():
    logger.info("MCP Server performing cleanup...")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError: # pragma: no cover
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        clients_to_close = [
            globals().get('yargitay_client_instance'),
            globals().get('danistay_client_instance'),
            globals().get('emsal_client_instance'),
            globals().get('uyusmazlik_client_instance'),
            globals().get('anayasa_norm_client_instance'),
            globals().get('anayasa_bireysel_client_instance')
        ]
        for client_instance in clients_to_close:
            if client_instance and hasattr(client_instance, 'close_client_session') and callable(client_instance.close_client_session):
                logger.info(f"Closing client session for {client_instance.__class__.__name__} via atexit.")
                loop.run_until_complete(client_instance.close_client_session())
    except Exception as e:
        logger.error(f"Error during atexit cleanup: {e}")
    logger.info("MCP Server atexit cleanup attempt finished.")

atexit.register(perform_cleanup)

# --- Main Entry Point ---
if __name__ == "__main__":
    # Standalone Docker container kalibi (23 Eyl 2026, Giray):
    # Ortam degiskeniyle streamable-http; varsayilan SSE geriye donuk uyumluluk.
    MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "sse")
    MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
    MCP_PORT = int(os.environ.get("MCP_PORT", "8890"))
    logger.info(f"Starting {app.name} server (main execution block)... transport={MCP_TRANSPORT} host={MCP_HOST} port={MCP_PORT}")
    logger.info(f"Logs will be written to: {LOG_FILE_PATH}")
    try:
        if MCP_TRANSPORT in ("http", "streamable-http"):
            asyncio.run(app.run_http_async(transport="streamable-http", host=MCP_HOST, port=MCP_PORT, log_level="info"))
        else:
            asyncio.run(app.run_sse_async(host=MCP_HOST, port=MCP_PORT, log_level="debug"))
    except KeyboardInterrupt:
        logger.info("Server shut down by user (KeyboardInterrupt).")
    except Exception as e:
        logger.exception("Server failed to start or crashed.")
    finally:
        logger.info(f"{app.name} server has shut down.")