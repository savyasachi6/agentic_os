from typing import List, Dict, Any, Iterator
from docling.chunking import HybridChunker
from docling_core.types.doc import DoclingDocument
from agent_config import docling_settings

class DoclingChunker:
    """
    Docling Hybrid Chunker implementation for semantically aware segmentation.
    Respects document structure (tables, headers) while hitting token targets.
    """
    
    def __init__(self, tokenizer: str = None, max_tokens: int = None):
        """
        Initializes the DoclingChunker with internal HybridChunker.
        
        Args:
            tokenizer: Name of the tokenizer to use. Defaults to docling_settings.
            max_tokens: Maximum tokens per chunk. (Note: currently managed by tokenizer config in 2.x)
        """
        # In Docling 2.x, HybridChunker can take a tokenizer name directly in some versions,
        # or we wrap it. Based on docling_core source, it's a Pydantic model.
        
        self.chunker = HybridChunker(
            tokenizer=tokenizer or docling_settings.tokenizer,
            # max_tokens=max_tokens or docling_settings.chunk_size, 
            # Note: docling_core 2.x uses max_tokens inside the tokenizer object or as a param depending on version.
            # The model_validator in hybrid_chunker.py handles string tokenizers.
        )

    def chunk_document(self, dl_doc: DoclingDocument) -> List[Dict[str, Any]]:
        """
        Takes a DoclingDocument object and returns a list of dictionaries with content and metadata.
        
        Args:
            dl_doc: Pre-parsed DoclingDocument.
            
        Returns:
            List of dictionaries containing 'content', 'heading', and 'metadata'.
        """
        chunk_iter = self.chunker.chunk(dl_doc)
        
        processed_chunks = []
        for chunk in chunk_iter:
            # In Docling 2.x, 'chunk' is a DocChunk object.
            # It has 'text' and 'meta'.
            
            # Extract heading if available in metadata
            heading = None
            if hasattr(chunk, 'meta') and hasattr(chunk.meta, 'headings') and chunk.meta.headings:
                heading = chunk.meta.headings[-1] # Take the most specific heading
            
            processed_chunks.append({
                "content": chunk.text,
                "heading": heading,
                "metadata": {
                    "docling_meta": chunk.meta.export_json_dict() if hasattr(chunk.meta, 'export_json_dict') else {},
                    "source": "docling_hybrid_chunker"
                }
            })
            
        return processed_chunks
