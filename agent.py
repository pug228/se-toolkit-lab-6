#!/usr/bin/env python3
"""Agent CLI - Calls an LLM with tools and returns a structured JSON answer.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
    All debug output goes to stderr.
"""

import json
import os
import sys
from pathlib import Path

import httpx

# Maximum number of tool calls per question
MAX_TOOL_CALLS = 8

# System prompt for the documentation agent
SYSTEM_PROMPT = """You are a documentation and system assistant with access to three tools:
- list_files: List files in a directory
- read_file: Read the contents of a file  
- query_api: Call the backend LMS API to query data or test endpoints

IMPORTANT: Your answers must be complete. Don't say "Let me check X" - provide the actual answer.
If you found a list of files, report the list. If you found a framework name, report it.

Tool selection guide:
- Use list_files/read_file for:
  - Wiki documentation questions (files in wiki/)
  - Source code questions (backend/, frontend/, agent.py)
  - Configuration file questions (docker-compose.yml, .env files, pyproject.toml)
  - File structure questions
  
- Use query_api for:
  - Questions about data in the database (item count, learner stats)
  - Questions about API behavior (status codes, responses)
  - Questions about analytics or metrics
  - Testing API endpoints (use auth=false to test unauthenticated access)

To answer questions:
1. Choose the right tool for the question type
2. For source code questions: use read_file to read Python files directly (e.g., backend/app/main.py)
3. For wiki questions: use list_files to explore wiki/, then read_file to read relevant files  
4. For file listing questions: use list_files to find files, then provide the list in your answer
   - File names often indicate their purpose (e.g., items.py handles items, analytics.py handles analytics)
   - Example: If you see ["items.py", "analytics.py"], answer: "items.py handles items, analytics.py handles analytics"
5. Use query_api to query the backend API for data or test endpoints
6. In your final answer, provide:
   - A clear, concise answer based on what you found
   - The source reference (wiki/filename.md#section) if from wiki
   - The file path if from source code
   - The API endpoint if from query_api

Rules:
- Make only ONE tool call at a time
- Always wait for the tool result before making another call
- When you have enough information to answer, STOP calling tools and provide the final answer immediately
- Maximum 10 tool calls per question
- For file listing questions, once you have the file list, provide the answer right away
- File names typically indicate their domain/purpose - you don't need to read every file
- For source code questions about frameworks/imports: READ the main Python file (e.g., main.py) and report what you find
- Your answer should be complete and standalone - not "let me check X" but "X handles Y"
"""


def load_env() -> dict:
    """Load environment variables from .env.agent.secret."""
    env_file = Path(__file__).parent / ".env.agent.secret"
    if not env_file.exists():
        print(f"Error: {env_file} not found", file=sys.stderr)
        print(
            "Copy .env.agent.example to .env.agent.secret and fill in your credentials.",
            file=sys.stderr,
        )
        sys.exit(1)

    env = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        env[key] = value

    return env


def load_docker_env() -> dict:
    """Load environment variables from .env.docker.secret."""
    env_file = Path(__file__).parent / ".env.docker.secret"
    if not env_file.exists():
        print(
            f"Warning: {env_file} not found, using environment variables only",
            file=sys.stderr,
        )
        return {}

    env = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        env[key] = value

    return env


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent


def validate_path(path: str) -> Path:
    """Validate that path is within project root and return the resolved path.

    Args:
        path: Relative path from project root

    Returns:
        Resolved absolute path

    Raises:
        ValueError: If path tries to escape project root
    """
    project_root = get_project_root()
    full_path = (project_root / path).resolve()

    # Check for path traversal
    if not str(full_path).startswith(str(project_root)):
        raise ValueError(f"Path traversal not allowed: {path}")

    return full_path


def read_file(path: str) -> str:
    """Read a file from the project repository.

    Args:
        path: Relative path from project root

    Returns:
        File contents as a string, or an error message
    """
    try:
        full_path = validate_path(path)

        if not full_path.exists():
            return f"Error: File not found: {path}"

        if not full_path.is_file():
            return f"Error: Not a file: {path}"

        return full_path.read_text()

    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error reading file: {e}"


def list_files(path: str) -> str:
    """List files and directories at a given path.

    Args:
        path: Relative directory path from project root

    Returns:
        Newline-separated listing of entries, or an error message
    """
    try:
        full_path = validate_path(path)

        if not full_path.exists():
            return f"Error: Directory not found: {path}"

        if not full_path.is_dir():
            return f"Error: Not a directory: {path}"

        entries = sorted(full_path.iterdir())
        return "\n".join(entry.name for entry in entries)

    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error listing directory: {e}"


