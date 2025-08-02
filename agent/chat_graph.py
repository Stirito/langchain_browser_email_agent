"""
Graph « email_chat » compatible LangGraph Studio :
– State global = historique de messages + variables du projet
– Chaque étape ajoute ToolMessage / AIMessage
"""
from typing import List
import json, re
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
)
from langgraph.graph import StateGraph, START, END
from agent.models import ConvState
from agent import tools
from agent.enrich_graph import enrich_graph as enrich_subgraph
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from logging import getLogger
from uuid import uuid4
from agent.models import EnrichState

llm = ChatOpenAI(model="gpt-4.1", streaming=True)

logger = getLogger("main_graph_logger")


async def extract_intent(state: ConvState):
    """Analyse le dernier message utilisateur → société ciblée + besoin d'e-mail."""
    last_msg = state.messages[-1].content if state.messages else ""
    logger.info(f"Message utilisateur: {last_msg}")

    sys_prompt = (
        "Tu es un assistant d'extraction. À partir du message, renvoie JSON avec :\n"
        "company: nom de l'entreprise (ou vide) ;\n"
        "want_email: true si l'utilisateur veut recevoir un e-mail ;\n"
        "email: adresse fournie ou vide ;\n"
        "use_last: true si l'utilisateur parle DU rapport précédent ;\n"
        "note: texte à ajouter à la fin du rapport (ex: 'PS: ...') ou vide.\n"
        "Réponds seulement en JSON."
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", sys_prompt),
        ("user", "{msg}"),
    ])
    chain = prompt | llm
    resp = await chain.ainvoke({"msg": last_msg})
    try:
        data = json.loads(resp.content)
    except Exception:
        logger.warning(f"JSON parsing failed: {resp.content}")
        data = {"company": "", "want_email": False, "email": None, "use_last": False, "note": ""}

    state.extracted_company = data.get("company") or state.extracted_company
    state.want_email = bool(data.get("want_email"))
    state.user_email = data.get("email")
    state.use_last = bool(data.get("use_last"))
    state.extra_note = data.get("note", "")

    if state.use_last and state.last_report:
        ai_msg = AIMessage(content="Je vais réutiliser le rapport précédent…")
    else:
        ai_msg = AIMessage(content=f"Recherche d'informations sur {state.extracted_company} …")
    return {
        "extracted_company": state.extracted_company,
        "want_email": state.want_email,
        "user_email": state.user_email,
        "use_last": state.use_last,
        "extra_note": state.extra_note,
        "messages": state.messages + [ai_msg],
    }
# ---------- GRAPH ------------------------------------------------------------

async def enrich(state:ConvState):
    """Recherche Brave + Crawl4AI, stocke résumé dans ToolMessage."""
    company = state.extracted_company
    summary  = await tools.abrave_search(f"{company} produit dirigeant", k=3)
    logger.info(f"Summary: {summary}")
    # Cherche un lien LinkedIn dans les résultats
    linkedin_url = None
    for line in summary.splitlines():
        m = re.search(r'https?://[\w./-]*linkedin\.com/[^" ]+', line, re.I)
        if m:
            linkedin_url = m.group(0)
            break

    if linkedin_url:
        ln_md = await tools.crawl_markdown(linkedin_url)
        summary += f"\n\n### Profil LinkedIn\n{ln_md[:2000]}"
    join_company = company.replace(" ", "+")
    md = await tools.crawl_markdown(
        f"https://www.societe.com/cgi-bin/search?champs=siren&q={join_company}"
    )
    summary += "\n" + md
    state.context = summary
    state.messages.append(
        ToolMessage(
            content=summary,
            name="research",
            tool_call_id=str(uuid4()),  # identifiant unique requis
        )
    )
    # Pas besoin de renvoyer le nom du prochain nœud, l’arête g.add_edge("enrich", "draft") s’en charge.
    return {"context": summary}


async def draft_summary(state: ConvState):
    """Produit un résumé Markdown des infos collectées."""
    prompt = (
        f"### Résumé des informations sur {state.extracted_company}\n\n"
        f"### Informations collectées\n"
        f"{state.company_info}"
        f"### Contexte de recherche\n"
        f"{state.context}\n\n"
        "Rédige un rapport clair et concis."
        "Pour chaque dirigeant, rédige un paragraphe de 3-4 lignes sur son profil et son parcours. Si leurs profils sur leurs réseaux sociaux sont disponibles, inclure un lien vers leur profil. (doit être le bon profil précis des dirigeants)"
    )
    result = await llm.ainvoke(prompt)
    state.summary = result.content
    # Mémoire
    state.last_company = state.extracted_company
    state.last_report = state.summary
    return {"summary": state.summary}

# -- reuse_report node --------------------------------------------------------

def reuse_report(state: ConvState):
    state.summary = state.last_report
    return {"summary": state.summary}


def send_email(state: ConvState):
    if not state.user_email:
        logger.warning("Adresse e-mail manquante, envoi annulé.")
        return {}
    body = state.summary
    if state.extra_note:
        body += f"\n\n---\n{state.extra_note}"
    tools.send_gmail(
        to_email=state.user_email,
        subject=f"Rapport sur {state.extracted_company}",
        body=body,
    )
    logger.info("E-mail envoyé à l'utilisateur.")
    return {}


def send_chat(state: ConvState):
    content = state.summary
    if state.extra_note:
        content += f"\n\n---\n{state.extra_note}"
    msg = AIMessage(content=content)
    return {"messages": state.messages + [msg]}

def review(state:ConvState):
    verdict = tools.critic(llm, state.email)
    state.attempts += 1
    if verdict == "YES" or state.attempts >= 3:
        return {"is_need_review": True}
    return {"is_need_review": False}

def build_main_graph():
    g = StateGraph(ConvState)

    g.add_node("extract_intent", extract_intent)
    async def enrich_wrapper(state: ConvState):
        e_state = EnrichState(
            company=state.extracted_company or (state.last_company or ""),
            context=state.context,
            messages=state.messages,
        )
        result = await enrich_subgraph.ainvoke(e_state)
        # Fusionner les champs renvoyés par le sous-graphe ----------------------
        logger.info(f"Enrich result: {result}")

        # Contexte mis à jour
        state.context = result.get("context", state.context)

        # CompanyInfo enrichi (avec directeurs)
        state.company_info = result.get("company_info", state.company_info)

        # Liste à plat des directeurs pour usage ultérieur
        if state.company_info and state.company_info.directors:
            state.directors = state.company_info.directors

        logger.info(f"Enrich COMPANY INFO: {state.company_info}")
        return {
            "context": state.context,
            "company_info": state.company_info,
            "directors": state.directors,
        }

    g.add_node("enrich", enrich_wrapper)
    g.add_node("summary", draft_summary)
    g.add_node("reuse_report", reuse_report)
    g.add_node("send_email", send_email)
    g.add_node("send_chat", send_chat)

    g.add_edge(START, "extract_intent")
    # Choix : réutiliser rapport ?
    g.add_conditional_edges(
        "extract_intent",
        lambda s: s.use_last,
        {
            True: "reuse_report",
            False: "enrich",
        },
    )
    g.add_edge("reuse_report", "summary")
    g.add_edge("extract_intent", "enrich")  # cas False
    g.add_edge("enrich", "summary")
    # Choix canal
    g.add_conditional_edges(
        "summary",
        lambda s: s.want_email,
        {
            True: "send_email",
            False: "send_chat",
        },
    )

    g.add_edge("send_email", END)
    g.add_edge("send_chat", END)

    graph = g.compile()
    return graph

graph = build_main_graph()