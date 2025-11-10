"""
Quick Azure OpenAI Connection Test
Run: python test_azure.py
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("=" * 60)
print("AZURE OPENAI CONNECTION TEST")
print("=" * 60)

# Check environment variables
azure_key = os.getenv("AZURE_OPENAI_KEY")
print(f"\n1. Environment Variables:")
print(f"   AZURE_OPENAI_KEY: {'✅ Set' if azure_key else '❌ Not set'}")
if azure_key:
    print(f"   Key (first 10 chars): {azure_key[:10]}...")

# Try importing config
try:
    from config import get_settings
    settings = get_settings()
    print(f"\n2. Config Settings:")
    print(f"   azure_openai_key: {'✅ Loaded' if settings.azure_openai_key else '❌ Not loaded'}")
    print(f"   azure_openai_endpoint: {settings.azure_openai_endpoint}")
    print(f"   azure_openai_api_version: {settings.azure_openai_api_version}")
    print(f"   azure_deployment_gpt4o: {settings.azure_deployment_gpt4o}")
    print(f"   azure_deployment_gpt4o_mini: {settings.azure_deployment_gpt4o_mini}")
except Exception as e:
    print(f"\n2. Config Settings: ❌ Error loading config: {e}")
    exit(1)

# Try creating LLM
try:
    from agent.llm_factory import get_smart_llm
    print(f"\n3. Creating LLM instance...")
    llm = get_smart_llm(temperature=0)
    print(f"   ✅ LLM instance created successfully")
    print(f"   Type: {type(llm).__name__}")
except Exception as e:
    print(f"\n3. Creating LLM: ❌ Error: {e}")
    exit(1)

# Try a simple API call
try:
    print(f"\n4. Testing API call...")
    print(f"   Sending test prompt to Azure OpenAI...")
    
    import asyncio
    
    async def test_call():
        response = await llm.ainvoke("Say 'Hello' in one word.")
        return response.content
    
    result = asyncio.run(test_call())
    print(f"   ✅ API call successful!")
    print(f"   Response: {result}")
    
except Exception as e:
    print(f"\n4. API Call: ❌ Error: {e}")
    print(f"\n   Detailed error: {type(e).__name__}: {str(e)}")
    import traceback
    print("\n   Full traceback:")
    traceback.print_exc()
    exit(1)

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED - Azure OpenAI is working correctly!")
print("=" * 60)

