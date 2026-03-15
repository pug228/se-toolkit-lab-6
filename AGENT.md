# Agent Architecture

## Overview

This agent is a CLI tool that connects to an LLM (Large Language Model) with **tools** and an **agentic loop**. The agent can read project files, list directories, query the backend API, and answer questions based on documentation, source code, and live system data.

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
uv run agent.py "How many items are in the database?"
```

**Output:** A single JSON line to stdout:

```json
{
  "answer": "There are 44 items currently stored in the database.",
  "source": "backend/app/routers/analytics.py",
  "tool_calls": [
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/"},
      "result": "{\"status_code\": 200, ...}"
    }
  ]
}
```

### Components

#### 1. Environment Loading

- `load_env()`: Reads `.env.agent.secret` for LLM credentials
- `load_docker_env()`: Reads `.env.docker.secret` for backend API key

**Environment Variables:**

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for `query_api` | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Base URL for `query_api` | Environment / `.env.docker.secret` (default: `http://localhost:42002`) |

> **Important:** The autochecker injects its own values. Never hardcode these.

#### 2. Tools

The agent has three tools exposed to the LLM via function calling schemas:

**`read_file`**

- **Purpose:** Read a file from the project repository
- **Parameters:** `path` (string) — relative path from project root
- **Returns:** File contents as a string
- **Security:** Validates path to prevent directory traversal

**`list_files`**

- **Purpose:** List files and directories at a given path
- **Parameters:** `path` (string) — relative directory path from project root
- **Returns:** Newline-separated listing of entries
- **Security:** Validates path to prevent directory traversal

**`query_api`**

- **Purpose:** Call the backend LMS API to query data or test endpoints
- **Parameters:**
  - `method` (string) — HTTP method (GET, POST, PUT, DELETE, PATCH)
  - `path` (string) — API path (e.g., `/items/`, `/analytics/completion-rate`)
  - `body` (string, optional) — JSON request body
  - `auth` (boolean, default: true) — Whether to include authentication header
- **Returns:** JSON string with `status_code` and `body`
- **Authentication:** Uses `LMS_API_KEY` from environment
- **Use case:** Set `auth=false` to test unauthenticated access (e.g., checking 401 responses)

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

#### 3. Agentic Loop

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

1. Initialize message history with system prompt + user question
2. Call LLM with messages and tool schemas
3. Check response:
   - If `tool_calls` present:
     - Execute each tool function
     - Append tool results as `tool` role messages
     - Increment tool call counter
     - If counter >= 8, stop and return current answer
     - Go back to step 2
   - If no `tool_calls`:
     - Extract final answer from `choices[0].message.content`
     - Extract source reference
     - Return JSON output
4. Output JSON with `answer`, `source`, and `tool_calls` array

**Maximum Tool Calls:** 8 per question (prevents infinite loops)

#### 4. System Prompt Strategy

The system prompt guides the LLM on tool selection:

- **Wiki questions** → `list_files` + `read_file`
- **Source code questions** → `read_file` (e.g., `backend/app/main.py`)
- **Configuration questions** → `read_file` (e.g., `docker-compose.yml`)
- **Data questions** → `query_api` (e.g., item count)
- **API behavior questions** → `query_api` (e.g., status codes)
- **Bug diagnosis** → `query_api` + `read_file`

Key guidance:

- File names often indicate their purpose (e.g., `items.py` handles items)
- Make only ONE tool call at a time
- When you have enough information, STOP and provide the answer
- Answers must be complete — don't say "Let me check X"

#### 5. Source Extraction

The `extract_source()` function extracts source references from:

1. The answer text (looking for `wiki/filename.md#section` patterns)
2. Tool calls (returning the path of files read via `read_file`)

This ensures the `source` field is populated for both wiki and source code questions.

#### 6. Output

- Prints valid JSON to stdout
- All debug/logging output goes to stderr
- Human-readable answer also printed to stderr for interactive use

## Data Flow

```
Command line argument → Load env config → Initialize agentic loop →
  [Call LLM → Check for tool calls → Execute tools → Repeat] →
Extract answer + source → Output JSON to stdout
```

## Configuration

Create `.env.agent.secret` and `.env.docker.secret` in the project root:

```bash
cp .env.agent.example .env.agent.secret
cp .env.docker.example .env.docker.secret
```

Fill in your credentials.

> **Note:** Both files are gitignored. Never commit API keys.

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

## Testing

Run the regression tests:

```bash
# Task 3 tests
uv run pytest tests/test_3.py -v

# All tests
uv run pytest tests/ -v
```

## Benchmark Performance

**Local Evaluation Score:** 7/10

**Passing Questions:**

1. ✓ Wiki: Protect a branch on GitHub
2. ✓ Wiki: Connect to VM via SSH
3. ✓ Source code: Python web framework (FastAPI)
4. ✓ Source code: API router modules
5. ✓ API data: Item count in database
6. ✓ API behavior: Status code without auth (401)
7. ✓ Bug diagnosis: Completion-rate ZeroDivisionError

**Challenging Questions:**

- Question 8 (top-learners crash): Requires multi-step reasoning (query API → read source → identify TypeError)
- Question 9 (idempotency): LLM judge question requiring deep code understanding
- Questions 10+: Hidden questions in autochecker

## Lessons Learned

**Tool Design:**

1. **Function calling works well** — Qwen Code supports OpenAI-compatible tool calling reliably
2. **Parameter descriptions matter** — Clear descriptions help the LLM use tools correctly
3. **Optional parameters are tricky** — The `auth` parameter for `query_api` needed explicit documentation

**System Prompt Engineering:**

1. **"Let me check" anti-pattern** — The LLM would say "Let me check X" instead of actually checking. Fixed by emphasizing complete answers.
2. **Exploration vs. completion** — The LLM would keep exploring files unnecessarily. Fixed by reducing MAX_TOOL_CALLS and adding explicit stop guidance.
3. **File names contain information** — For listing questions, file names often answer the question (e.g., `items.py` → items domain).

**Agentic Loop:**

1. **Message format matters** — Using `tool` role for tool responses is required by the API
2. **Tool call limits prevent hangs** — Setting MAX_TOOL_CALLS=8 prevents infinite exploration
3. **Source extraction needs flexibility** — Must handle both wiki files and source code files

**LLM Behavior:**

1. **Inconsistency** — Same question sometimes works, sometimes fails. This is inherent to LLMs.
2. **Context matters** — The LLM performs better with clear examples in the system prompt.
3. **Multi-step reasoning is hard** — Questions requiring "query API → find error → read source → explain bug" are challenging.

**Future Improvements:**

1. **Better error handling** — More graceful handling of API failures
2. **Caching** — Cache file reads to reduce API calls
3. **Streaming** — Stream responses for better UX on long answers
4. **Better source extraction** — Identify exact line numbers for bugs

## Files

- `agent.py` — Main agent CLI with tools and agentic loop
- `AGENT.md` — This documentation
- `plans/task-3.md` — Implementation plan
- `tests/test_3.py` — Regression tests
