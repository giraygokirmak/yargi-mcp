# uyusmazlik_mcp_module/models.py

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

# Enum definitions for user-friendly input based on the provided HTML form
class UyusmazlikBolumEnum(str, Enum):
    """User-friendly names for 'BolumId'."""
    TUMU = "" # Represents "...Seçiniz..." or all
    CEZA_BOLUMU = "Ceza Bölümü"
    GENEL_KURUL_KARARLARI = "Genel Kurul Kararları"
    HUKUK_BOLUMU = "Hukuk Bölümü"

class UyusmazlikTuruEnum(str, Enum):
    """User-friendly names for 'UyusmazlikId'."""
    TUMU = "" # Represents "...Seçiniz..." or all
    GOREV_UYUSMAZLIGI = "Görev Uyuşmazlığı"
    HUKUM_UYUSMAZLIGI = "Hüküm Uyuşmazlığı"

class UyusmazlikKararSonucuEnum(str, Enum): # Based on checkbox text in the form
    """User-friendly names for 'KararSonucuList' items."""
    HUKUM_UYUSMAZLIGI_OLMADIGINA_DAIR = "Hüküm Uyuşmazlığı Olmadığına Dair"
    HUKUM_UYUSMAZLIGI_OLDUGUNA_DAIR = "Hüküm Uyuşmazlığı Olduğuna Dair"
    # Add other "Karar Sonucu" options from the form's checkboxes as Enum members
    # Example: GOREVLI_YARGI_YERI_ADLI = "Görevli Yargı Yeri Belirlenmesine Dair (Adli Yargı)"
    # The client will map these enum values (which are strings) to their respective IDs.

class UyusmazlikSearchRequest(BaseModel): # This is the model the MCP tool will accept
    """Model for Uyuşmazlık Mahkemesi search request using user-friendly terms."""
    icerik: Optional[str] = Field("", description="Keyword or content for main text search (Icerik).")
    
    bolum: Optional[UyusmazlikBolumEnum] = Field(
        UyusmazlikBolumEnum.TUMU, 
        description="Select the department (Bölüm)."
    )
    uyusmazlik_turu: Optional[UyusmazlikTuruEnum] = Field(
        UyusmazlikTuruEnum.TUMU, 
        description="Select the type of dispute (Uyuşmazlık)."
    )
    
    # User provides a list of user-friendly names for Karar Sonucu
    karar_sonuclari: Optional[List[UyusmazlikKararSonucuEnum]] = Field( # Changed to list of Enums
        default_factory=list, 
        description="List of desired 'Karar Sonucu' types."
    )
    
    esas_yil: Optional[str] = Field("", description="Case year ('Esas Yılı').")
    esas_sayisi: Optional[str] = Field("", description="Case number ('Esas Sayısı').")
    karar_yil: Optional[str] = Field("", description="Decision year ('Karar Yılı').")
    karar_sayisi: Optional[str] = Field("", description="Decision number ('Karar Sayısı').")
    kanun_no: Optional[str] = Field("", description="Relevant Law Number ('KanunNo').")
    
    karar_date_begin: Optional[str] = Field("", description="Decision start date (DD.MM.YYYY) ('KararDateBegin').")
    karar_date_end: Optional[str] = Field("", description="Decision end date (DD.MM.YYYY) ('KararDateEnd').")
    
    resmi_gazete_sayi: Optional[str] = Field("", description="Official Gazette number ('ResmiGazeteSayi').")
    resmi_gazete_date: Optional[str] = Field("", description="Official Gazette date (DD.MM.YYYY) ('ResmiGazeteDate').")
    
    # Detailed text search fields from the "icerikDetail" section of the form
    tumce: Optional[str] = Field("", description="Exact phrase search ('Tumce').")
    wild_card: Optional[str] = Field("", description="Search for phrase and its inflections ('WildCard').") # Changed from WildCard for Pythonic name
    hepsi: Optional[str] = Field("", description="Search for texts containing all specified words ('Hepsi').")
    herhangi_birisi: Optional[str] = Field("", description="Search for texts containing any of the specified words ('Herhangibirisi').")
    not_hepsi: Optional[str] = Field("", description="Exclude texts containing these specified words ('NotHepsi').")

class UyusmazlikApiDecisionEntry(BaseModel):
    """Model for an individual decision entry parsed from Uyuşmazlık API's HTML search response."""
    karar_sayisi: Optional[str] = Field(None)
    esas_sayisi: Optional[str] = Field(None)
    bolum: Optional[str] = Field(None)
    uyusmazlik_konusu: Optional[str] = Field(None)
    karar_sonucu: Optional[str] = Field(None)
    popover_content: Optional[str] = Field(None, description="Summary/description from popover.")
    # Stored as plain str (pydantic 2 HttpUrl is not a str subclass and triggers
    # serializer warnings when assigned from a Python string).
    document_url: str
    pdf_url: Optional[str] = Field(None, description="Direct URL to PDF if available.")

class UyusmazlikSearchResponse(BaseModel): # This is what the MCP tool will return
    """Response model for Uyuşmazlık Mahkemesi search results for the MCP tool."""
    decisions: List[UyusmazlikApiDecisionEntry]
    total_records_found: Optional[int] = Field(None, description="Total number of records found for the query, if available.")

class UyusmazlikDocumentMarkdown(BaseModel):
    """Model for an Uyuşmazlık decision document, containing only Markdown content."""
    source_url: str # The URL from which the content was fetched
    markdown_content: Optional[str] = Field(None, description="The decision content converted to Markdown.")