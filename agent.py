#!/usr/bin/env python3
"""Agent CLI - Calls an LLM and returns a structured JSON answer.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "tool_calls": []}
    All debug output goes to stderr.
"""

import json
import os
import sys
from pathlib import Path

import httpx


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


def call_llm(question: str, api_base: str, api_key: str, model: str) -> str:
    """Call the LLM API and return the answer.

    Args:
        question: The user's question
        api_base: The API base URL (e.g., http://localhost:42005/v1)
        api_key: The API key for authentication
        model: The model name to use

    Returns:
        The assistant's answer as a string

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
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": question},
        ],
    }

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

    # Parse the response
    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        print(f"Error: Unexpected API response format: {e}", file=sys.stderr)
        print(f"Response: {data}", file=sys.stderr)
        sys.exit(1)

    return answer


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

    # Call the LLM
    answer = call_llm(question, api_base, api_key, model)

    # Output the result as JSON to stdout
    result = {
        "answer": answer,
        "tool_calls": [],
    }

    print(json.dumps(result))

    # Also print human-readable answer to stderr
    # print(f"{answer}\n", file=sys.stderr)


if __name__ == "__main__":
    main()
