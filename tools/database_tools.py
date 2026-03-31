from typing import Any, List, Dict
from tools.base_tool import BaseTool
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

class SkillSearchTool(BaseTool):
    """Safely retrieves available system capabilities without dynamic SQL."""
    
    name = "search_registered_skills"
    description = "Searches the internal system database for available capabilities and skills. Use this before attempting to write custom code for a capability."
    parameters_schema = {
        "type": "object",
        "properties": {
            "search_term": {
                "type": "string", 
                "description": "The semantic concept or specific name of the skill to find."
            },
            "category_filter": {
                "type": "string", 
                "description": "Optional category to filter results (e.g., 'productivity', 'system')."
            }
        },
        "required": ["search_term"]
    }

    def __init__(self, db_session: Session):
        self.db = db_session

    async def run(self, search_term: str, category_filter: str = None) -> List[Dict[str, Any]]:
        """Executes a secure, parameterized database query."""
        try:
            # Safe parameterized execution entirely removes SQL injection vulnerability
            sql = "SELECT name as skill_name, description FROM knowledge_skills WHERE description ILIKE :q"
            params = {"q": f"%{search_term}%"}
            
            if category_filter:
                sql += " AND skill_type = :cat"
                params["cat"] = category_filter
                
            sql += " LIMIT 10"
            
            results = self.db.execute(text(sql), params).fetchall()
            
            if not results:
                return [{"status": "failed", "message": f"No skills found matching '{search_term}'."}]
                
            # Accessing tuples returned by execute().fetchall()
            return [{"skill_name": r[0], "description": r[1]} for r in results]
            
        except Exception as e:
            logger.error(f"Database tool execution failed: {str(e)}")
            raise RuntimeError("Internal database execution error.")
