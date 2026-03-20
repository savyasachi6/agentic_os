"""
Unit tests for FractalCache: L1/L2 lookup, shared context, staleness validation,
and dependency cascade invalidation.
All database operations are mocked.
"""
import pytest
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Pre-mock dependencies
mock_config = MagicMock()
mock_config.model_settings = MagicMock()
mock_config.model_settings.embed_model = "test-embed"
mock_config.db_settings = MagicMock()
sys.modules["config"] = mock_config
sys.modules.setdefault("psycopg2", MagicMock())
sys.modules.setdefault("psycopg2.pool", MagicMock())
sys.modules.setdefault("pgvector", MagicMock())
sys.modules.setdefault("pgvector.psycopg2", MagicMock())
sys.modules.setdefault("ollama", MagicMock())

import agent_memory.cache as cache_module
from agent_memory.cache import FractalCache, SemanticCache


class TestFractalCache:

    def test_backward_compat_alias(self):
        """SemanticCache should be an alias for FractalCache."""
        assert SemanticCache is FractalCache

    def test_l1_exact_hit(self):
        """L1 exact hash match should return cached response."""
        with patch.object(cache_module, "get_db_connection") as mock_db, \
             patch.object(cache_module, "VectorStore"):

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            # L1 hit: (response_payload, staleness_version, is_current, content_hash)
            mock_cursor.fetchone.return_value = ('{"answer": "cached"}', 1, True, "hash123")

            cache = FractalCache()
            result = cache.get_cached_response("test query")

            assert result is not None
            assert result["strategy"] == "exact_cache"
            assert result["response"] == '{"answer": "cached"}'

    def test_l1_miss_l2_semantic_hit(self):
        """L1 miss, L2 semantic neighbor with valid staleness → cache hit."""
        with patch.object(cache_module, "get_db_connection") as mock_db, \
             patch.object(cache_module, "VectorStore") as MockVec:

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            MockVec.return_value.generate_embedding.return_value = [0.1] * 1536

            # Call sequence: L1 miss → L2 hit → staleness check
            mock_cursor.fetchone.side_effect = [
                None,  # L1 miss
                ('{"answer": "semantic"}', 0.98, "qh-neighbor", "hash456"),  # L2 hit
                (True,),  # staleness valid
            ]

            cache = FractalCache(similarity_threshold=0.95)
            result = cache.get_cached_response("semantic test query")

            assert result is not None
            assert result["strategy"] == "semantic_cache"
            assert result["similarity"] == 0.98

    def test_l2_stale_content_rejected(self):
        """L2 semantic hit with stale content should return None."""
        with patch.object(cache_module, "get_db_connection") as mock_db, \
             patch.object(cache_module, "VectorStore") as MockVec:

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            MockVec.return_value.generate_embedding.return_value = [0.1] * 1536

            mock_cursor.fetchone.side_effect = [
                None,  # L1 miss
                ('{"old": "data"}', 0.97, "qh-stale", "stale-hash"),  # L2 hit
                None,  # staleness check fails
            ]

            cache = FractalCache(similarity_threshold=0.95)
            result = cache.get_cached_response("stale query")
            assert result is None

    def test_shared_context_set_and_get(self):
        """Shared context should be settable and retrievable by hash."""
        with patch.object(cache_module, "get_db_connection") as mock_db, \
             patch.object(cache_module, "VectorStore"):

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            cache = FractalCache()

            # set should INSERT
            cache.set_shared_context("hash-abc", {"results": [{"id": "c1"}]})
            assert mock_cursor.execute.called

            # get should SELECT
            mock_cursor.fetchone.return_value = ({"results": [{"id": "c1"}]},)
            result = cache.get_shared_context("hash-abc")
            assert result is not None
            assert result["results"][0]["id"] == "c1"

    def test_invalidate_dependencies_cascade(self):
        """invalidate_dependencies should mark both parent and children stale."""
        with patch.object(cache_module, "get_db_connection") as mock_db, \
             patch.object(cache_module, "VectorStore"):

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            cache = FractalCache()
            cache.invalidate_dependencies("parent-hash-001")

            calls = mock_cursor.execute.call_args_list
            assert len(calls) >= 2  # children update + parent update

    def test_validate_staleness_fresh(self):
        """validate_staleness should return True for fresh content."""
        with patch.object(cache_module, "get_db_connection") as mock_db, \
             patch.object(cache_module, "VectorStore"):

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn

            mock_cursor.fetchone.return_value = (True,)

            cache = FractalCache()
            assert cache.validate_staleness("fresh-hash") is True
