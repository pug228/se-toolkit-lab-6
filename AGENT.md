# Agent Architecture

## Overview

This agent is a CLI tool that connects to an LLM (Large Language Model) with **tools** and an **agentic loop**. The agent can read project files, list directories, and answer questions based on the project documentation.

## LLM Provider

**Provider:** Qwen Code API (self-hosted via qwen-code-oai-proxy)

**Model:** `qwen3-coder-plus`

**Why Qwen Code:**

- 1000 free requests per day
- Works from Russia without restrictions
- No credit card required
- OpenAI-compatible API with tool calling support

## Architecture

### Input/Output

**Input:** A question passed as the first command-line argument:

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

**Output:** A single JSON line to stdout:

```json
{
  "answer": "When Git encounters conflicting changes during a merge...",
  "source": "wiki/git.md#merge-conflict",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git.md"},
      "result": "..."
    }
  ]
}
```

### Components

#### 1. Environment Loading (`load_env`)

- Reads `.env.agent.secret` in the project root
- Parses `LLM_API_KEY`, `LLM_API_BASE`, and `LLM_MODEL`
- Exits with error if file is missing or credentials are incomplete

#### 2. CLI Argument Parsing (`main`)

- Uses `sys.argv` to get the question from command line
- Validates that a question was provided
- Exits with usage message if no argument given

#### 3. Tools

The agent has two tools that are exposed to the LLM via function calling schemas:

**`read_file`**

- **Purpose:** Read a file from the project repository
- **Parameters:** `path` (string) — relative path from project root
- **Returns:** File contents as a string, or an error message
- **Security:** Validates path to prevent directory traversal (`../`)

**`list_files`**

- **Purpose:** List files and directories at a given path
- **Parameters:** `path` (string) — relative directory path from project root
- **Returns:** Newline-separated listing of entries
- **Security:** Validates path to prevent directory traversal (`../`)

**Path Security Implementation:**

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

#### 4. LLM API Client (`call_llm`)

- Uses `httpx` to make HTTP POST requests
- Endpoint: `{LLM_API_BASE}/chat/completions`
- Headers: `Authorization: Bearer {LLM_API_KEY}`, `Content-Type: application/json`
- Body: OpenAI-compatible format with `model`, `messages`, and `tools`
- Timeout: 60 seconds
- Handles errors: timeout, HTTP errors, connection errors

#### 5. Agentic Loop (`run_agentic_loop`)

The agentic loop enables the LLM to iteratively call tools before producing a final answer:

```
Question → LLM → tool call? → yes → execute tool → back to LLM
                  │
                  no
                  │
                  ↓
             JSON output
```

**Loop Steps:**

1. **Initialize** message history with system prompt + user question
2. **Call LLM** with messages and tool schemas
3. **Check response:**
   - If `tool_calls` present:
     - Execute each tool function
     - Append tool results as `tool` role messages
     - Increment tool call counter
     - If counter >= 10, stop and return current answer
     - Go back to step 2
   - If no `tool_calls`:
     - Extract final answer from `choices[0].message.content`
     - Extract source reference
     - Return JSON output
4. **Output** JSON with `answer`, `source`, and `tool_calls` array

**Message Format:**

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After tool calls:
    {"role": "assistant", "content": "", "tool_calls": [...]},
    {"role": "tool", "tool_call_id": "...", "content": "..."},
]
```

**Maximum Tool Calls:** 10 per question (prevents infinite loops)

#### 6. System Prompt

The system prompt instructs the LLM how to use tools effectively:

```
You are a documentation assistant with access to two tools:
- list_files: List files in a directory
- read_file: Read the contents of a file

To answer questions about the project documentation:
1. Use list_files to explore the wiki directory structure
2. Use read_file to read relevant wiki files
3. Find the answer to the user's question in the wiki files
4. In your final answer, provide:
   - A clear, concise answer based on what you found
   - The source reference in format: wiki/filename.md#section-anchor

Rules:
- Make only ONE tool call at a time
- Always wait for the tool result before making another call
- When you find the answer, stop calling tools and provide the final answer
- Maximum 10 tool calls per question
```

#### 7. Source Extraction (`extract_source`)

Extracts the source reference from:

1. The answer text (looking for patterns like `wiki/filename.md#section`)
2. The tool calls (if a `read_file` was used on a wiki file)

#### 8. Output

- Prints valid JSON to stdout
- All debug/logging output goes to stderr (using `print(..., file=sys.stderr)`)
- Human-readable answer also printed to stderr for interactive use

### Data Flow

```
Command line argument → Load env config → Initialize agentic loop →
  [Call LLM → Check for tool calls → Execute tools → Repeat] →
Extract answer + source → Output JSON to stdout
```

## Configuration

Create `.env.agent.secret` in the project root:

```bash
cp .env.agent.example .env.agent.secret
```

Fill in your credentials:

```env
LLM_API_KEY=your-api-key-here
LLM_API_BASE=http://<your-vm-ip>:<port>/v1
LLM_MODEL=qwen3-coder-plus
```

> **Note:** `.env.agent.secret` is gitignored. Never commit API keys.

## Usage

```bash
# Run with a question
uv run agent.py "How do you resolve a merge conflict?"

# Example output
{
  "answer": "When Git encounters conflicting changes...",
  "source": "wiki/git.md#merge-conflict",
  "tool_calls": [...]
}
```

## Error Handling

- **Missing credentials:** Exits with code 1, prints error to stderr
- **API timeout:** Exits with code 1 after 60 seconds
- **API error:** Exits with code 1, prints status code and response to stderr
- **Connection error:** Exits with code 1, prints error to stderr
- **Invalid response format:** Exits with code 1, prints error to stderr
- **Path traversal attempt:** Returns error message in tool result (doesn't crash)
- **Maximum tool calls reached:** Returns partial answer with tools used so far

## Testing

Run the regression tests:

```bash
# Task 2 tests
uv run pytest tests/test_2.py -v

# All tests
uv run pytest tests/ -v
```

Tests verify:

1. Agent produces valid JSON output
2. `answer`, `source`, and `tool_calls` fields are present
3. Appropriate tools are called for specific questions
4. Source references wiki files correctly

## Future Work (Task 3)

In the next task, you may extend this agent with:

- **More tools:** `query_api`, `search_code`, `run_command`
- **Better source extraction:** Identify exact section anchors
- **Improved system prompt:** Better guidance for complex queries
- **Caching:** Cache file reads to reduce API calls
- **Streaming:** Stream responses for better UX
