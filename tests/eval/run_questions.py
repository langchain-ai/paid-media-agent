"""Send each question to an agent server in a fresh thread; record tools, timing, and the answer.

Usage: run_questions.py <server url> <out.jsonl> [comma-separated question ids]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from langgraph_sdk import get_client

QUESTIONS = Path(__file__).with_name("questions.json")


def _text(content: object) -> str:
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return str(content)


async def main(url: str, out_path: str, only: set[str] | None) -> None:
    client = get_client(url=url)
    graph = (await client.assistants.search())[0]["assistant_id"]
    with open(out_path, "a", encoding="utf-8") as out:
        for question in json.loads(QUESTIONS.read_text()):
            if only and question["id"] not in only:
                continue
            thread = await client.threads.create()
            started = time.time()
            record: dict[str, object] = {"id": question["id"], "question": question["text"]}
            try:
                result = await client.runs.wait(
                    thread["thread_id"],
                    graph,
                    input={"messages": [{"role": "user", "content": question["text"]}]},
                )
                messages = result.get("messages", [])
                record["tools"] = [
                    call["name"]
                    for m in messages
                    if m.get("type") == "ai"
                    for call in (m.get("tool_calls") or [])
                ]
                record["answer"] = _text(messages[-1].get("content")) if messages else ""
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            record["seconds"] = round(time.time() - started, 1)
            out.write(json.dumps(record) + "\n")
            out.flush()
            print(f"{question['id']:18} {record['seconds']:7.1f}s tools={record.get('tools')}")


if __name__ == "__main__":
    ids = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None
    asyncio.run(main(sys.argv[1], sys.argv[2], ids))
