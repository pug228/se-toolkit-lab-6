# Task 2 Plan: The Documentation Agent

## Overview

Extend the agent from Task 1 with two tools (`read_file`, `list_files`) and implement an agentic loop that allows the LLM to call tools iteratively before producing a final answer.

## Tool Definitions

### `read_file`

**Purpose:** Read a file from the project repository.

**Parameters:**
- `path` (string, required) — relative path from project root

**Returns:** File contents as a string, or an error message if the file doesn't exist.

**Security:**
- Must resolve the path and ensure it stays within the project directory
- Reject any path containing `../` traversal attempts
- Use `Path.resolve()` to get the canonical path and verify it's under project root

### `list_files`

**Purpose:** List files and directories at a given path.

**Parameters:**
- `path` (string, required) — relative directory path from project root

**Returns:** Newline-separated listing of entries (files and directories).

**Security:**
- Same path traversal protection as `read_file`
- Only list directories within the project root

## Tool Schema (OpenAI Function Calling)

Tools will be defined as JSON schemas in the OpenAI-compatible format:

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read a file from the project repository",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Relative path from project root"
        }
      },
      "required": ["path"]
    }
  }
}
```

Similar schema for `list_files`.

## Agentic Loop

The loop will work as follows:

1. **Initialize** message history with system prompt + user question
2. **Call LLM** with messages and tool schemas
3. **Check response:**
   - If `tool_calls` present:
     - Execute each tool
     - Append tool results as `tool` role messages
     - Increment tool call counter
     - If counter >= 10, stop and return current answer
     - Go back to step 2
   - If no `tool_calls`:
     - Extract final answer from `choices[0].message.content`
     - Extract source reference (LLM should include it in the answer)
     - Return JSON output
4. **Output** JSON with `answer`, `source`, and `tool_calls` array

### Message Format

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After tool calls:
    {"role": "assistant", "content": None, "tool_calls": [...]},
    {"role": "tool", "tool_call_id": "...", "content": "..."},
]
```

### Tool Call Tracking

Each tool call in the output will have:
- `tool`: tool name (e.g., "read_file")
- `args`: the arguments passed (e.g., `{"path": "wiki/git-workflow.md"}`)
- `result`: the tool's return value

## System Prompt Strategy

The system prompt will instruct the LLM to:

1. Use `list_files` to discover files in the wiki directory
2. Use `read_file` to read relevant wiki files
3. Find the answer to the user's question
4. Include the source reference (file path + section anchor) in the final answer
5. Stop after providing the answer (don't call tools unnecessarily)

Example system prompt:

```
You are a documentation assistant. You have access to two tools:
- list_files: List files in a directory
- read_file: Read the contents of a file

To answer questions:
1. First use list_files to explore the wiki directory structure
2. Use read_file to read relevant files
3. Find the answer to the user's question
4. In your final answer, include:
   - A clear, concise answer
   - The source reference in format: wiki/filename.md#section-anchor

Maximum 10 tool calls per question.
```

## Path Security Implementation

```python
def validate_path(path: str) -> Path:
    """Validate that path is within project root."""
    project_root = Path(__file__).parent
    full_path = (project_root / path).resolve()
    
    # Check for path traversal
    if not str(full_path).startswith(str(project_root)):
        raise ValueError(f"Path traversal not allowed: {path}")
    
    return full_path
```

## Output Format

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "..."
    }
  ]
}
```

## Testing Strategy

Create 2 regression tests:

1. **Test merge conflict question:**
   - Question: "How do you resolve a merge conflict?"
   - Expected: `read_file` in tool_calls, `wiki/git-workflow.md` in source

2. **Test wiki listing question:**
   - Question: "What files are in the wiki?"
   - Expected: `list_files` in tool_calls

Tests will:
- Run agent.py as subprocess
- Parse JSON output
- Verify required fields exist
- Check that appropriate tools were called

## Files to Modify/Create

1. `plans/task-2.md` - This plan
2. `agent.py` - Add tools and agentic loop
3. `AGENT.md` - Update documentation
4. `tests/test_2.py` - 2 regression tests
