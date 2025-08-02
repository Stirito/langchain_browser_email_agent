import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig

async def test_crawl4ai():
    """Test simple de crawl4ai sur un site d'exemple."""
    
    try:
        config = BrowserConfig(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            headless=True,
            browser_type="chromium"
        )
        
        # Test sur un site simple
        test_url = "https://httpbin.org/html"
        
        print(f"Test de crawl4ai sur : {test_url}")
        
        async with AsyncWebCrawler(config=config) as crawler:
            print("Crawler initialisé...")
            result = await crawler.arun(url=test_url)
            print("Crawling terminé !")
            
            print(f"Status: {result.status_code}")
            print(f"Title: {result.metadata.get('title', 'N/A')}")
            print(f"HTML length: {len(result.html) if result.html else 0}")
            print(f"Markdown length: {len(result.markdown) if result.markdown else 0}")
            
            if result.markdown:
                print("\n--- Début du Markdown ---")
                print(result.markdown[:500] + "..." if len(result.markdown) > 500 else result.markdown)
                print("--- Fin du Markdown ---")
            else:
                print("Aucun markdown généré")
                
    except Exception as e:
        print(f"ERREUR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_crawl4ai()) 