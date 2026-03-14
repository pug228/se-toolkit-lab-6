# Task 1 Plan: Call an LLM from Code

## LLM Provider and Model

**Provider:** Qwen Code API (self-hosted via qwen-code-oai-proxy on VM)

**Model:** `qwen3-coder-plus`

**Why this choice:**
- Qwen Code provides 1000 free requests per day
- Works from Russia without restrictions
- No credit card required
- Uses OpenAI-compatible API, making integration simple

## Agent Structure

### Input/Output

**Input:** A question passed as the first command-line argument:
```bash
uv run agent.py "What does REST stand for?"
```

**Output:** A single JSON line to stdout:
```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

### Components

1. **Environment Loading**
   - Read `.env.agent.secret` for `LLM_API_KEY`, `LLM_API_BASE`, and `LLM_MODEL`
   - Use `pydantic-settings` or manual parsing to load configuration

2. **CLI Argument Parsing**
   - Use `sys.argv` or `argparse` to get the question from command line
   - Validate that a question was provided

3. **LLM API Client**
   - Use `httpx` (already in project dependencies) to make HTTP POST request
   - Endpoint: `{LLM_API_BASE}/chat/completions`
   - Headers: `Authorization: Bearer {LLM_API_KEY}`, `Content-Type: application/json`
   - Body: OpenAI-compatible format with `model`, `messages`

4. **Response Parsing**
   - Extract the assistant's answer from `choices[0].message.content`
   - Build the output JSON with `answer` and empty `tool_calls` array

5. **Output**
   - Print valid JSON to stdout
   - All debug/logging output goes to stderr

### Error Handling

- **Timeout:** The agent must respond within 60 seconds (enforced by subprocess timeout in tests)
- **API errors:** Print error message to stderr and exit with code 1
- **Missing question:** Print usage message to stderr and exit with code 1
- **Invalid response:** Handle gracefully and report error to stderr

### Data Flow

```
Command line argument → Load env config → Build HTTP request → 
Call LLM API → Parse response → Output JSON to stdout
```

## Testing Strategy

Create one regression test that:
1. Runs `agent.py` as a subprocess with a test question
2. Parses the stdout as JSON
3. Verifies that `answer` field exists and is non-empty
4. Verifies that `tool_calls` field exists (should be empty array for Task 1)

## Files to Create

1. `plans/task-1.md` - This plan
2. `agent.py` - The main agent CLI
3. `.env.agent.secret` - Configuration file (gitignored)
4. `AGENT.md` - Documentation
5. `backend/tests/unit/test_agent_task1.py` - Regression test
