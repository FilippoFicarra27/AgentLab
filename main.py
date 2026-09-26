import asyncio
from dotenv import load_dotenv
from src.tools.mcp_manager import load_mcp_tools
from src.graph import build_recon_graph
from langgraph.types import Command
load_dotenv()

async def run():
    print("Connessione ai server MCP in corso...")
    client, tools = await load_mcp_tools()
    print(f"Tool caricati con successo ({len(tools)} disponibili):")
    for t in tools:
        print(f"  - {t.name}")
    app = build_recon_graph(tools)
    
    # ID thread necessario a MemorySaver per recuperare lo stato congelato
    thread_config = {"configurable": {"thread_id": "session-k8s-sre"}}
    
    initial_state = {
        "target_namespace": "default",
        "discovered_pods": [],
        "app_mapping": {},
        "metrics_summary": {},
        "raw_prometheus_responses": {},
        "final_report": "",
        "user_query": None,
        "advisor_response": None,
        "messages": []
    }
    
    print("\n--- AVVIO PIPELINE: DISCOVERY -> EVALUATION -> PERSISTENCE ---")
    # Il flusso esegue fino al persister, salva su Mongo e si congela prima di advisor
    await app.ainvoke(initial_state, config=thread_config)
    
    # Controllo interattivo: l'utente scrive o preme semplicemente invio
    print("\n" + "="*60)
    print("Dati persistiti su MongoDB con successo.")
    user_input = input("Inserisci una richiesta per l'SRE Advisor (o premi solo INVIO per uscire): ").strip()
    print("="*60)
    
   
    await app.ainvoke(Command(resume=user_input), config=thread_config)

if __name__ == "__main__":
    asyncio.run(run())