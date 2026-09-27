import asyncio
from dotenv import load_dotenv
from src.tools.mcp_manager import load_mcp_tools
from src.graph import build_recon_graph
from langgraph.types import Command
import time
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
        "messages": [],
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0
    }
    
    print("\n--- AVVIO PIPELINE: DISCOVERY -> EVALUATION -> PERSISTENCE ---")
    start_time_etl = time.perf_counter()

    # Il flusso esegue fino al persister, salva su Mongo e si congela prima di advisor
    await app.ainvoke(initial_state, config=thread_config)
    etl_duration = time.perf_counter() - start_time_etl

    # Recupera lo stato al checkpoint per verificare token spesi nella sola fase ETL
    etl_state = app.get_state(thread_config).values
    etl_tokens = etl_state.get("total_tokens", 0)


    
    # Controllo interattivo: l'utente scrive o preme semplicemente invio
    print("\n" + "="*60)
    print("Dati persistiti su MongoDB con successo.")

    print(f"\n[BENCHMARK FASE ETL (Nodi 1-3)]")
    print(f"  * Tempo impiegato : {etl_duration:.2f} s")
    print(f"  * Token utilizzati: {etl_tokens} (Prompt: {etl_state.get('prompt_tokens', 0)}, Completion: {etl_state.get('completion_tokens', 0)})")

    user_input = input("Inserisci una richiesta per l'SRE Advisor (o premi solo INVIO per uscire): ").strip()
    print("="*60)
    
    start_time_advisor = time.perf_counter()
    await app.ainvoke(Command(resume=user_input), config=thread_config)
    advisor_duration = time.perf_counter() - start_time_advisor

    # Stato finale completo
    final_state = app.get_state(thread_config).values
    total_duration = etl_duration + advisor_duration

    print("\n" + "="*45)
    print("        REPORT BENCHMARK COMPLETO")
    print("="*45)
    print(f"Tempo ETL (Nodi 1-3)   : {etl_duration:.2f} s")
    print(f"Tempo Advisor (Nodo 4) : {advisor_duration:.2f} s")
    print(f"Tempo Totale Workflow  : {total_duration:.2f} s")
    print(f"Prompt Tokens Totali   : {final_state.get('prompt_tokens', 0)}")
    print(f"Output Tokens Totali   : {final_state.get('completion_tokens', 0)}")
    print(f"Token Totali Consumati : {final_state.get('total_tokens', 0)}")
    print("="*45)

if __name__ == "__main__":
    asyncio.run(run())