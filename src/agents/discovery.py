import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from src.state import ReconState

def extract_mcp_text(tool_output) -> str:
    if isinstance(tool_output, list) and len(tool_output) > 0:
        first = tool_output[0]
        if isinstance(first, dict) and "text" in first:
            return first["text"]
        if hasattr(first, "text"):
            return first.text
    if hasattr(tool_output, "content"):
        return str(tool_output.content)
    return str(tool_output)

async def discovery_node(state: ReconState, tools: list) -> dict:
    print("\n-> [NODO 1: DISCOVERY KUBERNETES VIA MCP]")
    
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=api_key,
        temperature=0.0,
        max_retries=5
    )
    
    k8s_tools = [t for t in tools if t.name == "get_app_pod_mapping"]
    llm_with_tools = llm.bind_tools(k8s_tools)
    
    ns = state.get("target_namespace", "default")
    prompt = [
        SystemMessage(content="Esegui la mappatura delle applicazioni usando get_app_pod_mapping."),
        HumanMessage(content=f"Estrai la mappa app/pod per il namespace '{ns}'.")
    ]
    
    response = await llm_with_tools.ainvoke(prompt)
    app_mapping = {}
    discovered_pods = []
    
    if response.tool_calls:
        target_tool = k8s_tools[0] if k8s_tools else None
        for tool_call in response.tool_calls:
            if target_tool and tool_call["name"] == target_tool.name:
                print(f"  [Tool Call K8s MCP] Invocazione: {tool_call['name']}")
                raw_out = await target_tool.ainvoke(tool_call["args"])
                text_content = extract_mcp_text(raw_out)
                
                try:
                    parsed = json.loads(text_content)
                    if isinstance(parsed, dict) and "error" not in parsed:
                        app_mapping = parsed
                        for pods in app_mapping.values():
                            discovered_pods.extend(pods)
                        print(f"  [Discovery SUCCESS] Trovate app: {list(app_mapping.keys())}")
                except Exception as e:
                    print(f"  [Discovery ERROR] Parsing mapping fallito: {e} | Raw: {text_content}")

    return {
        "discovered_pods": discovered_pods,
        "app_mapping": app_mapping,
        "messages": [response]
    }