import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic
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

LINEE GUIDA PER L'USO DEI TOOL:
- Per domande sullo stato istantaneo attuale ricavabili dallo snapshot fornito, rispondi direttamente senza invocare tool.
- Hai accesso all'intera suite di strumenti MCP (storico su database `get_historical_metrics`, query Prometheus `prom_query`, ispezione topologia, ecc.).
- Se la richiesta richiede dati non presenti nello snapshot corrente — come serie temporali storiche, andamenti passati, o verifiche dirette di metriche non campionate (es. riavvii pod, eventi) — seleziona ed esegui autonomamente lo strumento più idoneo tra quelli forniti.
Se per qualunque motivo non sei in grado di formulare una risposta conclusiva 
(ad esempio per complessità del calcolo, ambiguità delle metriche o dati insufficienti), non 
limitarti a dire "non posso rispondere perché mancano informazioni": dichiara chiaramente il 
motivo dell'impossibilità e consiglia esplicitamente all'operatore di sottomettere la richiesta 
a un modello più avanzato.
"""

def extract_clean_text(content) -> str:
    """Estrae il testo pulito gestendo blocchi multipli, thinking e fallback."""
    if isinstance(content, str):
        return content.strip()
        
    if isinstance(content, list):
        text_parts = []
        thinking_parts = []
        
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict):
                # Se è esplicitamente testo
                if item.get("type") == "text" and "text" in item:
                    text_parts.append(item["text"])
                elif "text" in item and item.get("type") != "thinking":
                    text_parts.append(item["text"])
                # Conserva il thinking come fallback di emergenza
                elif item.get("type") == "thinking" or "thinking" in item:
                    val = item.get("thinking") or item.get("text") or ""
                    if isinstance(val, str) and val.strip():
                        thinking_parts.append(val.strip())
            elif hasattr(item, "text"):
                text_parts.append(item.text)
            elif hasattr(item, "content"):
                text_parts.append(str(item.content))
                
        cleaned = " ".join(text_parts).strip()
        if cleaned:
            return cleaned
            
        # Fallback: se il modello ha scritto la risposta solo nel blocco di reasoning
        if thinking_parts:
            return f"[Output da Reasoning]: {' '.join(thinking_parts)}"
            
        return "[Risposta priva di testo]"
        
    return str(content).strip()

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

def get_advisor_llm(model_id: str):
    """Istanzia dinamicamente il modello richiesto."""
    model_id_lower = model_id.lower()
    if "claude" in model_id_lower:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        return ChatAnthropic(
            model_name=model_id,
            api_key=api_key,
            max_tokens=2048
        )
    else:
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        return ChatGoogleGenerativeAI(
            model=model_id,
            google_api_key=api_key,
            temperature=0.0,
            max_retries=5
        )

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

    target_model = state.get("target_model") or "gemini-2.5-flash"
    print(f"\n-> [NODO 4: SRE ADVISOR] Modello: '{target_model}' | Elaborazione richiesta: '{query}'")
    
    llm = get_advisor_llm(target_model)
    
    tools_map = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools) if tools else llm
    
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
    
    if response.tool_calls and tools:
        
        if isinstance(response.content, list):
            clean_content = [b for b in response.content if isinstance(b, dict) and b.get("type") != "thinking"]
            response_to_append = AIMessage(content=clean_content, tool_calls=response.tool_calls)
        else:
            response_to_append = response

        chat_messages.append(response_to_append)

        for call in response.tool_calls:
            tool_name = call.get("name")
            if tool_name in tools_map:
                print(f"  [Advisor Tool Call] Invocazione '{tool_name}': {call['args']}")
                raw_out = await tools_map[tool_name].ainvoke(call["args"])
                out_text = extract_mcp_text(raw_out)
            
                chat_messages.append(
                    ToolMessage(
                        content=out_text,
                        name=tool_name,
                        tool_call_id=call["id"]
                    )
                )
            else:
                print(f"  [Advisor Tool WARN] Tool richiesto non trovato: {tool_name}")
            
        response = await llm_with_tools.ainvoke(chat_messages)
        usage2 = getattr(response, "usage_metadata", None) or response.response_metadata.get("usage_metadata", {})
        prompt_tokens += usage2.get("input_tokens", 0)
        completion_tokens += usage2.get("output_tokens", 0)

    clean_text = extract_clean_text(response.content)
    print(f"\n[Risposta SRE Advisor ({target_model})]:\n{clean_text}\n")
    
    return {
        "user_query": query,
        "advisor_response": clean_text,
        "messages": [AIMessage(content=clean_text)],
        "prompt_tokens": state.get("prompt_tokens", 0) + prompt_tokens,
        "completion_tokens": state.get("completion_tokens", 0) + completion_tokens,
        "total_tokens": state.get("total_tokens", 0) + (prompt_tokens + completion_tokens)
    }