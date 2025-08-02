"""
Outils réutilisables : Brave Search, Crawl4AI, Gmail SMTP, Critic LLM.
"""
import os, ssl, smtplib, asyncio, requests, json
from email.mime.text import MIMEText    
from dotenv import load_dotenv
from crawl4ai import AsyncWebCrawler,BrowserConfig,CrawlerRunConfig,CacheMode
from crawl4ai.models import CrawlResult
from langchain_openai import ChatOpenAI
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter
from langchain_community.tools import BraveSearch
import os
from agent.models import Director
import logging
from pydantic import BaseModel, ValidationError
from typing import List
import re

logger = logging.getLogger("tools_logger")

load_dotenv()

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

# Configuration Windows-friendly pour Crawl4AI
if os.name == "nt":
    # Configuration spéciale pour Windows - évite les problèmes avec Playwright
    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=True,
        user_agent=DEFAULT_UA,
        ignore_https_errors=True,
        java_script_enabled=True,
        use_managed_browser=False,  # Évite les problèmes de subprocess sur Windows
    )
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        delay_before_return_html=5,
        excluded_tags=["nav","footer","script","style"]
    )
else:
    # Configuration standard pour Linux/Mac
    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=True,
        user_agent=DEFAULT_UA,
    )
    config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

# --- Variables d'environnement -------------------------------------------------
# Brave Search : on accepte deux noms de variables pour plus de souplesse.
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY") or os.getenv("BRAVE_SEARCH_API_KEY")
if not BRAVE_API_KEY:
    raise EnvironmentError(
        "Veuillez définir la variable d'environnement BRAVE_API_KEY ou BRAVE_SEARCH_API_KEY."
    )

# Gmail SMTP : on vérifie la présence des deux variables requises.
GMAIL_ADDR = os.getenv("GMAIL_ADDRESS")
GMAIL_PASS = os.getenv("GMAIL_APP_PASSWORD")
if not GMAIL_ADDR or not GMAIL_PASS:
    raise EnvironmentError(
        "Veuillez définir les variables GMAIL_ADDRESS et GMAIL_APP_PASSWORD pour envoyer des emails."
    )


def _brave_tool(k: int):
    """Instancie le tool BraveSearch avec le nombre de résultats voulu."""
    return BraveSearch.from_api_key(
        api_key=BRAVE_API_KEY,
        search_kwargs={"count": k},
    )

def brave_search(query: str, k: int = 5) -> str:
    """
    Renvoie les `k` premiers résultats au format Markdown
    (titre cliquable — URL) via le wrapper LangChain.
    """
    try:
        logger.info(f"Brave search: {query}")
        hits = _brave_tool(k).invoke(query)   
        logger.info(f"Brave search results: {hits}")
        # List[dict]
        if isinstance(hits, str):
            hits = json.loads(hits)
        if not hits:
            return "Aucun résultat trouvé."
        return "\n".join(f"- {h.get('title', 'Titre inconnu')} — {h.get('link', '#')}" for h in hits)
    except Exception as e:
        logger.error(f"Erreur lors de la recherche Brave pour '{query}': {e}")
        return "Erreur lors de la recherche."


# ---------------------------------------------------------------------------
# Version asynchrone pour éviter les appels bloquants depuis une boucle async
# ---------------------------------------------------------------------------


async def abrave_search(query: str, k: int = 5) -> str:
    """Equivalent asynchrone de `brave_search`.

    Utilise la méthode `.ainvoke()` du wrapper LangChain afin d'éviter de
    bloquer la boucle d'évènements. À employer avec `await` depuis un nœud
    LangGraph asynchrone.
    """
    try:
        logger.info(f"Brave search (async): {query}")
        hits = await _brave_tool(k).ainvoke(query)
        logger.info(f"Brave search results: {hits}")
        if isinstance(hits, str):
            hits = json.loads(hits)
        if not hits:
            return "Aucun résultat trouvé."
        return "\n".join(
            f"- {h.get('title', 'Titre inconnu')} — {h.get('link', '#')}" for h in hits
        )
    except Exception as e:
        logger.error(
            f"Erreur (async) lors de la recherche Brave pour '{query}': {e}"
        )
        return "Erreur lors de la recherche."

