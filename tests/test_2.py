"""Regression tests for agent.py (Task 2) - Documentation Agent with tools.

These tests verify:
1. The agent uses tools (read_file, list_files) appropriately
2. The source field is populated with wiki file references
3. The tool_calls array contains tool execution results
"""

import json
import subprocess
import sys
from pathlib import Path


def test_merge_conflict_question():
    """Test that the agent uses read_file for merge conflict question.
    
    Question: "How do you resolve a merge conflict?"
    Expected:
    - read_file in tool_calls
    - wiki/git.md or similar in source
    """
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"

    result = subprocess.run(
        [sys.executable, str(agent_path), "How do you resolve a merge conflict?"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, f"Agent exited with code {result.returncode}: {result.stderr}"
    assert result.stdout.strip(), "Agent produced no output"

    # Parse JSON
    try:
        data = json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise AssertionError(f"Agent output is not valid JSON: {result.stdout[:200]}") from e

    # Check required fields
    assert "answer" in data, "Missing 'answer' field"
    assert data["answer"], "'answer' field is empty"

    assert "source" in data, "Missing 'source' field"
    assert data["source"], "'source' field is empty"
    assert "wiki/" in data["source"], f"Source should reference wiki file, got: {data['source']}"

    assert "tool_calls" in data, "Missing 'tool_calls' field"
    assert isinstance(data["tool_calls"], list), "'tool_calls' should be an array"
    assert len(data["tool_calls"]) > 0, "'tool_calls' should not be empty"

    # Check that read_file was used
    tools_used = [tc.get("tool") for tc in data["tool_calls"]]
    assert "read_file" in tools_used, f"Expected 'read_file' in tool_calls, got: {tools_used}"

    # Check source references git-related file
    assert "git" in data["source"].lower(), f"Source should reference git documentation, got: {data['source']}"


def test_wiki_listing_question():
    """Test that the agent uses list_files for wiki listing question.
    
    Question: "What files are in the wiki?"
    Expected:
    - list_files in tool_calls
    - wiki directory path in tool args
    """
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"

    result = subprocess.run(
        [sys.executable, str(agent_path), "What files are in the wiki?"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, f"Agent exited with code {result.returncode}: {result.stderr}"
    assert result.stdout.strip(), "Agent produced no output"

    # Parse JSON
    try:
        data = json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise AssertionError(f"Agent output is not valid JSON: {result.stdout[:200]}") from e

    # Check required fields
    assert "answer" in data, "Missing 'answer' field"
    assert data["answer"], "'answer' field is empty"

    assert "tool_calls" in data, "Missing 'tool_calls' field"
    assert isinstance(data["tool_calls"], list), "'tool_calls' should be an array"
    assert len(data["tool_calls"]) > 0, "'tool_calls' should not be empty"

    # Check that list_files was used
    tools_used = [tc.get("tool") for tc in data["tool_calls"]]
    assert "list_files" in tools_used, f"Expected 'list_files' in tool_calls, got: {tools_used}"

    # Check that list_files was called with wiki path
    list_files_calls = [tc for tc in data["tool_calls"] if tc.get("tool") == "list_files"]
    assert len(list_files_calls) > 0, "list_files should have been called"
    
    # At least one list_files call should have 'wiki' in the path
    wiki_paths = [tc for tc in list_files_calls if 'wiki' in tc.get("args", {}).get("path", "")]
    assert len(wiki_paths) > 0, f"list_files should be called with wiki path, got: {[tc.get('args') for tc in list_files_calls]}"
