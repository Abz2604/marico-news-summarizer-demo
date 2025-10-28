#!/usr/bin/env python3
"""
Test with stock page URL (stress test)
"""

import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)

from agent.graph import run_agent


async def test_stock_page():
    """Test with the stock quote page URL"""
    print("=" * 70)
    print("🧪 STRESS TEST: Stock Quote Page URL")
    print("=" * 70)
    
    # The problematic URL
    seed_url = "https://www.moneycontrol.com/india/stockpricequote/personal-care/marico/M13"
    
    print(f"\n📍 Seed URL: {seed_url}")
    print(f"💬 User Prompt: Summarize recent Marico news")
    print(f"\n⚡ Expected: Should find MARICO news, NOT world/general news")
    print()
    
    # Run the agent
    result = await run_agent(
        prompt="Create an executive summary with bullet points for recent Marico news",
        seed_links=[seed_url],
        max_articles=3
    )
    
    print()
    print("=" * 70)
    print("📊 RESULTS")
    print("=" * 70)
    
    if not result:
        print("\n❌ No result returned")
        return False
    
    print(f"\n✅ Summary generated successfully!")
    print(f"   Model: {result.model}")
    print(f"   Bullet points: {len(result.bullet_points)}")
    print(f"   Citations: {len(result.citations)}")
    
    print(f"\n📝 Summary (first 500 chars):")
    print(f"{'-' * 70}")
    print(result.summary_markdown[:500])
    print(f"{'-' * 70}")
    
    print(f"\n🔗 Article URLs:")
    for i, citation in enumerate(result.citations, 1):
        url = citation.get('url', 'No URL')
        print(f"  [{i}] {url}")
        
        # Check if it's Marico-specific
        if "marico" in url.lower():
            print(f"      ✅ Marico-specific")
        else:
            print(f"      ⚠️  Generic news (PROBLEM!)")
    
    # Validation
    marico_count = sum(1 for c in result.citations if "marico" in c.get('url', '').lower())
    
    print()
    print("=" * 70)
    if marico_count == len(result.citations):
        print("🎉 SUCCESS! All articles are Marico-specific!")
    elif marico_count > 0:
        print(f"⚠️  PARTIAL: {marico_count}/{len(result.citations)} articles are Marico-specific")
    else:
        print("❌ FAIL: No Marico-specific articles found!")
    print("=" * 70)
    
    return marico_count == len(result.citations)


if __name__ == "__main__":
    success = asyncio.run(test_stock_page())
    exit(0 if success else 1)

