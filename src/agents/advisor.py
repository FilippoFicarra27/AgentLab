import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.types import interrupt
from src.state import ReconState

ADVISOR_SYSTEM_PROMPT = """Sei un SRE Advisor esperto in Kubernetes. 
Hai a disposizione l'istantanea esatta delle metriche raccolte e persistite sul database.
Il tuo compito è rispondere alle richieste dell'amministratore di sistema analizzando i carichi di lavoro.
Fornisci raccomandazioni concrete su:
- Applicazioni che saturano CPU o memoria
- Opportunità di scaling orizzontale (HPA) o riduzione repliche
- Identificazione di carichi anomali o idle
Basa le risposte esclusivamente sulle metriche reali fornite.

Nel caso in cui venga effettuata una richiesta di informazioni sull'andamento temporale delle metriche raccolte, c'è un tool a disposizione:
- `get_historical_metrics`: Usalo SE E SOLO SE l'operatore chiede informazioni sull'andamento temporale,
  trend storici, variazioni o confronti con le ore precedenti (es. "ultime 2 ore", "come è cambiato").
  In generale, può essere chiesto un qualunque intervallo temporale, sia di ore, ma anche di giorni, mesi (es. "ultimi 2 giorni", "ultimo mese", "ultimi 2 mesi").
  Per domande sullo stato istantaneo attuale, rispondi direttamente usando il contesto fornito senza invocare il tool.
  Se l'utente non specifica l'applicazione, usa il tool 'get_historical_metrics' per ciascuna applicazione scoperta nella topologia.
"""
def extract_clean_text(content) -> str:
    """Estrae la stringa pura da response.content anche se è una lista di dizionari."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
            elif hasattr(item, "text"):
                parts.append(item.text)
            else:
                parts.append(str(item))
        return " ".join(parts).strip()
    return str(content)

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

async def sre_advisor_node(state: ReconState, tools: list) -> dict:
 
    user_input = interrupt("Inserisci una richiesta per l'SRE Advisor (o conferma a vuoto per uscire):")
    
    query = ""
    if isinstance(user_input, str):
        query = user_input.strip()
    elif isinstance(user_input, dict):
        query = str(user_input.get("user_query") or user_input.get("query") or "").strip()
        
    if not query:
        query = (state.get("user_query") or "").strip()

    if not query:
        print("\n-> [SRE ADVISOR] Nessuna richiesta inoltrata dall'operatore. Conclusione a costo zero.")
        return {
            "user_query": "",
            "advisor_response": "Nessuna interrogazione inserita. Workflow terminato.",
            "prompt_tokens": state.get("prompt_tokens", 0),
            "completion_tokens": state.get("completion_tokens", 0),
            "total_tokens": state.get("total_tokens", 0)
        }

    print(f"\n-> [NODO 4: SRE ADVISOR] Elaborazione richiesta: '{query}'")
    
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=api_key,
        temperature=0.2,
        max_retries=5
    )
    
    history_tools = [t for t in tools if t.name == "get_historical_metrics"]
    llm_with_tools = llm.bind_tools(history_tools) if history_tools else llm
    
    mapping = state.get("app_mapping", {})
    metrics = state.get("metrics_summary", {})
    
    chat_messages = [
        SystemMessage(content=ADVISOR_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Topologia e Pod Attuali: {json.dumps(mapping)}\n"
                f"Metriche Istantanee Correnti: {json.dumps(metrics)}\n\n"
                f"Richiesta operatore: {query}"
            )
        )
    ]
    
    response = await llm_with_tools.ainvoke(chat_messages)
    
    usage = getattr(response, "usage_metadata", None) or response.response_metadata.get("usage_metadata", {})
    prompt_tokens = usage.get("input_tokens", 0)
    completion_tokens = usage.get("output_tokens", 0)
    
    if response.tool_calls and history_tools:
        target_tool = history_tools[0]
        chat_messages.append(response)
        
        for call in response.tool_calls:
            if call["name"] == target_tool.name:
                print(f"  [Advisor Tool Call] Consultazione storico: {call['args']}")
                raw_out = await target_tool.ainvoke(call["args"])
                out_text = extract_mcp_text(raw_out)
                
                chat_messages.append(
                    ToolMessage(
                        content=out_text,
                        name=target_tool.name,
                        tool_call_id=call["id"]
                    )
                )
        
        response = await llm.ainvoke(chat_messages)
        usage2 = getattr(response, "usage_metadata", None) or response.response_metadata.get("usage_metadata", {})
        prompt_tokens += usage2.get("input_tokens", 0)
        completion_tokens += usage2.get("output_tokens", 0)

    clean_text = extract_clean_text(response.content)
    print(f"\n[Risposta SRE Advisor]:\n{clean_text}\n")
    
    return {
        "user_query": query,
        "advisor_response": clean_text,
        "messages": [AIMessage(content=clean_text)],
        "prompt_tokens": state.get("prompt_tokens", 0) + prompt_tokens,
        "completion_tokens": state.get("completion_tokens", 0) + completion_tokens,
        "total_tokens": state.get("total_tokens", 0) + (prompt_tokens + completion_tokens)
    }