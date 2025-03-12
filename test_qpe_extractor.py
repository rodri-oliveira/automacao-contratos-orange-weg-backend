import asyncio
from app.core.extractors.qpe_extractor import QPEExtractor

async def test_process_selected_files():
    extractor = QPEExtractor()
    result = await extractor.process_selected_files(["arquivo1.pdf", "arquivo2.pdf"])
    print("Resultado:", result)

if __name__ == "__main__":
    asyncio.run(test_process_selected_files()) 