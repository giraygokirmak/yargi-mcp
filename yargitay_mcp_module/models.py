# yargitay_mcp_module/models.py

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class YargitayDetailedSearchRequest(BaseModel):
    """
    Model for the 'data' object sent in the request payload
    to Yargitay's detailed search endpoint (e.g., /aramadetaylist).
    Based on the payload provided by the user.
    """
    arananKelime: Optional[str] = Field("", description="Keyword to search for.")
    # Department/Board selection. Based on user provided payload.
    # birimYrg* fields seem to be the ones used for filtering.
    birimYrgKurulDaire: Optional[str] = Field("", description="Yargitay Board Unit (e.g., 'Hukuk Genel Kurulu').")
    birimYrgHukukDaire: Optional[str] = Field("", description="Yargitay Civil Chamber (e.g., '1. Hukuk Dairesi').")
    birimYrgCezaDaire: Optional[str] = Field("", description="Yargitay Criminal Chamber.")
    
    esasYil: Optional[str] = Field("", description="Case year for 'Esas No'.")
    esasIlkSiraNo: Optional[str] = Field("", description="Starting sequence number for 'Esas No'.")
    esasSonSiraNo: Optional[str] = Field("", description="Ending sequence number for 'Esas No'.")
    
    kararYil: Optional[str] = Field("", description="Decision year for 'Karar No'.")
    kararIlkSiraNo: Optional[str] = Field("", description="Starting sequence number for 'Karar No'.")
    kararSonSiraNo: Optional[str] = Field("", description="Ending sequence number for 'Karar No'.")
    
    baslangicTarihi: Optional[str] = Field("", description="Start date for decision search (DD.MM.YYYY).")
    bitisTarihi: Optional[str] = Field("", description="End date for decision search (DD.MM.YYYY).")
    
    siralama: Optional[str] = Field("3", description="Sorting criteria (1: Esas No, 2: Karar No, 3: Karar Tarihi).") # Default to 'Karar Tarihine Göre'
    siralamaDirection: Optional[str] = Field("desc", description="Sorting direction ('asc' or 'desc').") # Default to 'Büyükten Küçüğe'
    
    pageSize: int = Field(10, ge=1, le=100, description="Number of results per page.")
    pageNumber: int = Field(1, ge=1, description="Page number to retrieve.")

class YargitayApiDecisionEntry(BaseModel):
    """Model for an individual decision entry from the Yargitay API search response."""
    id: str # Unique system ID of the decision
    daire: Optional[str] = Field(None, description="The chamber that made the decision.")
    esasNo: Optional[str] = Field(None, alias="esasNo", description="Case registry number ('Esas No').")
    kararNo: Optional[str] = Field(None, alias="kararNo", description="Decision number ('Karar No').")
    kararTarihi: Optional[str] = Field(None, alias="kararTarihi", description="Date of the decision.")
    arananKelime: Optional[str] = Field(None, alias="arananKelime", description="Matched keyword in the search result item.")
    # 'index' and 'siraNo' from API response are not critical for MCP tool, so omitted for brevity
    
    # Assigned by the client after fetching the search list. Stored as plain str
    # so pydantic 2 doesn't warn during JSON serialization (HttpUrl is no longer
    # a str subclass in pydantic 2).
    document_url: Optional[str] = Field(None, description="Direct URL to the decision document.")

    class Config:
        populate_by_name = True # To allow populating by alias from API response


class YargitayApiResponseInnerData(BaseModel):
    """Model for the inner 'data' object in the Yargitay API search response."""
    data: List[YargitayApiDecisionEntry]
    # draw: Optional[int] = None # Typically used by DataTables, not essential for MCP
    recordsTotal: int # Total number of records matching the query
    recordsFiltered: int # Total number of records after filtering (usually same as recordsTotal)

class YargitayApiSearchResponse(BaseModel):
    """Model for the complete search response from the Yargitay API."""
    data: YargitayApiResponseInnerData
    # metadata: Optional[Dict[str, Any]] = None # Optional metadata from API

class YargitayDocumentMarkdown(BaseModel):
    """Model for a Yargitay decision document, containing only Markdown content."""
    document_id: str = Field(..., description="The unique ID of the document.")
    markdown_content: Optional[str] = Field(None, description="The decision content converted to Markdown.")
    source_url: str = Field(..., description="The source URL of the original document.")

class CompactYargitaySearchResult(BaseModel):
    """A more compact search result model for the MCP tool to return."""
    decisions: List[YargitayApiDecisionEntry]
    total_records: int
    requested_page: int
    page_size: int