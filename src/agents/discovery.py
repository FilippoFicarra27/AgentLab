import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from src.state import ReconState

async def discovery_node(state: ReconState, tools: list) -> dict:
    print("\n-> [NODO 1: DISCOVERY KUBERNETES VIA MCP]")
    
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=api_key,
        temperature=0.0
    )
    
    # Filtra i tool esposti dal server MCP Server di Kubernetes
    k8s_tools = [t for t in tools if t.name in ["get_pods", "get_deployments", "get_services"]]
    llm_with_tools = llm.bind_tools(k8s_tools)
    
    ns = state.get("target_namespace", "default")
    prompt = [
        SystemMessage(content="Sei un agente esperto Kubernetes. Interroga il cluster usando i tool MCP a tua disposizione per elencare i pod attivi."),
        HumanMessage(content=f"Verifica quali pod sono attualmente in esecuzione nel namespace '{ns}'.")
    ]
    
    response = await llm_with_tools.ainvoke(prompt)
    
    discovered_pods = []
    if response.tool_calls: #Verifica se la response contiene chiamate a tool
        for tool_call in response.tool_calls:
            #Verifica se tra la lista dei tool è presente quello richiesto da Gemini
            target_tool = next((t for t in k8s_tools if t.name == tool_call["name"]), None)
            if target_tool: #Se il tool è presente, lo invoca
                print(f"  [Tool Call K8s MCP] Invocazione: {tool_call['name']} con argomenti: {tool_call['args']}")
                tool_output = await target_tool.ainvoke(tool_call["args"])
                discovered_pods.append(str(tool_output))
            
    return {
        "discovered_pods": discovered_pods,
        "messages": [response]
    }