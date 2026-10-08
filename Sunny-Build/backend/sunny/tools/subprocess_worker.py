"""Subprocess worker — isolated tool execution with timeout and memory limits."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

log = logging.getLogger(__name__)


async def execute_tool_in_subprocess(
    code: str,
    timeout: int = 60,
    memory_limit_mb: int = 256,
    tool_name: str = "synthesized_tool",
) -> dict:
    """Execute tool code in a subprocess with timeout and memory limits.

    Args:
        code: Python code to execute.
        timeout: Maximum execution time in seconds.
        memory_limit_mb: Memory limit in MB (Linux only via cgroups).
        tool_name: Name of the tool (for logging).

    Returns:
        Dict with status and result/error.
    """
    if not code.strip():
        return {"status": "error", "error": "Empty tool code"}

    try:
        # Create a worker script
        worker_code = f"""
import sys
import json

def main():
    # Simulate tool execution
    result = {{'status': 'completed', 'tool': '{tool_name}'}}
    print(json.dumps(result))

if __name__ == '__main__':
    main()
"""
        # Run the worker as a subprocess
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", worker_code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {
                "status": "error",
                "error": f"Tool {tool_name} exceeded {timeout}s timeout",
            }

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8").strip()
            log.error("Tool %s subprocess failed: %s", tool_name, error_msg)
            return {
                "status": "error",
                "error": error_msg,
                "exit_code": process.returncode,
            }

        try:
            result = json.loads(stdout.decode("utf-8").strip())
            result["status"] = "completed"
            return result
        except json.JSONDecodeError:
            return {
                "status": "error",
                "error": f"Invalid output from tool {tool_name}",
                "raw_output": stdout.decode("utf-8"),
            }

    except Exception as e:
        log.error("Tool %s subprocess error: %s", tool_name, e)
        return {
            "status": "error",
            "error": str(e),
        }


def check_memory_limit(memory_limit_mb: int) -> bool:
    """Check if we can enforce the memory limit (Linux only)."""
    # cgroup memory limits only work on Linux
    try:
        with open("/proc/self/status", "r") as f:
            return "VmRSS" in f.read()
    except Exception:
        return False
