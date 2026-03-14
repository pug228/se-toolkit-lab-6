# Agent Architecture

## Overview

This agent is a CLI tool that connects to an LLM (Large Language Model) and answers questions. It forms the foundation for the more advanced agent you will build in Tasks 2-3, which will add tools and an agentic loop.

## LLM Provider

**Provider:** Qwen Code API (self-hosted via qwen-code-oai-proxy)

**Model:** `qwen3-coder-plus`

**Why Qwen Code:**
- 1000 free requests per day
- Works from Russia without restrictions
- No credit card required
- OpenAI-compatible API for easy integration

## Architecture

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

1. **Environment Loading (`load_env`)**
   - Reads `.env.agent.secret` in the project root
   - Parses `LLM_API_KEY`, `LLM_API_BASE`, and `LLM_MODEL`
   - Exits with error if file is missing or credentials are incomplete

2. **CLI Argument Parsing (`main`)**
   - Uses `sys.argv` to get the question from command line
   - Validates that a question was provided
   - Exits with usage message if no argument given

3. **LLM API Client (`call_llm`)**
   - Uses `httpx` to make HTTP POST requests
   - Endpoint: `{LLM_API_BASE}/chat/completions`
   - Headers: `Authorization: Bearer {LLM_API_KEY}`, `Content-Type: application/json`
   - Body: OpenAI-compatible format with `model` and `messages`
   - Timeout: 60 seconds
   - Handles errors: timeout, HTTP errors, connection errors

4. **Response Parsing**
   - Extracts answer from `choices[0].message.content`
   - Builds output JSON with `answer` and empty `tool_calls` array

5. **Output**
   - Prints valid JSON to stdout
   - All debug/logging output goes to stderr (using `print(..., file=sys.stderr)`)

### Data Flow

```
Command line argument → Load env config → Build HTTP request → 
Call LLM API → Parse response → Output JSON to stdout
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
uv run agent.py "What is the capital of France?"

# Example output
{"answer": "The capital of France is Paris.", "tool_calls": []}
```

## Error Handling

- **Missing credentials:** Exits with code 1, prints error to stderr
- **API timeout:** Exits with code 1 after 60 seconds
- **API error:** Exits with code 1, prints status code and response to stderr
- **Connection error:** Exits with code 1, prints error to stderr
- **Invalid response format:** Exits with code 1, prints error to stderr

## Testing

Run the regression test:

```bash
uv run pytest backend/tests/unit/test_agent_task1.py -v
```

The test verifies:
1. Agent produces valid JSON output
2. `answer` field is present and non-empty
3. `tool_calls` field is present (empty array for Task 1)

## Future Work (Tasks 2-3)

In the next tasks, you will extend this agent with:
- **Tools:** Add capabilities like `read_file`, `list_files`, `query_api`
- **Agentic loop:** Enable the agent to plan, use tools, and iterate
- **Domain knowledge:** Add system prompts with project-specific context
- **Source tracking:** Include file references in the output
