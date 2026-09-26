import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
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
    query = (state.get("user_query") or "").strip()
    
    
    if not query:
        print("\n-> [SRE ADVISOR] Nessuna richiesta inoltrata dall'operatore. Conclusione sessione.")
        return {
            "advisor_response": "Nessuna interrogazione inserita. Workflow terminato."
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