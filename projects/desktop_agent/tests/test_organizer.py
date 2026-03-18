import os
import pytest
from projects.desktop_agent.organizer import FileOrganizer

def test_scan_returns_file_list(tmp_path):
    # Setup: Create some files in a temp directory
    d = tmp_path / "downloads"
    d.mkdir()
    f1 = d / "test1.txt"
    f1.write_text("hello")
    f2 = d / "test2.jpg"
    f2.write_bytes(b"fake image")
    
    # Subdirectory should be ignored for now or handled as part of categorization
    sub = d / "sub"
    sub.mkdir()
    
    organizer = FileOrganizer()
    files = organizer.scan(str(d))
    
    assert len(files) == 2
    assert any(f.endswith("test1.txt") for f in files)
    assert any(f.endswith("test2.jpg") for f in files)

def test_scan_empty_directory(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    
    organizer = FileOrganizer()
    files = organizer.scan(str(d))
    
    assert files == []

def test_scan_handles_non_existent_directory():
    organizer = FileOrganizer()
    with pytest.raises(FileNotFoundError):
        organizer.scan("non_existent_path_xyz")

from unittest.mock import AsyncMock, patch
from projects.desktop_agent.models import FileCategory

@pytest.mark.asyncio
async def test_categorize_calls_llm_with_correct_prompt():
    organizer = FileOrganizer()
    file_path = "/mock/path/invoice.pdf"
    
    # Ensure FileOrganizer has categorize method
    mock_category = FileCategory(category="Documents", confidence=0.95, reasoning="Found PDF extension")
    
    # The import path for generate_structured_output is in core.core.llm
    # We patch it directly in the organizer module to ensure the mock is caught.
    with patch("projects.desktop_agent.organizer.generate_structured_output", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_category
        
        result = await organizer.categorize(file_path)
        
        assert result.category == "Documents"
        # Check if prompt mentions the filename
        args, kwargs = mock_llm.call_args
        assert "invoice.pdf" in kwargs["prompt"]
        assert kwargs["response_model"] == FileCategory

from lane_queue.models import Command, CommandType, CommandStatus

def test_propose_move_enqueues_command():
    organizer = FileOrganizer()
    file_path = "/mock/path/invoice.pdf"
    category = "Documents"
    lane_id = "test-lane"
    
    with patch("core.lane_queue.store.CommandStore.enqueue") as mock_enqueue:
        mock_command = Command(
            id="cmd-123", 
            lane_id=lane_id, 
            seq=1, 
            cmd_type=CommandType.HUMAN_REVIEW,
            status=CommandStatus.PENDING
        )
        mock_enqueue.return_value = mock_command
        
        command_id = organizer.propose_move(file_path, category, lane_id=lane_id)
        
        assert command_id == "cmd-123"
        args, kwargs = mock_enqueue.call_args
        assert kwargs["cmd_type"] == CommandType.HUMAN_REVIEW
        assert kwargs["payload"]["src"] == file_path
        assert category in kwargs["payload"]["dest"]
