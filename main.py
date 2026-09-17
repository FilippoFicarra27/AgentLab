import asyncio
from dotenv import load_dotenv
from src.tools.mcp_manager import load_mcp_tools
from src.graph import build_recon_graph

load_dotenv()

async def run():
    print("Connessione ai server MCP in corso...")
    client, tools = await load_mcp_tools()
    
    print(f"Tool caricati con successo ({len(tools)} disponibili):")
    for t in tools:
        print(f"  - {t.name}")

    app = build_recon_graph(tools)
    
    initial_state = {
        "target_namespace": "default",
        "discovered_pods": [],
        "metrics_summary": {},
        "final_report": "",
        "messages": []
    }
    
    result = await app.ainvoke(
    initial_state,
    config={
        "run_name": "Full-Recon-Pipeline",
        "tags": ["kind-cluster", "thesis-experiment", "gemini-2.5-flash"]
    }
)
    
    print("\n" + "="*60)
    print("REPORT FINALE DI RICOGNIZIONE:")
    print("="*60)
    print(result.get("final_report", "Nessun report generato."))

if __name__ == "__main__":
    asyncio.run(run())