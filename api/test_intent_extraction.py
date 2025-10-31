"""
Test Intent Extraction
Verifies that user prompts are correctly parsed into structured intent
"""

import asyncio
import logging
from agent.intent_extractor import extract_intent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test cases covering different intent patterns
TEST_CASES = [
    {
        "name": "Time range: last 5 days",
        "prompt": "Summarize last 5 days of Marico news",
        "expected": {
            "time_range": "last_5_days",
            "time_range_days": 5,
            "output_format": "bullet_points",
            "bullets_per_article": 3
        }
    },
    {
        "name": "Format: executive summary",
        "prompt": "Executive summary of Apple earnings",
        "expected": {
            "output_format": "executive_summary",
            "bullets_per_article": 0,
            "include_executive_summary": True
        }
    },
    {
        "name": "Format: one bullet per article",
        "prompt": "One bullet per article about Tesla",
        "expected": {
            "output_format": "one_per_article",
            "bullets_per_article": 1
        }
    },
    {
        "name": "Time: today",
        "prompt": "Today's Microsoft news",
        "expected": {
            "time_range": "today",
            "time_range_days": 0
        }
    },
    {
        "name": "Article count: 5 articles",
        "prompt": "Summarize top 5 articles about Google",
        "expected": {
            "max_articles": 5
        }
    },
    {
        "name": "Focus: financial performance",
        "prompt": "Financial performance of Amazon in last week",
        "expected": {
            "focus_areas": ["financial_performance"],
            "time_range": "this_week"
        }
    },
    {
        "name": "Complex: detailed with specific timeframe",
        "prompt": "Detailed analysis of Meta last 14 days focus on market activity",
        "expected": {
            "output_format": "detailed",
            "time_range": "last_14_days",
            "time_range_days": 14,
            "bullets_per_article": 5,
            "focus_areas": ["market_activity"]
        }
    },
    {
        "name": "Format: concise",
        "prompt": "Brief overview of Netflix recent updates",
        "expected": {
            "output_format": "concise",
            "bullets_per_article": 2,
            "time_range": "last_5_days"
        }
    },
    {
        "name": "Custom bullets: 2 bullets per article",
        "prompt": "Give me 2 bullets per article for Adobe",
        "expected": {
            "bullets_per_article": 2
        }
    },
    {
        "name": "No specific requirements (defaults)",
        "prompt": "Marico news",
        "expected": {
            "time_range": "last_7_days",
            "time_range_days": 7,
            "output_format": "bullet_points",
            "bullets_per_article": 3,
            "max_articles": 3
        }
    }
]


async def test_intent_extraction():
    """Test intent extraction with various prompts"""
    
    print("\n" + "="*80)
    print("🧪 TESTING INTENT EXTRACTION")
    print("="*80 + "\n")
    
    results = []
    passed = 0
    failed = 0
    
    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"\n📍 Test {i}/{len(TEST_CASES)}: {test_case['name']}")
        print(f"   Prompt: \"{test_case['prompt']}\"")
        
        try:
            intent = await extract_intent(test_case['prompt'], max_articles=3)
            
            # Check expected values
            mismatches = []
            matches = []
            
            for key, expected_value in test_case['expected'].items():
                if key == "focus_areas":
                    # Special handling for focus areas
                    actual_value = [f.value for f in (intent.focus_areas or [])]
                    if set(actual_value) == set(expected_value):
                        matches.append(f"{key}: {actual_value}")
                    else:
                        mismatches.append(f"{key}: expected {expected_value}, got {actual_value}")
                else:
                    actual_value = getattr(intent, key, None)
                    if isinstance(actual_value, Enum):
                        actual_value = actual_value.value
                    
                    if actual_value == expected_value:
                        matches.append(f"{key}: {actual_value}")
                    else:
                        mismatches.append(f"{key}: expected {expected_value}, got {actual_value}")
            
            # Determine status
            if not mismatches:
                status = "✅ PASS"
                passed += 1
            else:
                status = "⚠️ PARTIAL"
                failed += 1
            
            print(f"   Result: {status}")
            print(f"   Confidence: {intent.confidence:.2f}")
            
            if matches:
                print(f"   ✓ Matched: {', '.join(matches[:3])}")
            
            if mismatches:
                print(f"   ✗ Mismatches:")
                for mismatch in mismatches:
                    print(f"      - {mismatch}")
            
            if intent.ambiguities:
                print(f"   ⚠️ Ambiguities: {intent.ambiguities}")
            
            results.append({
                "test": test_case['name'],
                "status": status,
                "intent": intent,
                "matches": len(matches),
                "mismatches": len(mismatches)
            })
            
        except Exception as e:
            print(f"   Result: ❌ FAIL")
            print(f"   Error: {e}")
            failed += 1
            results.append({
                "test": test_case['name'],
                "status": "❌ FAIL",
                "error": str(e)
            })
    
    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    
    print(f"\n✅ Passed: {passed}/{len(TEST_CASES)}")
    print(f"⚠️ Partial/Failed: {failed}/{len(TEST_CASES)}")
    
    success_rate = (passed / len(TEST_CASES)) * 100
    print(f"\n🎯 Success Rate: {success_rate:.1f}%")
    
    if success_rate >= 80:
        print("\n🎉 INTENT EXTRACTION WORKING WELL!")
    elif success_rate >= 60:
        print("\n⚠️ Decent but needs improvement")
    else:
        print("\n❌ Major issues - intent extraction not working well")
    
    print("\n" + "="*80)
    print("Key Metrics:")
    print("="*80)
    
    # Calculate avg confidence
    confidences = [r["intent"].confidence for r in results if "intent" in r]
    if confidences:
        avg_confidence = sum(confidences) / len(confidences)
        print(f"Average Confidence: {avg_confidence:.2f}")
    
    # Count LLM fallbacks
    llm_fallbacks = sum(1 for r in results if "intent" in r and r["intent"].confidence < 0.8)
    print(f"LLM Fallbacks Used: {llm_fallbacks}/{len(TEST_CASES)} ({(llm_fallbacks/len(TEST_CASES)*100):.1f}%)")
    
    return results


# Import Enum for comparison
from enum import Enum

if __name__ == "__main__":
    print("Starting Intent Extraction Tests...")
    print("This may take 20-30 seconds (includes LLM calls for ambiguous cases)\n")
    
    results = asyncio.run(test_intent_extraction())
    
    print("\n✅ Test complete! Review results above.")

