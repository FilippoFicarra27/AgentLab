import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from src.state import ReconState

def extract_mcp_text(tool_output) -> str:
    """Estrae la stringa JSON dal formato TextContent del server MCP."""
    if isinstance(tool_output, list) and len(tool_output) > 0:
        first = tool_output[0]
        if isinstance(first, dict) and "text" in first:
            return first["text"]
        if hasattr(first, "text"):
            return first.text
    if hasattr(tool_output, "content"):
        return str(tool_output.content)
    return str(tool_output)

def parse_prom_result(raw_json: dict) -> dict:
    """Estrae {pod_name: float(valore)} dal JSON grezzo di Prometheus."""
    data_map = {}
    results = raw_json.get("data", {}).get("result", []) if isinstance(raw_json, dict) else []
    for item in results:
        pod = item.get("metric", {}).get("pod")
        value = item.get("value", [None, "0"])[1]
        if pod:
            try:
                data_map[pod] = float(value)
            except ValueError:
                data_map[pod] = 0.0
    return data_map

async def evaluator_node(state: ReconState, tools: list) -> dict:
    print("\n-> [NODO 2: EVALUATOR PROMETHEUS]")
    
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=api_key,
        temperature=0.0,
        max_retries=5
    )
    
    prom_tools = [t for t in tools if t.name == "prom_query"]
    llm_with_tools = llm.bind_tools(prom_tools)
    
    ns = state.get("target_namespace", "default")
    
   
    prompt = [
        SystemMessage(
            content=(
                "Sei un SRE esperto. Devi interrogare Prometheus per raccogliere le metriche hardware dei pod.\n"
                "Usa il tool `prom_query` ed esegui ESATTAMENTE queste 4 interrogazioni PromQL:\n"
                f'1. sum(rate(container_cpu_usage_seconds_total{{namespace="{ns}", container!=""}}[2m])) by (pod)\n'
                f'2. sum(container_memory_working_set_bytes{{namespace="{ns}", container!=""}}) by (pod)\n'
                f'3. sum(rate(container_fs_writes_bytes_total{{namespace="{ns}", container!=""}}[2m])) by (pod)\n'
                f'4. sum(rate(container_network_receive_bytes_total{{namespace="{ns}"}}[2m])) by (pod)\n'
                "Esegui tutte e quattro le chiamate al tool."
            )
        ),
        HumanMessage(content=f"Esegui il recupero delle metriche PromQL per il namespace '{ns}'.")
    ]
    
    response = await llm_with_tools.ainvoke(prompt)
    raw_responses = {}
    
    if response.tool_calls:
        target_tool = prom_tools[0] if prom_tools else None
        for tool_call in response.tool_calls:
            if target_tool and tool_call["name"] == target_tool.name:
                print(f"  [Tool Call Prometheus] Invocazione PromQL: {tool_call['args'].get('query')}")
                raw_out = await target_tool.ainvoke(tool_call["args"])
                text_content = extract_mcp_text(raw_out)
                
                try:
                    payload = json.loads(text_content)
                except Exception:
                    payload = {}
                    
                q_lower = tool_call["args"].get("query", "").lower()
                if "cpu" in q_lower:
                    raw_responses["cpu"] = payload
                elif "memory" in q_lower or "working_set" in q_lower:
                    raw_responses["mem"] = payload
                elif "fs" in q_lower or "writes" in q_lower or "disk" in q_lower:
                    raw_responses["disk"] = payload
                elif "network" in q_lower or "receive" in q_lower:
                    raw_responses["net"] = payload

    
    pod_cpu = parse_prom_result(raw_responses.get("cpu", {}))
    pod_mem = parse_prom_result(raw_responses.get("mem", {}))
    pod_disk = parse_prom_result(raw_responses.get("disk", {}))
    pod_net = parse_prom_result(raw_responses.get("net", {}))

    
    app_mapping = state.get("app_mapping", {})
    metrics_summary = {}
    for app, pods in app_mapping.items():
        total_mem = sum(pod_mem.get(p, 0.0) for p in pods)
        metrics_summary[app] = {
            "cpu_cores": sum(pod_cpu.get(p, 0.0) for p in pods),
            "memory_bytes": total_mem,
            "memory_mb": round(total_mem / (1024 * 1024), 2),
            "disk_write_bps": sum(pod_disk.get(p, 0.0) for p in pods),
            "network_rx_bps": sum(pod_net.get(p, 0.0) for p in pods),
        }

    return {
        "app_mapping": app_mapping,
        "raw_prometheus_responses": raw_responses,
        "metrics_summary": metrics_summary,
        "messages": [response]
    } 