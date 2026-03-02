from typing import List, Optional
import os
from projects.desktop_agent.models import FileCategory
from agentos_core.agent_core.llm import generate_structured_output
from agentos_core.lane_queue.store import CommandStore
from agentos_core.lane_queue.models import CommandType

class FileOrganizer:
    """
    Handles file scanning, categorization, and move proposals.
    """
    
    def __init__(self):
        self.store = CommandStore()
    
    def scan(self, directory: str) -> List[str]:
        """
        Scans the given directory and returns a list of absolute file paths.
        Only returns files, not subdirectories.
        """
        if not os.path.exists(directory):
            raise FileNotFoundError(f"Directory not found: {directory}")
            
        files = []
        for entry in os.scandir(directory):
            if entry.is_file():
                files.append(os.path.abspath(entry.path))
        return files

    async def categorize(self, file_path: str) -> FileCategory:
        """
        Uses the LLM to categorize the file based on its name and extension.
        """
        filename = os.path.basename(file_path)
        prompt = f"Categorize this file for organization: '{filename}'. Return the most appropriate folder name (e.g. Images, Documents, Code, Archives)."
        
        system_prompt = "You are a professional file organizer. Categorize files based on their extensions and names."
        
        category = await generate_structured_output(
            prompt=prompt,
            response_model=FileCategory,
            system_prompt=system_prompt
        )
        return category

    def propose_move(self, file_path: str, category: str, lane_id: str) -> str:
        """
        Proposes a move command and enqueues it in the specified lane for human review.
        """
        filename = os.path.basename(file_path)
        # Construct target path (just a recommendation for the human/tool to follow)
        dest_path = os.path.join(os.path.dirname(file_path), category, filename)
        
        payload = {
            "src": file_path,
            "dest": dest_path,
            "action": "move",
            "reason": f"Categorized as {category}"
        }
        
        command = self.store.enqueue(
            lane_id=lane_id,
            cmd_type=CommandType.HUMAN_REVIEW,
            payload=payload,
            tool_name="file_organizer"
        )
        return command.id
