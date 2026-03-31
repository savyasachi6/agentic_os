"""
rag/indexer.py
==============
Index skills into Postgres + pgvector.

Responsibilities:
- Walk the skills directory (from core.config.settings.skills_dir)
- Parse SKILL.md and other *.md files
- Extract YAML frontmatter + optional sidecar JSON metadata
- Chunk Markdown into semantically meaningful pieces
- Upsert skills and chunks into the database (with embeddings)
"""

import os
import re
import json
import hashlib
import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import yaml

from agent_core.config import settings
from db.queries.skills import upsert_skill, delete_skill_chunks, insert_skill_chunk, get_skill_metadata
from .embedder import Embedder


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~0.75 words per token for English."""
    return max(1, int(len(text.split()) / 0.75))


def _classify_chunk_type(heading: str) -> str:
    """Map a heading string to a chunk_type label."""
    h = heading.lower()
    if any(kw in h for kw in ["frontmatter", "metadata", "overview", "description"]):
        return "frontmatter"
    if any(kw in h for kw in ["example", "sample", "demo"]):
        return "examples"
    if any(kw in h for kw in ["script", "reference", "api"]):
        return "scripts_ref"
    return "instructions"


def chunk_markdown(
    content: str,
    min_tokens: int = 500,
    max_tokens: int = 800,
) -> List[Dict[str, str]]:
    """
    Split a Markdown document into chunks by H2/H3 boundaries, then
    merge or split sections to keep chunks within [min_tokens, max_tokens].
    """
    # Split on H2/H3 headers, keeping the header line
    pattern = re.compile(r"^(#{2,3}\s+.+)$", re.MULTILINE)
    parts = pattern.split(content)

    sections: List[Tuple[str, str]] = []
    if parts and not parts[0].strip().startswith("##"):
        preamble = parts.pop(0).strip()
        if preamble:
            sections.append(("Overview", preamble))

    i = 0
    while i < len(parts):
        heading = parts[i].strip().lstrip("#").strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if heading or body:
            sections.append((heading, body))
        i += 2

    # Merge small sections into previous ones
    merged: List[Tuple[str, str]] = []
    for heading, body in sections:
        if merged and _estimate_tokens(merged[-1][1]) < min_tokens:
            prev_heading, prev_body = merged[-1]
            merged[-1] = (prev_heading, f"{prev_body}\n\n## {heading}\n{body}")
        else:
            merged.append((heading, body))

    # Split large sections by paragraphs
    chunks: List[Dict[str, str]] = []
    for heading, body in merged:
        tok = _estimate_tokens(body)
        if tok <= max_tokens:
            chunks.append(
                {
                    "heading": heading,
                    "content": body,
                    "chunk_type": _classify_chunk_type(heading),
                }
            )
        else:
            paragraphs = re.split(r"\n{2,}", body)
            current = ""
            for para in paragraphs:
                candidate = f"{current}\n\n{para}".strip() if current else para
                if _estimate_tokens(candidate) > max_tokens and current:
                    chunks.append(
                        {
                            "heading": heading,
                            "content": current,
                            "chunk_type": _classify_chunk_type(heading),
                        }
                    )
                    current = para
                else:
                    current = candidate
            if current:
                chunks.append(
                    {
                        "heading": heading,
                        "content": current,
                        "chunk_type": _classify_chunk_type(heading),
                    }
                )

    return chunks


# ----------------------------------------------------------------------
# Skill indexer
# ----------------------------------------------------------------------

class SkillIndexer:
    """
    High-level indexer for skills.

    - Walks a skills directory
    - Indexes both directory nodes (categories) and Markdown files (skills)
    - Writes to knowledge_skills + related tables via db.queries.skills
    """

    def __init__(self, skills_dir: Optional[str] = None) -> None:
        # Default to the configured skills_dir if not provided
        self.skills_dir: Path = Path(skills_dir or settings.skills_dir).resolve()
        self.embedder = Embedder()

    # ---------- internal helpers ----------

    def _get_checksum(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _parse_markdown_frontmatter(
        self,
        content: str,
    ) -> Tuple[Dict, str]:
        """Extract YAML frontmatter from start of file."""
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    meta = yaml.safe_load(parts[1]) or {}
                    return meta, parts[2].strip()
                except Exception:
                    # fall through to treating the whole file as body
                    pass
        return {}, content.strip()

    def _load_metadata(self, skill_path: Path) -> Dict:
        """Load skill_meta.json (preferred) or fall back to plugin.json."""
        for filename in ("skill_meta.json", "plugin.json"):
            meta_path = skill_path / filename
            if meta_path.exists():
                with open(meta_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        return {}

    # ---------- public indexing methods ----------

    def index_skill_node(
        self,
        rel_path: str,
        is_dir: bool = False,
        file_content: Optional[str] = None,
    ) -> bool:
        """
        Index a skill (Markdown file) or a folder category (directory).

        Returns True if the node is up-to-date or successfully indexed.
        """
        # Normalize path to forward slashes
        rel_path = rel_path.replace("\\", "/").rstrip("/")
        if rel_path.endswith(".md"):
            rel_path = rel_path.removesuffix(".md")  # Strip .md for semantic path

        abs_path = self.skills_dir / rel_path
        if not is_dir:
            # For files, use <path>.md under skills_dir
            abs_path = self.skills_dir / f"{rel_path}.md"

        content = file_content
        if content is None:
            if is_dir:
                skill_file = abs_path / "SKILL.md"
                if skill_file.exists():
                    with open(skill_file, "r", encoding="utf-8") as f:
                        content = f.read()
            else:
                if abs_path.exists():
                    with open(abs_path, "r", encoding="utf-8") as f:
                        content = f.read()

        if not content and not is_dir:
            return False

        checksum = self._get_checksum(content) if content else "dir-node"

        # Metadata extraction
        metadata, body = self._parse_markdown_frontmatter(content or "")

        # For directories, look for sidecar metadata
        dir_meta: Dict = {}
        if is_dir:
            dir_meta = self._load_metadata(abs_path)

        combined_metadata = {**dir_meta, **metadata}

        # Name logic: use frontmatter name, else file/dir name
        node_name = abs_path.stem if not is_dir else abs_path.name
        name = combined_metadata.get("name", node_name)
        description = combined_metadata.get("description", "")
        aliases = combined_metadata.get("aliases", combined_metadata.get("tags", []))
        eval_lift = combined_metadata.get("eval_lift", 0.0)

        # Normalize name for DB slug
        normalized_name = name.lower().replace(" ", "_")
        skill_type = combined_metadata.get("skill_type", "framework")

        # --- Incremental Indexing Check ---
        existing = get_skill_metadata(normalized_name)
        if existing and existing["checksum"] == checksum:
            print(f"[indexer] Skipping {'dir' if is_dir else 'file'}: {rel_path} (unchanged)")
            return True

        print(f"[indexer] Indexing {'dir' if is_dir else 'file'}: {rel_path} ({name})")

        # Upsert skill record
        skill_id = upsert_skill(
            name=name,
            normalized_name=normalized_name,
            skill_type=skill_type,
            description=description,
            aliases=aliases,
            path=rel_path,
            checksum=checksum,
            eval_lift=eval_lift,
        )

        # Only process chunks if there is non-frontmatter body
        if body.strip():
            delete_skill_chunks(skill_id)
            chunks = chunk_markdown(
                body,
                min_tokens=settings.chunk_min_tokens,
                max_tokens=settings.chunk_max_tokens,
            )

            for chunk in chunks:
                token_count = _estimate_tokens(chunk["content"])
                # Generate embedding for the chunk content
                embedding, is_degraded = self.embedder.generate_embedding_sync(chunk["content"])
                
                insert_skill_chunk(
                    skill_id=skill_id,
                    chunk_type=chunk["chunk_type"],
                    heading=chunk["heading"],
                    content=chunk["content"],
                    token_count=token_count,
                    embedding=embedding
                )
        return True

    def _refresh_skill_relations(self) -> None:
        """Re-seed skill_relations graph after indexing completes."""
        from db.connection import get_db_connection
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO skill_relations
                            (source_skill_id, target_skill_id, relation_type, weight)
                        SELECT a.id, b.id, 'similar',
                               1 - (a.embedding <=> b.embedding)
                        FROM knowledge_skills a
                        CROSS JOIN knowledge_skills b
                        WHERE a.id < b.id
                          AND 1 - (a.embedding <=> b.embedding) > 0.75
                        ON CONFLICT DO NOTHING;
                    """)
                conn.commit()
            print("[indexer] skill_relations graph refreshed")
        except Exception as e:
            print(f"[indexer] skill_relations refresh failed (non-fatal): {e}")

    def index_all(self) -> None:
        """Recursively scan the skills directory and index everything."""
        if not self.skills_dir.exists():
            print(f"[indexer] Skills directory not found: {self.skills_dir}")
            return

        count = 0
        # Walk the directory
        for root, dirs, files in os.walk(str(self.skills_dir)):
            # Skip hidden directories like .git
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            rel_root = os.path.relpath(root, str(self.skills_dir))
            if rel_root == ".":
                rel_root = ""

            # Index current directory as a category node
            if rel_root:
                if self.index_skill_node(rel_root, is_dir=True):
                    count += 1

            # Index each markdown file as a skill node
            for f in files:
                if f.lower().endswith(".md") and not f.startswith("."):
                    # SKILL.md is special; it provides metadata for the directory node
                    if f.upper() == "SKILL.MD":
                        continue

                    rel_f_path = os.path.join(rel_root, f) if rel_root else f
                    if self.index_skill_node(rel_f_path, is_dir=False):
                        count += 1

        print(f"[indexer] Done - indexed/synced {count} nodes")
        self._refresh_skill_relations()


if __name__ == "__main__":
    indexer = SkillIndexer()
    indexer.index_all()
