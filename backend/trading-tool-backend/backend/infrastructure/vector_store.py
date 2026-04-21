import os
import logging
import json
try:
    import faiss
except ImportError:
    faiss = None
import numpy as np
from typing import List, Optional, Tuple, Dict
from sqlalchemy import text
from backend.utils.embedding_client import get_embedding

logger = logging.getLogger(__name__)

INDEX_PATH = "backend/static/ai/semantic_index.faiss"
MAPPING_PATH = "backend/static/ai/vector_mapping.json"
DIMENSION = 1536

class VectorStore:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(VectorStore, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_session=None):
        if self._initialized:
            return
        
        if faiss:
            self.index = faiss.IndexFlatIP(DIMENSION) # Cosine similarity (normalized)
        else:
            self.index = None
            logger.error("❌ FAISS is not installed. Vector store disabled.")

        self.mapping: Dict[int, str] = {} # FAISS ID -> query_hash
        self.db = db_session
        self._initialized = True
        
        # Zorg dat de map bestaat
        os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
        
        # Probeer te laden
        if os.path.exists(INDEX_PATH) and os.path.exists(MAPPING_PATH):
            self.load()
        else:
            logger.warning("⚠️ Vector index niet gevonden. Klaar voor rebuild.")

    def save(self):
        """Slaat de index en de mapping op naar schijf."""
        if not faiss or not self.index:
            return

        try:
            faiss.write_index(self.index, INDEX_PATH)
            with open(MAPPING_PATH, 'w') as f:
                json.dump(self.mapping, f)
            logger.info(f"💾 Vector index opgeslagen ({self.index.ntotal} items)")
        except Exception as e:
            logger.error(f"❌ Fout bij opslaan vector index: {e}")

    def load(self):
        """Laadt de index en de mapping van schijf."""
        if not faiss:
            return

        try:
            self.index = faiss.read_index(INDEX_PATH)
            with open(MAPPING_PATH, 'r') as f:
                self.mapping = {int(k): v for k, v in json.load(f).items()}
            logger.info(f"📂 Vector index geladen ({self.index.ntotal} items)")
        except Exception as e:
            logger.error(f"❌ Fout bij laden vector index: {e}")

    def add(self, query_hash: str, embedding: List[float]):
        """Voegt een embedding toe aan de index."""
        if not faiss or not self.index:
            return

        if not embedding or len(embedding) != DIMENSION:
            return

        # Normaliseer voor Cosine Similarity
        vector = np.array([embedding]).astype('float32')
        if faiss:
            faiss.normalize_L2(vector)
        
        # Check of we al een mapping hebben
        if query_hash in self.mapping.values():
            return

        vector_id = self.index.ntotal
        self.index.add(vector)
        self.mapping[vector_id] = query_hash
        
        # Direct opslaan (Safe mode)
        self.save()

    def search(self, embedding: List[float], top_k: int = 1) -> List[Tuple[str, float]]:
        """Zoekt naar de meest vergelijkbare items."""
        if not faiss or not self.index or self.index.ntotal == 0 or not embedding:
            return []

        vector = np.array([embedding]).astype('float32')
        if faiss:
            faiss.normalize_L2(vector)
        
        scores, indices = self.index.search(vector, top_k)
        
        results = []
        for i, score in enumerate(scores[0]):
            idx = int(indices[0][i])
            if idx in self.mapping:
                results.append((self.mapping[idx], float(score)))
        
        return results

    async def rebuild_from_db(self, db):
        """Bouwt de volledige index opnieuw op vanuit de database."""
        logger.info("🛠️ Rebuilding Vector Index from database...")
        
        stmt = text("SELECT query_hash, embedding FROM ai_response_cache WHERE embedding IS NOT NULL")
        res = await db.execute(stmt)
        rows = res.mappings().all()
        
        # Reset index
        if faiss:
            self.index = faiss.IndexFlatIP(DIMENSION)
        self.mapping = {}
        
        for row in rows:
            embedding = row['embedding']
            if embedding:
                self.add(row['query_hash'], embedding)
        
        logger.info(f"✅ Rebuild voltooid. {len(self.mapping)} items geïndexeerd.")
        self.save()

# Singleton helper
_vector_store = None
def get_vector_store(db=None):
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore(db)
    return _vector_store
