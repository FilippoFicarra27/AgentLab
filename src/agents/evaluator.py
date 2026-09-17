import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from src.state import ReconState

async def evaluator_node(state: ReconState, tools: list) -> dict:
    print("\n-> [NODO 2: EVALUATOR PROMETHEUS]")
    
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=api_key,
        temperature=0.0
    )
    #Filtra i tool passati come parametro includendo quelli esposti dall'MCP di Prometheus
    prom_tools = [t for t in tools if "prom" in t.name]
    llm_with_tools = llm.bind_tools(prom_tools)
    
    pods_info = state.get("discovered_pods", [])
    prompt = [
        SystemMessage(content="Sei un Site Reliability Engineer. Interroga Prometheus via PromQL usando i tool disponibili per verificare lo stato e le risorse dei pod."),
        HumanMessage(content=f"Dati scoperti da Kubernetes: {pods_info}\nVerifica lo stato con le metriche Prometheus.")
    ]
    
    response = await llm_with_tools.ainvoke(prompt)
    metrics_data = {} #dizionario in cui memorizzare gli output grezzi restituiti dall' MCP Server per ogni tool invocato
    
    if response.tool_calls: #Verifica se la response contiene chiamate a tool
        for tool_call in response.tool_calls:
            #Verifica se tra la lista dei tool è presente quello richiesto da Gemini
            target_tool = next((t for t in prom_tools if t.name == tool_call["name"]), None)
            if target_tool: #Se il tool è presente, lo invoca
                print(f"  [Tool Call Prometheus] Invocazione: {tool_call['name']} con argomenti: {tool_call['args']}")
                tool_output = await target_tool.ainvoke(tool_call["args"])

                #Memorizza la risposta restituita da prometheus
                metrics_data[tool_call["name"]] = str(tool_output)

    summary_prompt = [
        SystemMessage(content="Genera un report chiaro e leggibile con: 1) Applicazioni trovate, 2) Metriche estratte, 3) Stato complessivo."),
        HumanMessage(content=f"Dati ricognizione K8s: {pods_info}\nDati telemetrici Prometheus: {metrics_data}")
    ]
    final_report = await llm.ainvoke(summary_prompt)
    
    return {
        "metrics_summary": metrics_data,
        "final_report": str(final_report.content),
        "messages": [final_report]
    }