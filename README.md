# LangChain Browser Email Agent

## Aperçu

Ce dépôt propose un **agent IA "browser‑email"** basé sur LangChain, LangGraph et le crawler Playwright *Crawl4AI*. Il automatise :

- la recherche d’informations d’entreprise via Brave Search
- l’extraction de contenu Web (JavaScript, PDF, vitesse humaine)
- la synthèse par LLM (OpenAI GPT‑4o ou modèle compatible)
- la génération d’un brouillon d’e‑mail personnalisable aux décideurs identifiés

Le tout est orchestré sous forme de **graphes LangGraph** facilement visualisables dans LangGraph Studio.

---

## Fonctionnalités clés

- **Recherche sémantique** avec Brave Search API
- **Crawling contextuel** (Crawl4AI + Playwright) pour récupérer des pages riches
- **Raffinement des données** (LLM « Critic ») avant envoi
- **Template d’e‑mail prêt à l’emploi** via SMTP Gmail
- **Observabilité** : intégration LangSmith pour le traçage
- **Extensibilité** : ajoutez rapidement de nouveaux nœuds, outils ou modèles

---

## Architecture

```
┌──────────────┐      ┌───────────────┐     ┌──────────────┐
│ Brave Search │──┐  │  Crawl4AI     │──┐  │  Gmail SMTP  │
└──────────────┘  │  └───────────────┘  │  └──────────────┘
                  ▼                     ▼
            ┌─────────────────────────────────┐
            │   LangGraph « email_chat »      │
            │ (agent/chat_graph.py)           │
            └─────────────────────────────────┘
                       │  (LLM calls)   ▲
                       ▼                │
                 OpenAI / autre modèle  │
```

Chaque étape (nœud) ajoute ou lit des champs dans l’état typé Pydantic (voir `agent/models.py`).

---

## Prérequis

| Outil                                     | Version minimale | Pourquoi ?                  |
| ----------------------------------------- | ---------------- | --------------------------- |
| Python                                    | **3.11**         | Compatibilité LangGraph CLI |
| Playwright                                | 1.44+            | Rendu de pages JS           |
| Git                                       | n’importe        | clonage du repo             |
| Brave Search API key                      | active           | requêtes Web                |
| OpenAI ou modèle équivalent               | clé valide       | génération LLM              |
| Compte Gmail + mot‑de‑passe d’application | facultatif       | envoi d’e‑mails             |

---

## Installation pas à pas

```bash
# 1. Clonez et créez un environnement isolé
$ git clone https://github.com/Stirito/langchain_browser_email_agent.git
$ cd langchain_browser_email_agent
$ python -m venv .venv  # Windows : .venv\Scripts\activate

# 2. Dépendances Python
$ pip install --upgrade pip
$ pip install -r requirements.txt

# 3. Installez les navigateurs Playwright (une seule fois)
$ playwright install
```

---

## Configuration des variables d’environnement

Copiez le modèle puis éditez‑le :

```bash
$ cp .env.example .env  # ou renommez‑le simplement
```

| Variable             | Description                                                                                         |
| -------------------- | --------------------------------------------------------------------------------------------------- |
| `OPENAI_API_KEY`     | Clé OpenAI ou de votre modèle compatible                                                            |
| `BRAVE_API_KEY`      | Clé d’API Brave Search ([https://developer.brave.com/search/](https://developer.brave.com/search/)) |
| `GMAIL_ADDRESS`      | Adresse Gmail expéditrice                                                                           |
| `GMAIL_APP_PASSWORD` | Mot‑de‑passe d’application (obligatoire si 2FA)                                                     |
| `LANGSMITH_*`        | (Optionnel) pour le traçage LangSmith                                                               |

> **Astuce :** ne versionnez jamais votre `.env`. Ajoutez‑le à votre `.gitignore`.

---

## Lancement rapide

```bash
# Fixe la boucle d’événement asynchrone spéciale Windows + lance LangGraph
$ python start_dev.py
```

Vous pourrez ensuite :

1. Entrer le nom d’une entreprise lorsque le prompt s’affiche.
2. L’agent collecte, résume et propose un brouillon d’e‑mail.
3. Valider l’envoi via SMTP si souhaité.

---

## Tester la stack Crawl4AI

```bash
$ python test_crawl4ai.py
```

Le test affiche un extrait markdown de la page cible pour vérifier que Playwright fonctionne.

---

## Personnalisation rapide

| Besoin                  | Fichier concerné                                                    | Point d’entrée                   |
| ----------------------- | ------------------------------------------------------------------- | -------------------------------- |
| Nouvel outil (API, DB…) | `agent/tools.py`                                                    | Déclarez une fonction + @tool    |
| Modifier le prompt LLM  | `agent/chat_graph.py` ou `agent/enrich_graph.py`                    | variable `prompt`                |
| Changer le modèle       | `agent/models.py` (config) ou passage du nom de modèle `ChatOpenAI` |                                  |
| Ajuster le workflow     | `agent/chat_graph.py`                                               | Méthodes async + edges LangGraph |

---

## Déploiement (optionnel)

- **Docker** : créez un `Dockerfile` multi‑stage reliant l’installation Playwright et exécutez `langgraph run`.
- **Serveur** : hébergez avec `uvicorn` si vous exposez un endpoint FastAPI autour du graphe.

---

## Dépannage courant

| Symptôme                                                                          | Cause probable            | Correctif                           |
| --------------------------------------------------------------------------------- | ------------------------- | ----------------------------------- |
| `playwright._impl._api_types.Error: BrowserType.launch: Executable doesn’t exist` | Navigateurs non installés | `playwright install chromium`       |
| `EnvironmentError: Veuillez définir BRAVE_API_KEY`                                | Variable manquante        | Vérifiez votre `.env`               |
| Échec SMTP                                                                        | Auth Gmail 2FA            | Créez un mot‑de‑passe d’application |

---

## Contribution

1. Fork / branch : `feature/<nom>`
2. Respectez la PEP 8 et formatez avec `black`.
3. Couverture : ajoutez un test pytest.
4. Ouvrez une Pull Request descriptive.

