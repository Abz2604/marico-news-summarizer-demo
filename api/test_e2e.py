#!/usr/bin/env python3
"""
End-to-end test of the agent flow
"""

import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)

from agent.graph import run_agent


async def test_marico_flow():
    """Test the full Marico summarization flow"""
    print("=" * 60)
    print("🚀 Testing End-to-End Agent Flow")
    print("=" * 60)
    
    # Test URL
    seed_url = "https://www.moneycontrol.com/company-article/marico/news/M13"
    
    print(f"\n📍 Seed URL: {seed_url}")
    print(f"📊 Requesting 3 articles")
    print(f"🎯 Asking for executive summary")
    print()
    
    # Run the agent
    result = await run_agent(
        prompt="Create an executive summary with bullet points for recent Marico news",
        seed_links=[seed_url],
        max_articles=3
    )
    
    print()
    print("=" * 60)
    print("📊 RESULTS")
    print("=" * 60)
    
    if not result:
        print("\n❌ No result returned")
        return False
    
    print(f"\n✅ Summary generated successfully!")
    print(f"   Model: {result.model}")
    print(f"   Bullet points: {len(result.bullet_points)}")
    print(f"   Citations: {len(result.citations)}")
    
    print(f"\n📝 Summary:")
    print(f"{'-' * 60}")
    print(result.summary_markdown)
    print(f"{'-' * 60}")
    
    print(f"\n🔗 Citations:")
    for i, citation in enumerate(result.citations, 1):
        print(f"  [{i}] {citation.get('title', 'No title')}")
        print(f"      {citation.get('url', 'No URL')}")
    
    print("\n" + "=" * 60)
    print("🎉 TEST COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_marico_flow())
    exit(0 if success else 1)

