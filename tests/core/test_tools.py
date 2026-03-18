"""Tests for built-in tools and the tool registry."""

import os
import tempfile
import pytest

from core.tools import (
    build_tool_registry,
    format_tool_descriptions,
    _read_file,
    _write_file,
    _list_dir,
    _run_shell,
)


class TestReadFile:
    def test_reads_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        result = _read_file(str(f))
        assert result == "hello world"

    def test_file_not_found(self):
        result = _read_file("/nonexistent/path/file.txt")
        assert "not found" in result.lower()

    def test_large_file_truncated(self, tmp_path):
        f = tmp_path / "big.txt"
        f.write_text("x" * 20_000)
        result = _read_file(str(f))
        assert "truncated" in result


class TestWriteFile:
    def test_writes_new_file(self, tmp_path):
        path = str(tmp_path / "subdir" / "out.txt")
        result = _write_file(path, "content here")
        assert "Written" in result
        assert os.path.exists(path)
        with open(path) as f:
            assert f.read() == "content here"


class TestListDir:
    def test_lists_contents(self, tmp_path):
        (tmp_path / "a.txt").touch()
        (tmp_path / "b").mkdir()
        result = _list_dir(str(tmp_path))
        assert "a.txt" in result
        assert "b" in result

    def test_not_a_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.touch()
        result = _list_dir(str(f))
        assert "Not a directory" in result


class TestRunShell:
    def test_echo(self):
        result = _run_shell("echo hello")
        assert "hello" in result

    def test_nonexistent_command(self):
        result = _run_shell("nonexistent_command_xyz_12345")
        # Should return stderr or error
        assert result  # not empty


class TestToolRegistry:
    def test_all_tools_registered(self):
        registry = build_tool_registry()
        expected = {"read_file", "write_file", "list_dir", "run_shell", "skill_search", "rag_query"}
        assert set(registry.keys()) == expected

    def test_format_descriptions(self):
        registry = build_tool_registry()
        desc = format_tool_descriptions(registry)
        assert "read_file" in desc
        assert "Action:" in desc