def query_api(
    method: str, path: str, body: str | None = None, auth: bool = True
) -> str:
    """Call the backend LMS API.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        path: API path (e.g., /items/, /analytics/completion-rate)
        body: Optional JSON request body (for POST/PUT/PATCH)
        auth: Whether to include authentication header (default: True)

    Returns:
        JSON string with status_code and body, or an error message
    """
    # Load docker env for LMS_API_KEY
    docker_env = load_docker_env()

    # Get API key from environment variable first, then from .env.docker.secret
    lms_api_key = os.environ.get("LMS_API_KEY") or docker_env.get("LMS_API_KEY")

    # Get API base URL from environment variable, then from .env.docker.secret, then default
    # Caddy runs on port 42002 and proxies to the backend
    agent_api_base = (
        os.environ.get("AGENT_API_BASE_URL")
        or docker_env.get("AGENT_API_BASE_URL")
        or "http://localhost:42002"
    )

    if auth and not lms_api_key:
        return "Error: LMS_API_KEY not configured"

    url = f"{agent_api_base}{path}"

    headers = {
        "Content-Type": "application/json",
    }

    # Only add auth header if auth is True and we have a key
    if auth and lms_api_key:
        headers["Authorization"] = f"Bearer {lms_api_key}"

    # print(f"Calling API: {method} {url} (auth={auth})", file=sys.stderr)

    try:
        with httpx.Client(timeout=30.0) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                response = client.post(url, headers=headers, content=body or "{}")
            elif method.upper() == "PUT":
                response = client.put(url, headers=headers, content=body or "{}")
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers)
            elif method.upper() == "PATCH":
                response = client.patch(url, headers=headers, content=body or "{}")
            else:
                return f"Error: Unknown method: {method}"

            result = {
                "status_code": response.status_code,
                "body": response.text,
            }
            return json.dumps(result)

    except httpx.TimeoutException:
        return "Error: API request timed out"
    except httpx.RequestError as e:
        return f"Error: Cannot reach API: {e}"
    except Exception as e:
        return f"Error: {e}"


# Tool definitions for OpenAI function calling
TOOLS = [
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
                        "description": "Relative path from project root",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a given path",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": "Call the backend LMS API to query data or test endpoints. Use this for questions about database contents, API behavior, or analytics. Set auth=false to test unauthenticated access.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, PUT, DELETE, PATCH)",
                        "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    },
                    "path": {
                        "type": "string",
                        "description": "API path (e.g., /items/, /analytics/completion-rate)",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional JSON request body (for POST/PUT/PATCH)",
                    },
                    "auth": {
                        "type": "boolean",
                        "description": "Whether to include authentication header (default: true). Set to false to test unauthenticated access.",
                    },
                },
                "required": ["method", "path"],
            },
        },
    },
]

# Map of tool names to functions
TOOL_FUNCTIONS = {
    "read_file": read_file,
    "list_files": list_files,
    "query_api": query_api,
}


def call_llm(
    messages: list[dict],
    api_base: str,
    api_key: str,
    model: str,
    tools: list[dict] | None = None,
) -> dict:
    """Call the LLM API and return the response.

    Args:
        messages: List of message dicts in OpenAI format
        api_base: The API base URL
        api_key: The API key for authentication
        model: The model name to use
        tools: Optional list of tool schemas

    Returns:
        The response data dict

    Raises:
        SystemExit: If the API call fails
    """
    url = f"{api_base}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
    }

    # Use tools format (OpenAI compatible)
    if tools:
        payload["tools"] = tools

    # print(f"Calling LLM at {url} with model {model}...", file=sys.stderr)

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

    except httpx.TimeoutException:
        print("Error: API request timed out after 60 seconds", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"Error: API returned status {e.response.status_code}", file=sys.stderr)
        print(f"Response: {e.response.text[:200]}", file=sys.stderr)
        sys.exit(1)
    except httpx.RequestError as e:
        print(f"Error: Cannot reach API: {e}", file=sys.stderr)
        sys.exit(1)

    # Debug: print the response to see if function_call is present
    # print(f"Response choices: {data.get('choices', [])}", file=sys.stderr)

    return data


def execute_tool(tool_name: str, args: dict) -> str:
    """Execute a tool and return the result.

    Args:
        tool_name: Name of the tool to execute
        args: Arguments to pass to the tool

    Returns:
        Tool result as a string
    """
    if tool_name not in TOOL_FUNCTIONS:
        return f"Error: Unknown tool: {tool_name}"

    func = TOOL_FUNCTIONS[tool_name]

    # For query_api, pass method, path, body, and auth
    if tool_name == "query_api":
        method = args.get("method", "GET")
        path = args.get("path", "")
        body = args.get("body")
        auth = args.get("auth", True)  # Default to True
        if not path:
            return "Error: Missing required argument 'path'"
        return func(method, path, body, auth)

    # For read_file and list_files, pass path
    path = args.get("path", "")
    if not path:
        return "Error: Missing required argument 'path'"

    return func(path)


