import logging
from typing import List
from backend.utils.openai_client import client
from backend.services.ai_availability_service import acquire_ai_call_slot, get_ai_availability

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"

def get_embedding(text: str) -> List[float]:
    """
    Genereert een vector embedding voor de opgegeven tekst.
    Gebruikt het text-embedding-3-small model (1536 dimensies).
    """
    if not get_ai_availability()["available"]:
        return []
    if not client:
        logger.error("❌ Embedding Client gefaald: Geen OpenAI Client")
        return []
    if not acquire_ai_call_slot("embedding:single"):
        logger.warning("Embedding overgeslagen: centrale AI-limiet bereikt")
        return []

    try:
        # Normalisatie voor consistentie
        clean_text = text.replace("\n", " ").strip()
        
        response = client.embeddings.create(
            input=[clean_text],
            model=EMBEDDING_MODEL
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"❌ Fout bij genereren embedding: {e}")
        return []

def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Genereert embeddings voor een lijst van teksten (batch verwerking).
    """
    if not get_ai_availability()["available"]:
        return []
    if not client or not texts:
        return []
    if not acquire_ai_call_slot("embedding:batch"):
        logger.warning("Embedding-batch overgeslagen: centrale AI-limiet bereikt")
        return []

    try:
        clean_texts = [t.replace("\n", " ").strip() for t in texts]
        response = client.embeddings.create(
            input=clean_texts,
            model=EMBEDDING_MODEL
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        logger.error(f"❌ Fout bij batch genereren embeddings: {e}")
        return []
