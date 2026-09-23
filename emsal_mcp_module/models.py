# emsal_mcp_module/models.py

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class EmsalDetailedSearchRequestData(BaseModel):
    """
    Internal model for the 'data' object in the Emsal detailed search payload.
    Field names use aliases to match the exact keys in the API payload
    (e.g., "Bam Hukuk Mahkemeleri" with spaces).
    The API expects empty strings for None/omitted optional fields.
    """
    arananKelime: Optional[str] = ""
    
    Bam_Hukuk_Mahkemeleri: Optional[str] = Field(None, alias="Bam Hukuk Mahkemeleri")
    Hukuk_Mahkemeleri: Optional[str] = Field(None, alias="Hukuk Mahkemeleri")
    # Add other specific court type fields from the form if they are separate keys in payload
    # E.g., "Ceza Mahkemeleri", "İdari Mahkemeler" etc.
    
    birimHukukMah: Optional[str] = Field("", description="List of selected Regional Civil Chambers, '+' separated.") 

    esasYil: Optional[str] = ""
    esasIlkSiraNo: Optional[str] = ""
    esasSonSiraNo: Optional[str] = ""
    kararYil: Optional[str] = ""
    kararIlkSiraNo: Optional[str] = ""
    kararSonSiraNo: Optional[str] = ""
    baslangicTarihi: Optional[str] = ""
    bitisTarihi: Optional[str] = ""
    siralama: str # Mandatory in payload example
    siralamaDirection: str # Mandatory in payload example
    pageSize: int
    pageNumber: int
    
    class Config:
        populate_by_name = True # Enables use of alias in serialization (when dumping to dict for payload)
        # anystr_strip_whitespace = True # Optional: strip whitespace from strings

class EmsalSearchRequest(BaseModel): # This is the model the MCP tool will accept
    """Model for Emsal detailed search request, with user-friendly field names."""
    keyword: Optional[str] = Field(None, description="Keyword to search.")
    
    selected_bam_civil_court: Optional[str] = Field(None, description="Selected BAM Civil Court (maps to 'Bam Hukuk Mahkemeleri' payload key).")
    selected_civil_court: Optional[str] = Field(None, description="Selected Civil Court (maps to 'Hukuk Mahkemeleri' payload key).")
    selected_regional_civil_chambers: Optional[List[str]] = Field(default_factory=list, description="Selected Regional Civil Chambers (for 'birimHukukMah', joined by '+').")

    case_year_esas: Optional[str] = Field(None, description="Case year for 'Esas No'.")
    case_start_seq_esas: Optional[str] = Field(None, description="Starting sequence for 'Esas No'.")
    case_end_seq_esas: Optional[str] = Field(None, description="Ending sequence for 'Esas No'.")
    
    decision_year_karar: Optional[str] = Field(None, description="Decision year for 'Karar No'.")
    decision_start_seq_karar: Optional[str] = Field(None, description="Starting sequence for 'Karar No'.")
    decision_end_seq_karar: Optional[str] = Field(None, description="Ending sequence for 'Karar No'.")
    
    start_date: Optional[str] = Field(None, description="Start date for decision (DD.MM.YYYY).")
    end_date: Optional[str] = Field(None, description="End date for decision (DD.MM.YYYY).")
    
    sort_criteria: str = Field("1", description="Sorting criteria (e.g., 1: Esas No).")
    sort_direction: str = Field("desc", description="Sorting direction ('asc' or 'desc').")
    
    page_number: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)


class EmsalApiDecisionEntry(BaseModel):
    """Model for an individual decision entry from the Emsal API search response."""
    id: str
    daire: Optional[str] = Field(None, description="The chamber/court that made the decision.")
    esasNo: Optional[str] = Field(None)
    kararNo: Optional[str] = Field(None)
    kararTarihi: Optional[str] = Field(None)
    arananKelime: Optional[str] = Field(None, description="Matched keyword from the search.")
    durum: Optional[str] = Field(None, description="Status of the decision (e.g., 'KESİNLEŞMEDİ').")
    # index: Optional[int] = None # Present in Emsal response, can be added if tool needs it

    document_url: Optional[str] = Field(None, description="URL to the full document, constructed by the client. Stored as plain str to keep pydantic 2 serializers happy.")

    class Config:
        extra = 'ignore'

class EmsalApiResponseInnerData(BaseModel):
    """Model for the inner 'data' object in the Emsal API search response."""
    data: List[EmsalApiDecisionEntry]
    recordsTotal: int
    recordsFiltered: int
    draw: Optional[int] = Field(None, description="Draw counter from API, usually for DataTables.")

class EmsalApiResponse(BaseModel):
    """Model for the complete search response from the Emsal API."""
    data: EmsalApiResponseInnerData
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata from API, if any.")

class EmsalDocumentMarkdown(BaseModel):
    """Model for an Emsal decision document, containing only Markdown content."""
    document_id: str
    markdown_content: Optional[str] = Field(None, description="The decision content converted to Markdown.")
    source_url: str

class CompactEmsalSearchResult(BaseModel):
    """A compact search result model for the MCP tool to return."""
    decisions: List[EmsalApiDecisionEntry]
    total_records: int
    requested_page: int
    page_size: int