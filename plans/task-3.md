# Task 3 Plan: The System Agent

## Overview

Extend the agent from Task 2 with a new `query_api` tool that can call the deployed backend API. This enables the agent to answer questions about:

- **Static system facts**: framework, ports, status codes
- **Data-dependent queries**: item count, analytics, scores

## New Tool: `query_api`

### Tool Schema

```json
{
  "type": "function",
  "function": {
    "name": "query_api",
    "description": "Call the backend LMS API to query data or test endpoints",
    "parameters": {
      "type": "object",
      "properties": {
        "method": {
          "type": "string",
          "description": "HTTP method (GET, POST, PUT, DELETE, etc.)",
          "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]
        },
        "path": {
          "type": "string",
          "description": "API path (e.g., /items/, /analytics/completion-rate)"
        },
        "body": {
          "type": "string",
          "description": "Optional JSON request body (for POST/PUT/PATCH)"
        }
      },
      "required": ["method", "path"]
    }
  }
}
```

### Implementation

```python
def query_api(method: str, path: str, body: str | None = None) -> str:
    """Call the backend LMS API.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path (e.g., /items/)
        body: Optional JSON request body
        
    Returns:
        JSON string with status_code and body
    """
    # Read LMS_API_KEY from .env.docker.secret
    # Read AGENT_API_BASE_URL from environment (default: http://localhost:42002)
    
    url = f"{api_base_url}{path}"
    headers = {
        "Authorization": f"Bearer {lms_api_key}",
        "Content-Type": "application/json",
    }
    
    # Make HTTP request
    # Return JSON response with status_code and body
```

### Authentication

- Use `LMS_API_KEY` from `.env.docker.secret` (backend API key)
- **NOT** the same as `LLM_API_KEY` from `.env.agent.secret` (LLM provider key)
- Send as `Authorization: Bearer {LMS_API_KEY}` header

### Environment Variables

| Variable | Purpose | Source | Default |
|----------|---------|--------|---------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` | - |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` | - |
| `LLM_MODEL` | Model name | `.env.agent.secret` | - |
| `LMS_API_KEY` | Backend API key for `query_api` auth | `.env.docker.secret` | - |
| `AGENT_API_BASE_URL` | Base URL for `query_api` | Environment / `.env.docker.secret` | `http://localhost:42002` |

> **Important:** The autochecker injects its own values. Never hardcode these.

## System Prompt Update

Update the system prompt to guide the LLM on when to use each tool:

```
You are a documentation and system assistant with access to these tools:
- list_files: List files in a directory
- read_file: Read the contents of a file
- query_api: Call the backend LMS API

Tool selection guide:
- Use list_files/read_file for:
  - Wiki documentation questions
  - Source code questions
  - Configuration file questions
  - File structure questions
  
- Use query_api for:
  - Questions about data in the database (item count, learner stats)
  - Questions about API behavior (status codes, responses)
  - Questions about analytics or metrics
  - Testing API endpoints

When answering:
1. Choose the right tool for the question
2. Make only ONE tool call at a time
3. Wait for the tool result before making another call
4. When you find the answer, provide:
   - A clear, concise answer
   - The source reference (wiki/filename.md#section) if from wiki
   - The API endpoint if from query_api
```

## Agentic Loop Changes

The loop remains the same - just add `query_api` to the tools list.

## Benchmark Results

**Initial Score:** 3/10

**First Failures:**

- Question 3 (framework): LLM said "Let me check" instead of reading the file
- Question 4 (routers): LLM kept reading individual router files instead of reporting the list
- Question 5 (items count): query_api tool had a bug (missing arguments)

**Iteration Strategy:**

1. Fixed `execute_tool` to properly pass arguments to `query_api`
2. Updated system prompt to emphasize complete answers
3. Added guidance that file names indicate their purpose
4. Reduced MAX_TOOL_CALLS from 10 to 8 to force earlier completion
5. Updated `extract_source` to handle source code files

**Final Score:** 7/10

**Remaining Failures:**

- Question 8 (top-learners crash): LLM doesn't read the source file to find the bug
- Question 9 (idempotency): LLM judge question - requires reasoning
- Question 10: Hidden question

**Lessons Learned:**

- LLM behavior can be inconsistent - same prompt works sometimes, fails others
- "Let me check" pattern indicates the LLM is in exploration mode
- Reducing tool call limits helps force completion
- File names often contain enough information (items.py → items domain)

## Expected Failures and Fixes

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| query_api not called for data questions | LLM doesn't know when to use it | Improve system prompt |
| query_api returns 401 | Wrong API key or missing auth | Check LMS_API_KEY loading |
| query_api wrong URL | Hardcoded URL | Use AGENT_API_BASE_URL env var |
| Agent loops on same file | File too large | Truncate content, improve prompt |
| Answer close but wrong keywords | Phrasing issue | Adjust prompt for precision |

## Files to Modify/Create

1. `plans/task-3.md` - This plan
2. `agent.py` - Add `query_api` tool, update system prompt
3. `AGENT.md` - Update documentation (200+ words on lessons learned)
4. `tests/test_3.py` - 2 regression tests

## Testing Strategy

Create 2 regression tests:

1. **Framework question:**
   - Question: "What Python web framework does the backend use?"
   - Expected: `read_file` in tool_calls, `FastAPI` in answer

2. **Database count question:**
   - Question: "How many items are in the database?"
   - Expected: `query_api` in tool_calls, number in answer

## Success Criteria

- All 10 `run_eval.py` questions pass
- `query_api` tool works with authentication
- Agent correctly selects tools based on question type
- 2 new regression tests pass
- AGENT.md has 200+ words on lessons learned
