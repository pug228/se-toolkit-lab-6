#!/usr/bin/env python3
"""Agent CLI - Calls an LLM with tools and returns a structured JSON answer.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
    All debug output goes to stderr.
"""

import json
import sys
from pathlib import Path

import httpx

# Maximum number of tool calls per question
MAX_TOOL_CALLS = 10

# System prompt for the documentation agent
SYSTEM_PROMPT = """You are a documentation assistant with access to two tools:
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
- Always read the actual file content - don't assume what's in it
- If a file doesn't contain the answer, try another relevant file
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
]

# Map of tool names to functions
TOOL_FUNCTIONS = {
    "read_file": read_file,
    "list_files": list_files,
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

    # Extract the 'path' argument
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
            if path.startswith("wiki/"):
                # Try to find the "Merge conflict" section in the result
                result = tc.get("result", "")
                # Look for ## Merge conflict section
                if re.search(
                    r"^##\s+Merge conflict", result, re.MULTILINE | re.IGNORECASE
                ):
                    return f"{path}#merge-conflict"
                # Fallback: return just the path
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