def _sync_crawl_markdown(url: str) -> str:
    """Version synchrone du crawling pour éviter les blocages."""
    import asyncio
    
    async def _do_crawl():
        try:
            # Utiliser la configuration Windows-friendly
            async with AsyncWebCrawler(
                config=browser_config,
                always_by_pass_cache=True,
                thread_safe=True
            ) as crawler:
                result = await crawler.arun(url, config=config)
                if result.status_code == 404:
                    logger.error(f"Page non trouvée: {url}")
                    return "Page non trouvée."
                return result.markdown
        except Exception as crawl_error:
            logger.warning(f"Crawl4AI a échoué pour {url}: {crawl_error}")
            # Fallback : simple requête HTTP si Crawl4AI échoue
            try:
                response = requests.get(url, headers={"User-Agent": DEFAULT_UA}, timeout=10)
                response.raise_for_status()
                return f"Contenu brut de {url}:\n\n{response.text[:5000]}..."
            except Exception as req_error:
                logger.error(f"Fallback requests a également échoué: {req_error}")
                return f"Impossible d'accéder à {url}: {str(crawl_error)}"
    
    try:
        # Créer une nouvelle boucle d'événements pour ce thread avec la policy correcte
        loop = asyncio.new_event_loop()
        if os.name == "nt":
            # Important : ProactorEventLoop (par défaut) supporte les subprocess ;
            # on veille à conserver cette policy plutôt que Selector.
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore[attr-defined]
            except AttributeError:
                # Version de Python plus ancienne (<3.8) : on laisse la policy courante
                pass
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_do_crawl())
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Erreur lors du crawling de {url}: {e}")
        return f"Erreur lors du crawling: {str(e)}"

def _sync_crawl_dirigeants(page_url: str) -> list[Director]:
    """
    Version synchrone (thread-safe) pour récupérer les dirigeants d'une page,
    inspirée de `_sync_crawl_markdown`. Elle exécute le crawler dans une nouvelle
    boucle d'événements afin d'éviter l'erreur `NotImplementedError` que l'on
    rencontre sous Windows lorsque `asyncio.create_subprocess_exec` est appelé
    depuis Playwright.
    """
    import asyncio

    async def _do_crawl_dirigeants() -> list[Director]:
        

        # 2. Lancer le crawler (Playwright) de façon Windows-friendly
        try:
            async with AsyncWebCrawler(
                config=browser_config,
                always_by_pass_cache=True,
                thread_safe=True,
            ) as crawler:
                result = await crawler.arun(page_url, config=config)
        except Exception as crawl_error:
            logger.error(f"Crawl4AI a échoué pour {page_url}: {crawl_error}")
            return []

        if not result.success:
            logger.error(result.error_message or "Crawl failed Dirigeants")
            return []

        markdown_text = result.markdown

        # --- 1. Isoler la section "Dirigeants" pour réduire les faux-positifs ---
        #   On capture tout ce qui se trouve après le titre `## Dirigeants` (ou variante
        #   d’orthographe/casse) jusqu’au prochain titre de niveau 2 (`##`) ou la fin
        #   du document. Cela évite de récupérer des éléments sans rapport comme
        #   « Publication du bilan », « Voir la fiche », etc.
        section_match = re.search(
            r"^##\s*Dirigeant[\w\s]*\n([\s\S]*?)(?=^##\s|\Z)",
            markdown_text,
            re.IGNORECASE | re.MULTILINE,
        )
        if section_match:
            markdown_text = section_match.group(1)

        logger.info(f"Crawl4AI results (section Dirigeants): {markdown_text}")

        directors: list[Director] = []

        # a) Noms sous forme de lien : [Jean Dupont](https://… "titre optionnel")
        #    - On capture uniquement l'URL (jusqu'à l'espace ou la fin de la parenthèse)
        link_pattern = re.compile(
            r"\[([A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ'’\- ]{2,})\]\((https?://[^\s\)]+)"  # groupe 1 = nom, groupe 2 = URL
        )
        for full_name, link in link_pattern.findall(markdown_text):
            prenom, *rest = full_name.strip().split()
            # On ignore les entrées non pertinentes (un seul mot ou mot-clé technique)
            if (not rest) or prenom.lower() in {"voir", "obtenir", "publication", "calculer"}:
                continue
            nom = " ".join(rest)
            try:
                clean_link = link.replace('</', '')
                directors.append(Director(first_name=prenom, last_name=nom, links=[clean_link]))
            except ValidationError:
                # Ignore les cas invalide (ex: caractères spéciaux inattendus)
                pass

        # b) Noms simples dans des listes : « - Jean Dupont »
        plain_pattern = re.compile(
            r"^[\*\-\+] +([A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ'’\- ]{2,})$",
            re.MULTILINE,
        )
        for full_name in plain_pattern.findall(markdown_text):
            prenom, *rest = full_name.strip().split()
            # On s'assure qu'il y a au moins un nom de famille et que le prénom n'est pas un mot-clé non pertinent
            if (not rest) or prenom.lower() in {"voir", "obtenir", "publication", "calculer"}:
                continue
            nom = " ".join(rest)
            try:
                directors.append(Director(first_name=prenom, last_name=nom))
            except ValidationError:
                pass

        # 5. Déduplication simple (prenom+nom+url) en conservant l’ordre
        seen = set()
        deduped: list[Director] = []
        for d in directors:
            key = (
                d.first_name.lower(),
                d.last_name.lower(),
                d.links[0] if d.links else "",
            )
            if key not in seen:
                seen.add(key)
                deduped.append(d)
        return deduped

    # 6. Exécution dans un thread avec une boucle d'événements dédiée
    try:
        loop = asyncio.new_event_loop()
        if os.name == "nt":
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore[attr-defined]
            except AttributeError:
                pass
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_do_crawl_dirigeants())
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Erreur lors du crawling de dirigeants {page_url}: {e}")
        return []


