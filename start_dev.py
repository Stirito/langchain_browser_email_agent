"""
Script de démarrage pour Windows qui fixe l'event loop policy avant LangGraph.
"""
import os
import sys
import asyncio
import subprocess

def fix_windows_event_loop():
    """Applique la policy Windows pour éviter l'erreur NotImplementedError avec Playwright."""
    if os.name == "nt":
        try:
            # Forcer la policy Proactor (nécessaire pour les subprocess Playwright)
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

            # On garde la variable d'environnement Playwright mais on retire celle d'asyncio # Désactive le téléchargement auto des navigateurs

            print("✅ WindowsProactorEventLoopPolicy appliquée (support subprocess Playwright).")
        except AttributeError:
            print("❌ Impossible d'appliquer WindowsSelectorEventLoopPolicy (Python trop ancien).")
            sys.exit(1)

def main():
    # Fixer l'event loop pour Windows
    fix_windows_event_loop()
    
    # Lancer LangGraph dev avec les arguments passés
    cmd = ["langgraph", "dev"] + sys.argv[1:]
    
    print(f"🚀 Démarrage de LangGraph: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur lors du démarrage de LangGraph: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n🛑 Arrêt de LangGraph...")
        sys.exit(0)

if __name__ == "__main__":
    main() 