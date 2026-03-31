"""Tests for built-in tools and the tool registry using the new Pydantic Action Engine."""

import os
import tempfile
import pytest

from tools import (
    build_tool_registry,
    format_tool_descriptions,
    ReadFileAction,
    WriteFileAction,
    ListDirAction,
    RunShellAction,
    WorkspaceManager
)

def test_workspace_manager_sandbox():
    try:
        WorkspaceManager.sanitize_path("../../etc/passwd")
        assert False, "Should have raised PermissionError"
    except PermissionError:
        assert True

class TestReadFile:
    def test_reads_existing_file(self, tmp_path):
        # Override WorkspaceManager base for testing
        WorkspaceManager.BASE_DIR = str(tmp_path)
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        
        action = ReadFileAction(path="test.txt")
        result = action.run()
        assert result == "hello world"

class TestWriteFile:
    def test_writes_new_file(self, tmp_path):
        WorkspaceManager.BASE_DIR = str(tmp_path)
        action = WriteFileAction(path="subdir/out.txt", content="content here")
        result = action.run()
        assert "Written" in result
        
        path = str(tmp_path / "subdir" / "out.txt")
        assert os.path.exists(path)
        with open(path) as f:
            assert f.read() == "content here"

class TestListDir:
    def test_lists_contents(self, tmp_path):
        WorkspaceManager.BASE_DIR = str(tmp_path)
        (tmp_path / "a.txt").touch()
        (tmp_path / "b").mkdir()
        
        action = ListDirAction(path=".")
        result = action.run()
        assert "a.txt" in result
        assert "b" in result

class TestToolRegistry:
    def test_all_tools_registered(self):
        registry = build_tool_registry()
        # There are legacy PythonFnActions + basic actions so there are ~11 tools
        assert "read_file" in registry
        assert "write_file" in registry
        assert "skill_search" in registry

    def test_format_descriptions(self):
        registry = build_tool_registry()
        desc = format_tool_descriptions(registry)
        assert "read_file" in desc
        assert "Action:" in desc
