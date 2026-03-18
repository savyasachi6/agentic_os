from typing import Optional
from docling.document_converter import DocumentConverter
from docling.datamodel.pipeline_options import PdfPipelineOptions
from agent_config import docling_settings

class DoclingParser:
    """
    Decoupled Docling Parser for complex document conversion.
    Wraps IBM's Docling DocumentConverter with configurable pipeline options.
    """
    
    def __init__(self, use_ocr: Optional[bool] = None):
        """
        Initializes the DoclingParser.
        
        Args:
            use_ocr: Boolean flag to enable/disable OCR. If None, defaults to docling_settings.
        """
        # Override with manual setting if provided, else use config
        ocr_enabled = use_ocr if use_ocr is not None else docling_settings.use_ocr
        
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = ocr_enabled
        
        self.converter = DocumentConverter(
            # Additional configuration can be injected here for tables, etc.
        )
        
    def convert_to_markdown(self, source_path: str) -> str:
        """
        Converts any document (PDF, DOCX, etc.) to structured Markdown.
        """
        result = self.converter.convert(source_path)
        return result.document.export_to_markdown()

    def get_document_object(self, source_path: str) -> DoclingDocument:
        """
        Returns the raw Docling document object for advanced metadata extraction.
        
        Args:
            source_path: Local path or URI to the document.
            
        Returns:
            A DoclingDocument instance.
        """
        return self.converter.convert(source_path).document
