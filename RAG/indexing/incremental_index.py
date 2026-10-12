from collections.abc import Sequence

from RAG.indexing.embedder import Embedder
from RAG.indexing.metadata_index import EmbeddingCache
from RAG.models import Chunk
from RAG.vectorstore.base import VectorStore


class IncrementalIndexer:
	def __init__(
		self,
		embedder: Embedder,
		vector_store: VectorStore,
		embedding_cache: EmbeddingCache,
		batch_size: int = 64,
	) -> None:
		self._embedder = embedder
		self._vector_store = vector_store
		self._embedding_cache = embedding_cache
		self._batch_size = batch_size

	def index(self, chunks: Sequence[Chunk]) -> int:
		indexed = 0
		for start in range(0, len(chunks), self._batch_size):
			batch = chunks[start : start + self._batch_size]
			keys = self._embedding_cache.keys_for([chunk.text for chunk in batch])
			cached = self._embedding_cache.get_many(keys)
			vectors: list[list[float] | None] = [cached.get(key) for key in keys]
			missing_positions = [index for index, vector in enumerate(vectors) if vector is None]
			if missing_positions:
				missing_texts = [batch[index].text for index in missing_positions]
				computed = self._embedder.embed_documents(missing_texts)
				if len(computed) != len(missing_positions):
					raise ValueError("Embedder must return one vector per input text")
				for position, vector in zip(missing_positions, computed):
					vectors[position] = vector
				self._embedding_cache.set_many(
					{keys[position]: vectors[position] for position in missing_positions}
				)
			complete_vectors = [vector for vector in vectors if vector is not None]
			self._vector_store.upsert(batch, complete_vectors)
			indexed += len(batch)
		return indexed
