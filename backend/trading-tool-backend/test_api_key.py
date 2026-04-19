import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv("backend/.env")
key = os.getenv("OPENAI_API_KEY")

print(f"Testing key: {key[:15]}...{key[-5:]}")

try:
    client = OpenAI(api_key=key)
    client.models.list()
    print("✅ API Key is VALID!")
except Exception as e:
    print(f"❌ API Key is INVALID: {e}")