async def crawl_dirigeants(page_url: str) -> list[Director]:
    """
    Wrapper asynchrone qui exécute la version synchrone dans un thread afin
    d'isoler la création de la boucle d'événements et d'éviter les conflits
    avec la boucle principale de LangGraph.
    """
    try:
        return await asyncio.to_thread(_sync_crawl_dirigeants, page_url)
    except Exception as e:
        logger.error(f"Erreur (async) lors du crawling de dirigeants {page_url}: {e}")
        return []




async def crawl_markdown(url: str) -> str:
    """
    Crawl une page web et retourne le contenu en Markdown.
    Utilise asyncio.to_thread pour éviter les blocages lors de l'initialisation de AsyncWebCrawler.
    """
    try:
        return await asyncio.to_thread(_sync_crawl_markdown, url)
    except Exception as e:
        logger.error(f"Erreur lors du crawling de {url}: {e}")
        return f"Erreur lors du crawling: {str(e)}"


def send_gmail(to_email: str, subject: str, body: str) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, GMAIL_ADDR, to_email
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
        smtp.login(GMAIL_ADDR, GMAIL_PASS)
        smtp.sendmail(GMAIL_ADDR, [to_email], msg.as_string())

# === Critic : simple LLM « OK / NO » =========================================
_llm_critic = ChatOpenAI(model="gpt-4.1-nano")


def critic(llm_or_draft, draft: str | None = None) -> str:
    """Évalue un brouillon d'email.

    Utilisation flexible :
        critic(llm, draft)  # signature historique
        critic(draft)       # utilise un LLM par défaut
    Renvoie "YES" ou "NO" en majuscules.
    """

    # Permet d'appeler la fonction avec soit (llm, draft) soit (draft).
    if draft is None:
        draft = llm_or_draft
        llm = _llm_critic
    else:
        llm = llm_or_draft

    prompt = (
        "Réponds uniquement par YES ou NO.\n"
        "Le mail suivant est-il professionnel, clair et personnalisé ?\n\n"
        f"{draft}\n\nAnswer:"
    )
    return llm.invoke(prompt).content.strip().upper()

# ---------------------------------------------------------------------------
# Correctif Windows : l'event-loop par défaut (Proactor) ne gère pas
# asyncio.create_subprocess_exec → Playwright lève NotImplementedError.
# On force donc le SelectorEventLoop compatible subprocess.
# ---------------------------------------------------------------------------
if os.name == "nt":
    # On s'assure d'utiliser la ProactorEventLoop qui prend en charge les subprocess
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore[attr-defined]
        logger.info("WindowsProactorEventLoopPolicy appliquée (support subprocess Playwright).")
    except AttributeError:
        # Python < 3.8 : WindowsProactorEventLoopPolicy peut ne pas exister
        logger.warning("WindowsProactorEventLoopPolicy indisponible ; la policy courante est conservée.")