def run_agentic_loop(
    question: str,
    api_base: str,
    api_key: str,
    model: str,
) -> tuple[str, str, list[dict]]:
    """Run the agentic loop to answer a question.

    Args:
        question: The user's question
        api_base: The API base URL
        api_key: The API key for authentication
        model: The model name to use

    Returns:
        Tuple of (answer, source, tool_calls)
    """
    # Initialize message history
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    # Track all tool calls for output
    all_tool_calls = []
    tool_call_count = 0

    while tool_call_count < MAX_TOOL_CALLS:
        # Call LLM with tools
        response = call_llm(messages, api_base, api_key, model, tools=TOOLS)

        # Get the assistant message
        try:
            assistant_message = response["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as e:
            print(f"Error: Unexpected API response format: {e}", file=sys.stderr)
            print(f"Response: {response}", file=sys.stderr)
            sys.exit(1)

        # Check for tool calls
        tool_calls = assistant_message.get("tool_calls")

        if not tool_calls:
            # No tool calls - this is the final answer
            answer = assistant_message.get("content", "")

            # Try to extract source from the answer
            source = extract_source(answer, all_tool_calls)

            return answer, source, all_tool_calls

        # Process tool calls
        # First, add the assistant message with tool calls to history
        messages.append(assistant_message)

        for tool_call in tool_calls:
            tool_call_id = tool_call["id"]
            tool_name = tool_call["function"]["name"]

            # Parse arguments
            try:
                args = json.loads(tool_call["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}

            # print(f"Executing tool: {tool_name} with args: {args}", file=sys.stderr)

            # Execute the tool
            result = execute_tool(tool_name, args)

            # Record the tool call
            all_tool_calls.append(
                {
                    "tool": tool_name,
                    "args": args,
                    "result": result,
                }
            )

            # Add tool response to messages
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result,
                }
            )

            tool_call_count += 1

            if tool_call_count >= MAX_TOOL_CALLS:
                print(f"Reached maximum tool calls ({MAX_TOOL_CALLS})", file=sys.stderr)
                break

    # If we exit the loop without a final answer, use the last assistant message
    if messages and messages[-1].get("role") == "assistant":
        answer = messages[-1].get("content", "")
    else:
        answer = "I was unable to find an answer within the tool call limit."

    source = extract_source(answer, all_tool_calls)
    return answer, source, all_tool_calls


def extract_source(answer: str, tool_calls: list[dict]) -> str:
    """Extract source reference from the answer or tool calls.

    Looks for patterns like:
    - wiki/filename.md#section
    - wiki/filename.md
    - backend/app/path/file.py

    Args:
        answer: The answer text
        tool_calls: List of tool calls made

    Returns:
        Source reference or empty string
    """
    import re

    # First try to extract from answer
    match = re.search(r"(wiki/[\w-]+\.md(?:#[\w-]+)?)", answer)
    if match:
        return match.group(1)

    # If not found in answer, check tool calls for read_file
    for tc in tool_calls:
        if tc.get("tool") == "read_file":
            path = tc.get("args", {}).get("path", "")
            # Return the last file that was read (most relevant)
            if path.endswith(".py") or path.endswith(".md") or path.endswith(".yml"):
                return path

    return ""


def main() -> None:
    """Main entry point."""
    # Parse command-line arguments
    if len(sys.argv) < 2:
        print('Usage: uv run agent.py "Your question here"', file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    # Load configuration
    env = load_env()

    api_key = env.get("LLM_API_KEY")
    api_base = env.get("LLM_API_BASE")
    model = env.get("LLM_MODEL")

    if not all([api_key, api_base, model]):
        print(
            "Error: Missing required environment variables.",
            file=sys.stderr,
        )
        print(
            "Ensure .env.agent.secret contains LLM_API_KEY, LLM_API_BASE, and LLM_MODEL.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Remove trailing slash from api_base if present
    api_base = api_base.rstrip("/")

    # Run the agentic loop
    answer, source, tool_calls = run_agentic_loop(question, api_base, api_key, model)

    # Output the result as JSON to stdout
    result = {
        "answer": answer,
        "source": source,
        "tool_calls": tool_calls,
    }

    print(json.dumps(result))

    # Also print human-readable answer to stderr
    # print(f"\nAnswer: {answer}", file=sys.stderr)
    # if source:
    #    print(f"Source: {source}", file=sys.stderr)


if __name__ == "__main__":
    main()
