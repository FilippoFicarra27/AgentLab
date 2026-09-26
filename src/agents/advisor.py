import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
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
"""

async def sre_advisor_node(state: ReconState) -> dict:
    print("\n-> [NODO 4: SRE INTERACTIVE ADVISOR]")
    
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=api_key,
        temperature=0.2
    )
    
    metrics = state.get("metrics_summary", {})
    mapping = state.get("app_mapping", {})

    user_input = interrupt("Inserisci una richiesta per l'SRE Advisor (o conferma a vuoto per uscire):")
    
    # Recupera l'input
    query = ""
    if isinstance(user_input, str):
        query = user_input.strip()
    elif isinstance(user_input, dict):
        query = str(user_input.get("user_query") or user_input.get("query") or "").strip()
    
    # Fallback sullo stato se non è stato passato tramite il valore di resume
    if not query:
        query = (state.get("user_query") or "").strip()

    # Se l'utente ha premuto solo INVIO o ha inviato stringa vuota:
    if not query:
        print("-> [SRE ADVISOR] Nessuna richiesta inserita. Conclusione a costo zero.")
        msg = AIMessage(content="Nessuna richiesta formulata dall'operatore. Sessione terminata.")
        return {
            "user_query": "",
            "advisor_response": msg.content,
            "messages": [msg]
        }
    
    prompt = [
        SystemMessage(content=ADVISOR_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Topologia Pod: {json.dumps(mapping)}\n"
                f"Metriche di Consumo: {json.dumps(metrics)}\n\n"
                f"Domanda dell'operatore: {query}"
            )
        )
    ]
    
    response = await llm.ainvoke(prompt)
    print(f"\n[SRE Advisor]:\n{response.content}\n")
    
    return {
        "advisor_response": response.content,
        "messages": [response]
    }