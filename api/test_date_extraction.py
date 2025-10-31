"""
Test Date Extraction
Quick verification that date extraction works
"""

import asyncio
import logging
from agent.date_parser import extract_article_date
from agent.brightdata_fetcher import fetch_url

logging.basicConfig(level=logging.INFO)

async def test_date_extraction():
    """Test date extraction on a few real URLs"""
    
    test_urls = [
        "https://www.moneycontrol.com/news/business/",
        "https://www.bloomberg.com/technology",
    ]
    
    print("\n" + "="*80)
    print("🧪 DATE EXTRACTION TEST")
    print("="*80 + "\n")
    
    for url in test_urls:
        print(f"\n📍 Testing: {url}")
        print("-" * 80)
        
        # Fetch HTML
        html = await fetch_url(url, timeout=20)
        if not html:
            print("❌ Failed to fetch")
            continue
        
        # Extract date
        date, confidence, method = await extract_article_date(html, url)
        
        if date:
            print(f"✅ Date extracted: {date.strftime('%Y-%m-%d')}")
            print(f"   Confidence: {confidence:.2f}")
            print(f"   Method: {method}")
        else:
            print(f"⚠️ No date found (method: {method})")
    
    print("\n" + "="*80)
    print("✅ Test complete")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(test_date_extraction())

