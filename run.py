# run.py - The Main Power Button
import os
import asyncio
from agents.supervisor import swiggy_graph
from langchain_core.messages import HumanMessage

async def main():
    print("🎤 Swiggy Bot Session Started | Seedhe Maut Vibe Active")
    print("Type 'exit' to quit.\n")
    
    config = {"configurable": {"thread_id": "local_test_user"}}
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit"]:
            break
            
        # We use ainvoke because your agents are async (talking to the internet)
        result = await swiggy_graph.ainvoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config
        )
        
        # Print the last bot response
        for msg in reversed(result["messages"]):
            if msg.type == "ai" and not msg.content.startswith("["):
                print(f"\nBot: {msg.content}\n")
                break

if __name__ == "__main__":
    asyncio.run(main())