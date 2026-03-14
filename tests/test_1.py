"""Regression test for agent.py (Task 1).

Runs agent.py as a subprocess and verifies:
1. The output is valid JSON
2. The 'answer' field is present and non-empty
3. The 'tool_calls' field is present (should be empty array for Task 1)
"""

import json
import subprocess
import sys
from pathlib import Path


def test_agent_returns_valid_json():
    """Test that agent.py returns valid JSON with required fields."""
    # Path to agent.py in project root
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"

    # Run agent with a simple question
    result = subprocess.run(
        [sys.executable, str(agent_path), "What is 2+2?"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check exit code
    assert result.returncode == 0, f"Agent exited with code {result.returncode}: {result.stderr}"

    # Check stdout is not empty
    assert result.stdout.strip(), "Agent produced no output"

    # Parse JSON
    try:
        data = json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise AssertionError(f"Agent output is not valid JSON: {result.stdout[:200]}") from e

    # Check required fields
    assert "answer" in data, "Missing 'answer' field in output"
    assert data["answer"], "'answer' field is empty"
    assert isinstance(data["answer"], str), "'answer' should be a string"

    assert "tool_calls" in data, "Missing 'tool_calls' field in output"
    assert isinstance(data["tool_calls"], list), "'tool_calls' should be an array"
    assert len(data["tool_calls"]) == 0, "'tool_calls' should be empty for Task 1"
