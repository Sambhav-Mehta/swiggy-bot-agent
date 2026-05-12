import re
import asyncio
from dotenv import load_dotenv

load_dotenv()

from agents.supervisor import swiggy_graph
from langchain_core.messages import HumanMessage


def _get_text(content) -> str:
    """Extract plain text from LLM content — handles str, list of blocks, or objects."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                # Include "text" blocks; skip "thinking"/"thought" blocks
                block_type = block.get("type", "text")
                if block_type not in ("thinking", "thought", "tool_use", "tool_result"):
                    text = block.get("text", "")
                    if text:
                        parts.append(text)
        return "".join(parts)
    return str(content)


def _clean_for_display(text: str) -> str:
    """Strip internal routing JSON blocks so users don't see plumbing."""
    cleaned = re.sub(r'\s*```json[\s\S]*?```', '', text, flags=re.DOTALL)
    return cleaned.strip()


async def main():
    print("🎤 Swiggy Bot Session Started | Seedhe Maut Vibe Active")
    print("Type 'exit' to quit.\n")

    config = {
        "configurable": {"thread_id": "local_test_user"},
        "recursion_limit": 12,
    }

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ["exit", "quit"]:
            break

        print("⏳ Working on it...\n")
        result = await swiggy_graph.ainvoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config,
        )

        # Walk messages newest-first; show the last non-empty AI response
        # after stripping internal routing JSON blocks.
        for msg in reversed(result["messages"]):
            if msg.type != "ai":
                continue
            text = _get_text(msg.content)
            if not text:
                continue
            clean = _clean_for_display(text)
            if clean:
                print(f"\nBot: {clean}\n")
                break


if __name__ == "__main__":
    asyncio.run(main())
