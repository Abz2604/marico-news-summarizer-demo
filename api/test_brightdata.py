#!/usr/bin/env python3
"""
Test Bright Data Integration
"""

import asyncio
import sys
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)

from agent.brightdata_fetcher import fetch_url


async def test_brightdata():
    """Test that Bright Data can fetch MoneyControl"""
    
    print("="*60)
    print("Testing Bright Data Web Unlocker")
    print("="*60)
    print()
    
    # Test URL that was previously blocked
    test_url = "https://www.moneycontrol.com/news/tags/marico.html"
    
    print(f"📍 Target: {test_url}")
    print(f"🔄 Fetching with Bright Data...")
    print()
    
    try:
        html = await fetch_url(test_url, timeout=30)
        
        if html:
            print(f"✅ SUCCESS!")
            print(f"   HTML Length: {len(html):,} bytes")
            print()
            
            # Check content quality
            if len(html) > 10000:
                print(f"✅ Content looks substantial")
            elif len(html) > 2000:
                print(f"⚠️  Content is moderate ({len(html):,} bytes)")
            else:
                print(f"❌ Content is suspiciously short")
                return False
            
            # Check for block indicators
            if "Access Denied" in html:
                print(f"❌ Still getting 'Access Denied'")
                return False
            elif "Cloudflare" in html[:5000] and len(html) < 10000:
                print(f"❌ Cloudflare protection detected")
                return False
            else:
                print(f"✅ No block indicators found")
            
            # Show sample
            print()
            print("📄 Sample content (first 300 chars):")
            print("-" * 60)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator=" ", strip=True)[:300]
            print(text)
            print("-" * 60)
            print()
            
            print("🎉 Bright Data is working perfectly!")
            return True
        else:
            print("❌ Failed to fetch HTML")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_brightdata())
    sys.exit(0 if success else 1)

