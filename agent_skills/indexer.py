import os
import re
import json
import sys
import hashlib
import yaml
from typing import List, Dict, Tuple, Optional
from pathlib import Path


from agent_memory.vector_store import VectorStore
from agent_memory.db import get_db_connection
from agent_config import agent_settings


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


def chunk_markdown(content: str, min_tokens: int = 500, max_tokens: int = 800) -> List[Dict[str, str]]:
    """
    Split a Markdown document into chunks by H2/H3 boundaries.
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

    merged: List[Tuple[str, str]] = []
    for heading, body in sections:
        if merged and _estimate_tokens(merged[-1][1]) < min_tokens:
            prev_heading, prev_body = merged[-1]
            merged[-1] = (prev_heading, f"{prev_body}\n\n## {heading}\n{body}")
        else:
            merged.append((heading, body))

    chunks: List[Dict[str, str]] = []
    for heading, body in merged:
        tok = _estimate_tokens(body)
        if tok <= max_tokens:
            chunks.append({
                "heading": heading,
                "content": body,
                "chunk_type": _classify_chunk_type(heading),
            })
        else:
            paragraphs = re.split(r"\n{2,}", body)
            current = ""
            for para in paragraphs:
                candidate = f"{current}\n\n{para}".strip() if current else para
                if _estimate_tokens(candidate) > max_tokens and current:
                    chunks.append({
                        "heading": heading,
                        "content": current,
                        "chunk_type": _classify_chunk_type(heading),
                    })
                    current = para
                else:
                    current = candidate
            if current:
                chunks.append({
                    "heading": heading,
                    "content": current,
                    "chunk_type": _classify_chunk_type(heading),
                })

    return chunks


class SkillIndexer:
    def __init__(self, skills_dir: str = None):
        self.skills_dir = Path(skills_dir or agent_settings.skills_dir).resolve()
        self.vector_store = VectorStore()

    def _get_checksum(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _get_existing_checksum(self, path: str) -> Optional[str]:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT checksum FROM knowledge_skills WHERE path = %s", (path,))
                row = cur.fetchone()
                return row[0] if row else None

    def _parse_markdown_frontmatter(self, content: str) -> Tuple[Dict, str]:
        """Extract YAML frontmatter from start of file."""
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    meta = yaml.safe_load(parts[1]) or {}
                    return meta, parts[2].strip()
                except Exception:
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

    def index_skill_node(self, rel_path: str, is_dir: bool = False, file_content: str = None) -> bool:
        """Index a skill (file) or a folder category (directory)."""
        # Normalize path to forward slashes
        rel_path = rel_path.replace("\\", "/").rstrip("/")
        if rel_path.endswith(".md"):
            rel_path = rel_path[:-3] # Strip .md for semantic path

        abs_path = self.skills_dir / rel_path
        if not is_dir:
            # It's a file, so abs_path doesn't exist as a dir, we need to check the .md file
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
        
        checksum = self._get_checksum(content) if content else "dir-node"
        existing_checksum = self._get_existing_checksum(rel_path)
        
        if existing_checksum == checksum and checksum != "dir-node":
            # No print here to avoid flooding for skipped files
            return True

        # Metadata extraction
        metadata, body = self._parse_markdown_frontmatter(content or "")
        
        # For directories, look for sidecar metadata
        dir_meta = {}
        if is_dir:
            dir_meta = self._load_metadata(abs_path)
        
        combined_metadata = {**dir_meta, **metadata}
        
        # Name logic: use frontmatter name, else file/dir name
        node_name = abs_path.stem if not is_dir else abs_path.name
        name = combined_metadata.get("name", node_name)
        description = combined_metadata.get("description", "")
        tags = combined_metadata.get("tags", [])
        eval_lift = combined_metadata.get("eval_lift", 0.0)

        print(f"[indexer] Indexing {'dir' if is_dir else 'file'}: {rel_path} ({name})")

        # Upsert skill record
        skill_id = self.vector_store.upsert_skill(
            name=name,
            description=description,
            tags=tags,
            path=rel_path,
            checksum=checksum,
            eval_lift=eval_lift,
        )
        
        def serialize_meta(obj):
            if isinstance(obj, (dict, list)):
                if isinstance(obj, dict):
                    return {k: serialize_meta(v) for k, v in obj.items()}
                return [serialize_meta(x) for x in obj]
            import datetime
            if isinstance(obj, (datetime.date, datetime.datetime)):
                return obj.isoformat()
            return obj

        serializable_meta = serialize_meta(combined_metadata)
        
        # Update metadata_json
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE knowledge_skills SET metadata_json = %s WHERE id = %s",
                    (json.dumps(serializable_meta), skill_id)
                )
            conn.commit()

        # Only process chunks if there is non-frontmatter body
        if body.strip():
            self.vector_store.delete_skill_chunks(skill_id)
            chunks = chunk_markdown(
                body,
                min_tokens=agent_settings.chunk_min_tokens,
                max_tokens=agent_settings.chunk_max_tokens,
            )

            for chunk in chunks:
                token_count = _estimate_tokens(chunk["content"])
                self.vector_store.insert_skill_chunk(
                    skill_id=skill_id,
                    chunk_type=chunk["chunk_type"],
                    heading=chunk["heading"],
                    content=chunk["content"],
                    token_count=token_count,
                )
        return True

    def index_all(self):
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
                    # SKILL.md is special, it provides metadata for the directory node
                    if f.upper() == "SKILL.MD":
                        continue
                    
                    rel_f_path = os.path.join(rel_root, f) if rel_root else f
                    if self.index_skill_node(rel_f_path, is_dir=False):
                        count += 1

        print(f"[indexer] Done - indexed/synced {count} nodes")


if __name__ == "__main__":
    indexer = SkillIndexer()
    indexer.index_all()
