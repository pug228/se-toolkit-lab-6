"""Regression tests for agent.py (Task 3) - System Agent with query_api tool.

These tests verify:
1. The agent uses read_file for source code questions
2. The agent uses query_api for data questions
3. The tool_calls array contains tool execution results
"""

import json
import subprocess
import sys
from pathlib import Path


def test_framework_question():
    """Test that the agent uses read_file for framework question.
    
    Question: "What framework does the backend use?"
    Expected:
    - read_file in tool_calls
    - FastAPI in answer
    """
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"

    result = subprocess.run(
        [sys.executable, str(agent_path), "What framework does the backend use?"],
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

    # Check that FastAPI is mentioned
    assert "fastapi" in data["answer"].lower(), f"Answer should mention FastAPI, got: {data['answer'][:100]}"

    assert "tool_calls" in data, "Missing 'tool_calls' field"
    assert isinstance(data["tool_calls"], list), "'tool_calls' should be an array"
    assert len(data["tool_calls"]) > 0, "'tool_calls' should not be empty"

    # Check that read_file was used
    tools_used = [tc.get("tool") for tc in data["tool_calls"]]
    assert "read_file" in tools_used, f"Expected 'read_file' in tool_calls, got: {tools_used}"


def test_items_count_question():
    """Test that the agent uses query_api for database count question.
    
    Question: "How many items are in the database?"
    Expected:
    - query_api in tool_calls
    - A number in the answer
    """
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"

    result = subprocess.run(
        [sys.executable, str(agent_path), "How many items are in the database?"],
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

    # Check that a number is mentioned (the item count)
    import re
    numbers = re.findall(r'\d+', data["answer"])
    assert len(numbers) > 0, f"Answer should contain a number, got: {data['answer'][:100]}"

    assert "tool_calls" in data, "Missing 'tool_calls' field"
    assert isinstance(data["tool_calls"], list), "'tool_calls' should be an array"
    assert len(data["tool_calls"]) > 0, "'tool_calls' should not be empty"

    # Check that query_api was used
    tools_used = [tc.get("tool") for tc in data["tool_calls"]]
    assert "query_api" in tools_used, f"Expected 'query_api' in tool_calls, got: {tools_used}"
