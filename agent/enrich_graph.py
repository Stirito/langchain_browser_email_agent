"""
Graphe principal + sous‑graphe d'enrichissement Entreprise.
Boucle d'auto‑correction « draft ↔ review ».
"""
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from agent.models import EnrichState, CompanyInfo, Director
from agent import tools
import re, logging

logger = logging.getLogger("enrich_graph")

# -- Helpers -----------------------------------------------------------------



def _parse_societe_markdown(md: str, company: str) -> CompanyInfo:
    """Extrait informations clés depuis le Markdown de Societe.com."""
    lines = md.split("\n")
    name = None
    site_url = None
    registration = None
    address = None
    directors: list[Director] = []
    

    # Cherche l'URL du profil société sur societe.com
    # Collecte toutes les URL societe.com présentes dans le markdown
    all_societe = []
    for u in re.findall(r'https?://[^\s)]+', md):
        clean = u.strip('<>').strip()
        if 'societe.com' in clean:
            clean = clean.replace('cgi-bin/</societe/', 'societe/').replace('</', '')
            all_societe.append(clean)

    # Sélectionne celle qui ressemble le plus au nom de l'entreprise
    tokens = set(re.sub('[^a-z0-9]', ' ', company.lower()).split())
    best_score = 0
    for url in all_societe:
        slug = url.split('/')[-1]
        score = sum(1 for t in tokens if t in slug.lower())
        if score > best_score:
            best_score = score
            site_url = url

    logger.info(f"Best score: {best_score} for {site_url}")

    # Nom et SIREN (première ligne en majuscules suivie de numéro)
    for l in lines:
        if re.match(r"^[A-Z][A-Z0-9 &'-]+\d{3}", l):
            parts = l.split()
            name = " ".join(part for part in parts if not part.isdigit())
            registration = next((p for p in parts if p.isdigit()), None)
            break

    # Adresse (ligne contenant un code postal)
    for l in lines:
        if re.search(r"\d{5} [A-Z]", l):
            address = l.strip()
            break
        
    logger.info(f"Name: {name}, Registration: {registration}, Address: {address}")
    logger.info(f"Directors: {directors}")

    return CompanyInfo(name=name, site_url=site_url, registration=registration, address=address, directors=directors)


async def fetch_societe(state: EnrichState):
    clean_company = state.company.replace(" ", "+")
    url = (
        f"https://www.societe.com/cgi-bin/search?champs=siren&q={clean_company}"
    )
    markdown = await tools.crawl_markdown(url)
    logger.info("[Enrich] Societe.com markdown récupéré")

    company_info = _parse_societe_markdown(markdown, state.company)
    ctx = state.context + markdown
    state.company_info = company_info
    return {"context": ctx, "company_info": company_info}


async def directors(state: EnrichState):
    logger.info(f"[Enrich] crawl_dirigeants → {state.company_info.site_url}")
    gathered_directors = await tools.crawl_dirigeants(state.company_info.site_url)
    logger.info(f"Gathered directors: {gathered_directors}")
    logger.info(f"[Enrich] crawl_dirigeants → {len(gathered_directors)} dirigeants")
    ctx = state.context + "\n" + "\n".join([f"{d.first_name} {d.last_name}" for d in gathered_directors])
    state.company_info.directors = gathered_directors
    return {"context": ctx, "company_info": state.company_info}


async def profiles(state: EnrichState):
    ctx = state.context
    logger.info(f"[Enrich] profiles RESEAUX SOCIAUX → {state.company_info.directors}")
    if state.company_info.directors:
        for director in state.company_info.directors:
            # Accepte Director ou simple str
            if isinstance(director, Director):
                name = f"{director.first_name} {director.last_name}".strip()
            else:
                name = str(director)
            linkedin_profiles = await tools.abrave_search(f"{name} LinkedIn", k=3)
            ctx += "\n### Profil Linkedin des dirigeants potentiels " + linkedin_profiles
            logger.info(f"Linkedin Search profiles: {linkedin_profiles}")
    else:
        # fallback : recherche générique sur la société
        ctx += "\n### Profil Linkedin des dirigeants potentiels " + await tools.abrave_search(f"{state.company} LinkedIn", k=3)

    return {"context": ctx, "company_info": state.company_info}


def build_enrich_graph():
    enrich = StateGraph(EnrichState)
    enrich.add_node("fetch_societe", fetch_societe)
    enrich.add_node("directors", directors)
    enrich.add_node("profiles", profiles)
    enrich.add_edge(START, "fetch_societe")
    enrich.add_edge("fetch_societe", "directors")
    enrich.add_edge("directors", "profiles")
    enrich.add_edge("profiles", END)
    return enrich.compile()
enrich_graph = build_enrich_graph()