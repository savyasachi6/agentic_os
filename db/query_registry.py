"""
db/query_registry.py
====================
Centralized, typed registry for all SQL queries used by agents and retrieval.
Ensures schema safety and provides metadata for the bandit policy to select queries.
"""
import logging
from typing import List, Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel, Field

logger = logging.getLogger("agentos.db.registry")

class RetrievalRole(str, Enum):
    FACT = "fact"
    FILTER = "filter"
    CANDIDATE_GEN = "candidate_gen"
    ANALYTICS = "analytics"

class QuerySpec(BaseModel):
    name: str
    sql: str
    description: str
    params_schema: Optional[Dict[str, Any]] = None  # Pydantic-style schema JSON
    row_schema: Optional[Dict[str, Any]] = None     # Pydantic-style schema JSON
    allowed_agents: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    retrieval_role: Optional[RetrievalRole] = None

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Runtime validation of LLM-generated arguments (Phase 6)."""
        if not self.params_schema:
            return params
        
        # Dynamic Pydantic model creation (Simulation of Zod)
        from pydantic import create_model
        fields = {k: (Any, ...) for k in self.params_schema.keys()}
        Validator = create_model(f"{self.name}Params", **fields)
        
        try:
            validated = Validator(**params)
            return validated.model_dump()
        except Exception as e:
            raise ValueError(f"Parameter validation failed for {self.name}: {e}")

class QueryRegistry:
    _queries: Dict[str, QuerySpec] = {}

    @classmethod
    def register(cls, spec: QuerySpec):
        """Register a new query specification."""
        cls._queries[spec.name.strip().upper()] = spec
        logger.info(f"Registered query: {spec.name} ({len(cls._queries)} total)")

    @classmethod
    def get(cls, name: str) -> Optional[QuerySpec]:
        """Fetch a query spec by name (trimmed and uppered for robustness)."""
        if not name: return None
        return cls._queries.get(name.strip().upper())

    @classmethod
    def list_all(cls) -> List[QuerySpec]:
        """List all registered queries."""
        return list(cls._queries.values())

    @classmethod
    def audit_all(cls):
        """Phase 6: Startup Bootstrapping Audit. Verifies SQL vs Specs."""
        import re
        errors = []
        for name, spec in cls._queries.items():
            # Check for :param bindings in SQL
            found_params = re.findall(r":([a-zA-Z0-9_]+)", spec.sql)
            schema_params = spec.params_schema.keys() if spec.params_schema else []
            
            for p in found_params:
                if p not in schema_params:
                    errors.append(f"Query '{name}' references unknown parameter ': {p}' not in params_schema.")
        
        if errors:
            raise RuntimeError(f"Query Registry Audit Failed:\n" + "\n".join(errors))
        logger.info(f"Query Registry Audit Passed ({len(cls._queries)} queries validated).")

# --- Core Queries Registration ---

QueryRegistry.register(QuerySpec(
    name="FULL_INVENTORY_QUERY",
    description=(
        "Comprehensive skill and tool manifest. Use THIS when the user asks 'what can you do', "
        "'list your skills', or requests a full system summary. Do NOT use this for specific "
        "domain research. Returns skill counts grouped by type and an array of top skill names."
    ),
    retrieval_role=RetrievalRole.ANALYTICS,
    params_schema={}, # No parameters required
    tags=["inventory", "capability"],
    allowed_agents=["capability", "orchestrator"],
    sql="""
    SELECT
        ks.skill_type,
        COUNT(*) as skill_count,
        AVG(ks.eval_lift) as avg_lift,
        array_agg(ks.name ORDER BY ks.eval_lift DESC NULLS LAST) as skill_names
    FROM knowledge_skills ks
    WHERE ks.deleted_at IS NULL AND ks.skill_type != 'system_stats'
    GROUP BY ks.skill_type
    ORDER BY skill_count DESC;
    """
))

QueryRegistry.register(QuerySpec(
    name="TOOL_INVENTORY_QUERY",
    description=(
        "Detailed listing of available technical tools. Use this to identify specific "
        "agentic capabilities like 'web_search', 'python_sandbox', or 'browser_tools'. "
        "Provides risk levels and detailed descriptions for each tool."
    ),
    retrieval_role=RetrievalRole.ANALYTICS,
    params_schema={}, # No parameters required
    tags=["tools", "inventory"],
    allowed_agents=["capability", "orchestrator"],
    sql="""
    SELECT name, description, risk_level, tags
    FROM tools
    ORDER BY 
        CASE risk_level 
            WHEN 'low' THEN 1 
            WHEN 'normal' THEN 2 
            WHEN 'high' THEN 3 
            ELSE 4 END ASC, 
        name ASC;
    """
))

QueryRegistry.register(QuerySpec(
    name="SYSTEM_STATS_QUERY",
    description=(
        "High-level system health and quantitative metrics. Use this when the user "
        "asks for 'system status', 'how many documents are indexed', or 'graph connectivity stats'."
    ),
    retrieval_role=RetrievalRole.ANALYTICS,
    params_schema={}, # No parameters required
    tags=["stats", "health"],
    allowed_agents=["capability", "orchestrator"],
    sql="""
    SELECT
        (SELECT COUNT(*) FROM knowledge_skills WHERE deleted_at IS NULL) as total_skills,
        (SELECT COUNT(*) FROM skill_chunks) as total_chunks,
        (SELECT COUNT(*) FROM entity_relations) as total_kg_links,
        (SELECT COUNT(*) FROM tools) as total_tools;
    """
))
