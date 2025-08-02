# models.py
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from langchain_core.messages import BaseMessage

# --------------------------------------------------------------------------- #
#                             ÉTAT GÉNÉRIQUE                                  #
# --------------------------------------------------------------------------- #

class Director(BaseModel):
    first_name: str
    last_name: str
    links: List[str] = []

class CompanyInfo(BaseModel):
    name: str | None = None
    site_url: str | None = None
    registration: str | None = None
    address: str | None = None
    directors: List[Director] = []

class ConvState(BaseModel):
    """
    Schéma de base partagé par tous les nœuds.
    La clé « messages » est requise par LangGraph Studio pour le traçage.
    """ 
    model_config = ConfigDict(arbitrary_types_allowed=True)  # accepte BaseMessage

    messages: List[BaseMessage] = Field(
        default_factory=list, description="Historique de la conversation"
    )
    context: str = ""
    extracted_company: Optional[str] = None
    is_need_review: bool = False
    email: Optional[str] = None
    attempts: int = 0
    # --- Champs pour l’agent Entreprise Hunter ---
    want_email: bool = False
    user_email: Optional[str] = None
    summary: str = ""
    # Mémoire du dernier rapport + options
    last_company: Optional[str] = None
    last_report: str = ""
    extra_note: str = ""      # texte supplémentaire demandé ("précisant Z")
    use_last: bool = False
    company_info: CompanyInfo | None = None
    directors: List[Director] = Field(default_factory=list)

# --------------------------------------------------------------------------- #
#                     SPÉCIFIQUES AU WORKFLOW « EMAIL »                       #
# --------------------------------------------------------------------------- #

class EmailState(ConvState):
    company: str



class EnrichState(ConvState):
    company: str
    company_info: CompanyInfo | None = None
    directors: List[Director] = Field(default_factory=list)

