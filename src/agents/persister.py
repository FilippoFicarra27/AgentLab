import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from src.state import ReconState

async def persister_node(state: ReconState, tools: list) -> dict:
    print("\n-> [NODO 3: PERSISTER MONGODB VIA MCP]")
    
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=api_key,
        temperature=0.0,
        max_retries=5
    )
    
    mongo_tools = [t for t in tools if t.name == "save_metrics_to_mongodb"]
    llm_with_tools = llm.bind_tools(mongo_tools, tool_choice="any")
    
    app_mapping = state.get("app_mapping", {})
    metrics_summary = state.get("metrics_summary", {})
    raw_responses = state.get("raw_prometheus_responses", {})
    
    print(f"  [Persister Check] Applicazioni da salvare: {list(app_mapping.keys())}")
    print(f"  [Persister Check] Metriche calcolate: {metrics_summary}")

    if not app_mapping or not metrics_summary:
        print("  [Persister WARN] Dati assenti, salvataggio interrotto.")
        return {"final_report": "Salvataggio non eseguito: metriche non disponibili.", "messages": []}

    prompt = [
        SystemMessage(
            content=(
                "Sei un assistente per la persistenza su database. "
                "Per OGNI applicazione, devi chiamare `save_metrics_to_mongodb`.\n"
                "È FONDAMENTALE passare nel parametro `metrics` il dizionario completo delle metriche calcolate "
                "(cpu_cores, memory_bytes, memory_mb, disk_write_bps, network_rx_bps) e in `raw_prometheus_responses` "
                "il dizionario con i dati grezzi ricevuti."
            )
        ),
        HumanMessage(
            content=(
                f"Dati da salvare:\n"
                f"- Mappatura Pod: {json.dumps(app_mapping)}\n"
                f"- Metriche Calcolate: {json.dumps(metrics_summary)}\n"
                f"- Risposte Grezze Prometheus: {json.dumps(raw_responses)}"
            )
        )
    ]
    
    response = await llm_with_tools.ainvoke(prompt)
    saved_reports = []
    
    if response.tool_calls:
        target_tool = mongo_tools[0] if mongo_tools else None
        for call in response.tool_calls:
            if target_tool and call["name"] == target_tool.name:
                args = call["args"]
                app_name = args.get("app_name")
                
                
                if not args.get("metrics") and app_name in metrics_summary:
                    args["metrics"] = metrics_summary[app_name]
                if not args.get("raw_prometheus_responses"):
                    args["raw_prometheus_responses"] = raw_responses
                if not args.get("pods") and app_name in app_mapping:
                    args["pods"] = app_mapping[app_name]

                print(f"  [Tool Call MongoDB] Invocazione per app: {app_name} con metrics: {args.get('metrics')}")
                out = await target_tool.ainvoke(args)
                saved_reports.append(str(out))
    else:
        print("  [Persister WARN] Nessuna tool_call rilevata nel messaggio di risposta.")

    return {
        "final_report": "\n".join(saved_reports) if saved_reports else "Nessun dato salvato.",
        "messages": [response]
    }