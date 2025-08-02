import os

if os.name == "nt":
    import asyncio, logging
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
        logging.getLogger(__name__).info("WindowsSelectorEventLoopPolicy appliquée (agent.__init__).")
    except AttributeError:
        logging.getLogger(__name__).warning("Impossible d'appliquer WindowsSelectorEventLoopPolicy (attribut manquant) dans agent.__init__.") 