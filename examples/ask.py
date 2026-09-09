"""Ask the agent one question with the configured model, locally, through the deployment's profile."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from langchain_core.runnables import RunnableConfig

from paid_media_agent.config import Settings
from paid_media_agent.runtime.local import build_configured_runtime


async def main(question: str) -> None:
    settings = Settings()
    root = Path(__file__).resolve().parents[1]
    runtime = build_configured_runtime(settings, project_root=root)
    config = RunnableConfig(configurable={"thread_id": "example", "caller_ref": "local-user"})
    state = await runtime.graph.ainvoke(
        {"messages": [{"role": "user", "content": question}]}, config=config
    )
    print(state["messages"][-1].content)
    print(
        f"\nselection={runtime.components.metadata.selection.strategy.value} catalog={runtime.catalog.revision}"
    )


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or "Compare the last two weeks with the prior two weeks."
    asyncio.run(main(prompt))
