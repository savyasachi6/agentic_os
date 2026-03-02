import pytest
import os
from unittest.mock import AsyncMock, patch, MagicMock
from projects.desktop_agent.main import run_organizer
from projects.desktop_agent.models import FileCategory
from agentos_core.lane_queue.models import Command, CommandType, CommandStatus

@pytest.mark.asyncio
async def test_full_workflow_execution(tmp_path):
    # Setup temp files
    scan_dir = tmp_path / "test_scan"
    scan_dir.mkdir()
    (scan_dir / "doc.pdf").write_text("dummy")
    
    # Mock LLMRouter to avoid background threads/network
    with patch("projects.desktop_agent.main.LLMRouter.get_instance") as mock_router_get:
        mock_router = MagicMock()
        mock_router_get.return_value = mock_router
        
        # Mock LLM categorization
        with patch("projects.desktop_agent.organizer.generate_structured_output", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = FileCategory(category="Documents", confidence=0.9, reasoning="Mocked")
            
            # Mock CommandStore to ignore DB
            with patch("agentos_core.lane_queue.store.get_db_connection"):
                 with patch("agentos_core.lane_queue.store.CommandStore.create_lane") as mock_lane:
                     mock_lane.return_value = MagicMock(id="lane-123")
                     with patch("agentos_core.lane_queue.store.CommandStore.enqueue") as mock_enqueue:
                         mock_enqueue.return_value = MagicMock(id="cmd-456")
                         
                         # Execute the run_organizer function (main logic)
                         await run_organizer(str(scan_dir))
                         
                         # Verification
                         mock_lane.assert_called_once()
                         mock_llm.assert_called_once()
                         mock_enqueue.assert_called_once()
                         
                         # Check payload
                         args, kwargs = mock_enqueue.call_args
                         assert kwargs["payload"]["src"].endswith("doc.pdf")
                         assert "Documents" in kwargs["payload"]["dest"]
