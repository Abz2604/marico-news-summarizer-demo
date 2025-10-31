"""
Test Universal Context Extraction
Tests that LLM-based context extraction works for various sources
"""

import asyncio
import logging
from agent.context_extractor_llm import extract_context_with_llm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test URLs from different sources
TEST_CASES = [
    {
        "name": "MoneyControl (Baseline - Must Work)",
        "url": "https://www.moneycontrol.com/india/stockpricequote/personal-care/marico/M13",
        "prompt": "Summarize recent Marico news",
        "expected_company": "Marico",
        "expected_source": "stock_aggregator"
    },
    {
        "name": "Bloomberg Quote Page",
        "url": "https://www.bloomberg.com/quote/MRCO:IN",
        "prompt": "Latest Marico updates",
        "expected_company": "Marico",
        "expected_source": "financial_news"
    },
    {
        "name": "Reuters Company Page",
        "url": "https://www.reuters.com/companies/MRCO.NS",
        "prompt": "Marico news summary",
        "expected_company": "Marico",
        "expected_source": "financial_news"
    },
    {
        "name": "Yahoo Finance",
        "url": "https://finance.yahoo.com/quote/MRCO.NS",
        "prompt": "Recent news",
        "expected_company": "Marico",
        "expected_source": "stock_aggregator"
    },
    {
        "name": "Company Website",
        "url": "https://marico.com/investors/press-releases",
        "prompt": "Latest updates",
        "expected_company": "Marico",
        "expected_source": "official_company_site"
    },
    {
        "name": "TechCrunch (Generic News)",
        "url": "https://techcrunch.com/ai-startups",
        "prompt": "AI startups funding news",
        "expected_company": None,
        "expected_source": "tech_news"
    },
]


async def test_context_extraction():
    """Test context extraction with various sources"""
    
    print("\n" + "="*80)
    print("🧪 TESTING UNIVERSAL CONTEXT EXTRACTION")
    print("="*80 + "\n")
    
    results = []
    
    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"\n📍 Test {i}/{len(TEST_CASES)}: {test_case['name']}")
        print(f"   URL: {test_case['url']}")
        print(f"   Prompt: {test_case['prompt']}")
        print(f"   Expected: Company={test_case['expected_company']}, Source={test_case['expected_source']}")
        
        try:
            context = await extract_context_with_llm(
                url=test_case['url'],
                prompt=test_case['prompt']
            )
            
            # Check results
            company_match = context.get('company') == test_case['expected_company']
            source_match = context.get('source_type') == test_case['expected_source']
            
            status = "✅ PASS" if (company_match and source_match) else "⚠️ PARTIAL"
            
            print(f"   Result: {status}")
            print(f"   - Company: {context.get('company')} {'✓' if company_match else '✗'}")
            print(f"   - Source Type: {context.get('source_type')} {'✓' if source_match else '✗'}")
            print(f"   - Topic: {context.get('topic')}")
            print(f"   - Is Specific: {context.get('is_specific')}")
            print(f"   - Confidence: {context.get('confidence')}")
            print(f"   - Reasoning: {context.get('reasoning', 'N/A')[:100]}...")
            
            results.append({
                "test": test_case['name'],
                "status": status,
                "context": context
            })
            
        except Exception as e:
            print(f"   Result: ❌ FAIL")
            print(f"   Error: {e}")
            results.append({
                "test": test_case['name'],
                "status": "❌ FAIL",
                "error": str(e)
            })
    
    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for r in results if r['status'] == "✅ PASS")
    partial = sum(1 for r in results if r['status'] == "⚠️ PARTIAL")
    failed = sum(1 for r in results if r['status'] == "❌ FAIL")
    
    print(f"\n✅ Passed: {passed}/{len(TEST_CASES)}")
    print(f"⚠️ Partial: {partial}/{len(TEST_CASES)}")
    print(f"❌ Failed: {failed}/{len(TEST_CASES)}")
    
    success_rate = (passed / len(TEST_CASES)) * 100
    print(f"\n🎯 Success Rate: {success_rate:.1f}%")
    
    if success_rate >= 80:
        print("\n🎉 UNIVERSAL CONTEXT EXTRACTION WORKING!")
    elif success_rate >= 50:
        print("\n⚠️ Needs Improvement - Review partial/failed cases")
    else:
        print("\n❌ Major Issues - LLM context extraction not working well")
    
    return results


if __name__ == "__main__":
    print("Starting Universal Context Extraction Tests...")
    print("This will make LLM calls and may take 30-60 seconds\n")
    
    results = asyncio.run(test_context_extraction())
    
    print("\n" + "="*80)
    print("Test complete! Review results above.")
    print("="*80)

