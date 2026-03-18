
import os
import sys
import uuid
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock dependencies BEFORE importing worker
import unittest
from unittest.mock import MagicMock, patch

# Mock the enrichment and search logic to avoid deep dependency chain collisions
sys.modules["agent_rag.ingestion.enrichment"] = MagicMock()
sys.modules["memory.rag_store"] = MagicMock()
sys.modules["memory.vector_store"] = MagicMock()

from agent_rag.ingestion.worker import ingest_document
from agent_rag.ingestion.docling_parser import DoclingParser
from agent_rag.ingestion.docling_chunker import DoclingChunker
from docling_core.types.doc import DoclingDocument

class TestDoclingIntegration(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.sample_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "sample_doc.md"))
        if not os.path.exists(cls.sample_path):
            with open(cls.sample_path, "w") as f:
                f.write("# Test Doc\n\nThis is a test document with a table.\n\n| A | B |\n|---|---|\n| 1 | 2 |")

    def test_docling_parser_instantiation(self):
        """Verify the parser can be instantiated (requires docling installed)."""
        try:
            parser = DoclingParser(use_ocr=False)
            self.assertIsNotNone(parser.converter)
            print("DoclingParser instantiated successfully.")
        except ImportError:
            self.skipTest("Docling not installed, skipping live instantiation test.")

    def test_docling_chunker_logic(self):
        """Verify the chunker properly maps Docling outputs to our internal schema."""
        try:
            from docling.chunking import HybridChunker
            chunker = DoclingChunker()
            
            # Mock a Docling result object
            mock_chunk = MagicMock()
            mock_chunk.text = "Sample chunk text"
            mock_chunk.meta = MagicMock()
            mock_chunk.meta.headings = ["Header 1"]
            mock_chunk.meta.export_json_dict.return_value = {"headings": ["Header 1"]}
            
            # We mock the internal docling chunker's chunk method
            with patch("agent_rag.ingestion.docling_chunker.HybridChunker.chunk", return_value=[mock_chunk]):
                results = chunker.chunk_document(MagicMock(spec=DoclingDocument))
                
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]["content"], "Sample chunk text")
                self.assertEqual(results[0]["heading"], "Header 1")
                self.assertEqual(results[0]["metadata"]["source"], "docling_hybrid_chunker")
                print("DoclingChunker logic verified with mocks.")
        except ImportError:
            self.skipTest("Docling not installed, skipping chunker test.")

    def test_worker_routing(self):
        """Test that ingest_document correctly routes to Docling when requested."""
        # Mocking the stores to avoid DB hits
        with patch("agent_rag.ingestion.worker.RagStore") as mock_rag, \
             patch("agent_rag.ingestion.worker.VectorStore") as mock_vec, \
             patch("agent_rag.ingestion.worker.DoclingParser") as mock_parser, \
             patch("agent_rag.ingestion.worker.DoclingChunker") as mock_chunker:
            
            # Set up mocks
            mock_rag_instance = mock_rag.return_value
            mock_rag_instance.save_document.return_value = "doc-123"
            mock_chunker_instance = mock_chunker.return_value
            mock_chunker_instance.chunk_document.return_value = [{"content": "test", "heading": "h1"}]
            
            # Run ingestion with explicit docling engine
            doc_id = ingest_document(self.sample_path, engine="docling")
            
            self.assertEqual(doc_id, "doc-123")
            mock_parser.assert_called_once()
            mock_chunker.assert_called_once()
            print("Worker routing to Docling verified.")

if __name__ == "__main__":
    unittest.main()
