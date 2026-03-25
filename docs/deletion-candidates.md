# Deletion Candidates

| Module/File | Referenced By | Decision | Rationale |
| :--- | :--- | :--- | :--- |
| `agent_core/state_legacy.py` | None | **DELETE** | Legacy state management superseded by Graph/TreeStore. |
| `agent_core/antigravity.py` | None | **DELETE** | Experimental framework not used by current agents. |
| `agent_skills/` (root) | README only | **DELETE** | Empty except for an empty `mcp` folder. |
| `agent_core/setup_native.py` | None | **DELETE** | Superseded by standard environment setup. |
| `apply_migration_v4.py` (root) | None | **DELETE** | One-off migration script. |
| `skill.md` (root) | None | **DELETE** | Scratch/Template file. |
| `agent_core/agentos_tools_node/` | None | **MOVE** | C# project inside Python package. |
| `agent_core/migrate_and_seed.py` | None | **MOVE** | Utility script belongs in `dev/scripts/`. |
