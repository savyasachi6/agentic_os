import pytest
pytest.skip("Feature or Module 'rag.hyde' missing from source.", allow_module_level=True)
import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

from rag.hyde import HyDERetriever
from rag.rerankers.cross_encoder import CrossEncoderReranker
from rag.compression.compress import ContextualCompressor
from rag.indexing.hierarchy_builder import HierarchyBuilder
from rag.zoomer import DynamicZoomer

@pytest.fixture
def mock_chunk():
    chunk = MagicMock()
    chunk.id = "chunk-123"
    chunk.content = "This is a sample chunk content. It has multiple sentences. Context is important."
    chunk.score = 0.5
    chunk.metadata = {"parent_chunk_id": "parent-456"}
    return chunk

@pytest.mark.asyncio
async def test_hyde_logic():
    with patch("ollama.AsyncClient") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.chat = AsyncMock(return_value={
            "message": {"content": "Hypothetical answer text."}
        })
        
        retriever = HyDERetriever()
        with patch.object(retriever._vector_store, "generate_embedding_async", return_value=([0.1]*1536, False)):
            vec, is_fb = await retriever.generate_hyde_vector("What is the capital of France?")
            assert len(vec) == 1536
            assert is_fb is False

@pytest.mark.asyncio
async def test_cross_encoder_rerank(mock_chunk):
    with patch("ollama.AsyncClient") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.chat = AsyncMock(return_value={
            "message": {"content": "0.95"}
        })

        reranker = CrossEncoderReranker()
        reranked = await reranker.rerank("France capital", [mock_chunk])
        assert len(reranked) == 1
        assert reranked[0].score == 0.95

@pytest.mark.asyncio
async def test_compressor(mock_chunk):
    with patch("ollama.AsyncClient") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.chat = AsyncMock(return_value={
            "message": {"content": "Compressed text."}
        })

        compressor = ContextualCompressor()
        compressed = await compressor.compress("France capital", [mock_chunk])
        assert len(compressed) == 1
        assert compressed[0].content == "Compressed text."
        assert compressed[0].metadata["compressed"] is True


def test_hierarchy_builder():
    def mock_embed(text): return [0.1]*1536, False
    builder = HierarchyBuilder(embed_fn=mock_embed, parent_size=100, child_size=20)
    text = "This is a long text that should be split into parents and children. " * 5
    parents, children = builder.build("doc-1", text)
    assert len(parents) > 0
    assert len(children) > 0
    assert children[0]["parent_chunk_id"] == parents[0]["id"]

@pytest.mark.asyncio
async def test_zoomer(mock_chunk):
    zoomer = DynamicZoomer()
    # Test Zoom In
    sentences = zoomer.zoom_in(mock_chunk)
    assert len(sentences) == 3
    assert sentences[0] == "This is a sample chunk content."

    # Test Zoom Out (Mocking DB)
    with patch.object(zoomer._rag_store, "fetch_parent_chunk", return_value={"raw_text": "Parent text content"}):
        parent_text = await zoomer.zoom_out(mock_chunk)
        assert parent_text == "Parent text content"
