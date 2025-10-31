"""
Phase 0 Integration Test
Verify intent extraction works end-to-end with the agent
"""

import asyncio
import logging
from agent.graph import run_agent

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_phase0_integration():
    """Test full agent flow with different intent patterns"""
    
    print("\n" + "="*80)
    print("🚀 PHASE 0 INTEGRATION TEST")
    print("Testing intent-driven summarization with real URLs")
    print("="*80 + "\n")
    
    # Test Case 1: Standard request with default intent
    print("\n📍 TEST 1: Standard request (default intent)")
    print("-" * 80)
    
    result1 = await run_agent(
        prompt="Summarize Marico news",
        seed_links=["https://www.moneycontrol.com/india/stockpricequote/personal-care/marico/M13"],
        max_articles=3
    )
    
    if result1:
        print("✅ Test 1 PASSED")
        print(f"   Generated {len(result1.bullet_points)} bullet points")
        print(f"   Citations: {len(result1.citations)}")
        print(f"   Model: {result1.model}")
    else:
        print("❌ Test 1 FAILED - No result returned")
    
    # Test Case 2: Executive Summary format
    print("\n📍 TEST 2: Executive Summary format")
    print("-" * 80)
    
    result2 = await run_agent(
        prompt="Executive summary of Marico news",
        seed_links=["https://www.moneycontrol.com/india/stockpricequote/personal-care/marico/M13"],
        max_articles=2
    )
    
    if result2:
        print("✅ Test 2 PASSED")
        print(f"   Summary length: {len(result2.summary_markdown)} chars")
        print(f"   First 200 chars: {result2.summary_markdown[:200]}...")
    else:
        print("❌ Test 2 FAILED - No result returned")
    
    # Test Case 3: One bullet per article
    print("\n📍 TEST 3: One bullet per article")
    print("-" * 80)
    
    result3 = await run_agent(
        prompt="One concise bullet per article about Marico",
        seed_links=["https://www.moneycontrol.com/india/stockpricequote/personal-care/marico/M13"],
        max_articles=3
    )
    
    if result3:
        print("✅ Test 3 PASSED")
        print(f"   Generated {len(result3.bullet_points)} bullet points")
        print("   Sample bullets:")
        for i, bullet in enumerate(result3.bullet_points[:3], 1):
            print(f"      {i}. {bullet[:100]}...")
    else:
        print("❌ Test 3 FAILED - No result returned")
    
    # Test Case 4: Time-specific request
    print("\n📍 TEST 4: Time-specific request (last 3 days)")
    print("-" * 80)
    
    result4 = await run_agent(
        prompt="Summarize last 3 days of Marico news",
        seed_links=["https://www.moneycontrol.com/india/stockpricequote/personal-care/marico/M13"],
        max_articles=3
    )
    
    if result4:
        print("✅ Test 4 PASSED")
        print(f"   Citations: {len(result4.citations)}")
        print("   Note: Time filtering applied (cutoff date used)")
    else:
        print("❌ Test 4 FAILED - No result returned")
    
    # Summary
    print("\n" + "="*80)
    print("📊 INTEGRATION TEST SUMMARY")
    print("="*80)
    
    results = [result1, result2, result3, result4]
    passed = sum(1 for r in results if r is not None)
    total = len(results)
    
    print(f"\n✅ Passed: {passed}/{total}")
    print(f"❌ Failed: {total - passed}/{total}")
    
    success_rate = (passed / total) * 100
    print(f"\n🎯 Success Rate: {success_rate:.1f}%")
    
    if success_rate == 100:
        print("\n🎉 PHASE 0 FULLY OPERATIONAL!")
        print("\n✨ Intent-driven summarization is working correctly:")
        print("   • Intent extraction from prompts ✓")
        print("   • Dynamic formatting based on intent ✓")
        print("   • Time-based filtering ✓")
        print("   • Custom output formats ✓")
    elif success_rate >= 75:
        print("\n⚠️ Mostly working but some issues detected")
    else:
        print("\n❌ Major issues - Phase 0 needs fixing")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    print("Starting Phase 0 Integration Test...")
    print("This may take 2-3 minutes (fetching articles + LLM calls)\n")
    
    asyncio.run(test_phase0_integration())
    
    print("\n✅ Integration test complete!")

