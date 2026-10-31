import os
import time
import asyncio
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool

load_dotenv()


api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
if not api_key:
    print("[ERRORE CRITICO] Chiave GOOGLE_API_KEY o GEMINI_API_KEY non trovata nel file .env!")
    exit(1)

print(f"[OK] Google API Key rilevata (prefisso: {api_key[:8]}...)")

MODEL_ID = "gemini-3.6-flash"

@tool
def get_cluster_status(namespace: str) -> str:
    """Restituisce lo stato fittizio dei nodi e dei pod nel namespace specificato."""
    return f"Namespace {namespace}: 3 nodi Ready, 12 pod Running, 0 riavvii."


async def invoke_with_retry(llm_instance, messages, max_retries: int = 5, initial_delay: float = 3.0):
    """
    Esegue l'invocazione gestendo picchi di carico (503 Service Unavailable)
    tramite exponential backoff progressivo.
    """
    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        try:
            t0 = time.perf_counter()
            response = await llm_instance.ainvoke(messages)
            elapsed = time.perf_counter() - t0
            return response, elapsed, attempt
        except Exception as e:
            err_msg = str(e)
            print(f"  [Tentativo {attempt}/{max_retries}] Errore riscontrato: {err_msg[:120]}...")
            
            # Se è un errore di capacità transitoria o rate limit, attende prima di riprovare
            if "503" in err_msg or "UNAVAILABLE" in err_msg or "429" in err_msg:
                if attempt == max_retries:
                    raise e
                print(f"  -> Server sovraccarico. Pausa di {delay:.1f} secondi prima del prossimo tentativo...")
                await asyncio.sleep(delay)
                delay *= 2.0  # Raddoppia il tempo di attesa
            else:
                # Errore non transitorio (es. modello inesistente o chiave invalida)
                raise e


async def test_gemini_basic():
    print("\n" + "=" * 80)
    print(f"TEST 1: Invocazione Diretta Chat ({MODEL_ID})")
    print("=" * 80)

    llm = ChatGoogleGenerativeAI(
        model=MODEL_ID,
        google_api_key=api_key,
        temperature=0.0,
        max_retries=3,
        timeout=60.0
    )

    messages = [
        SystemMessage(content="Sei un assistente diagnostico SRE."),
        HumanMessage(content="Rispondi con una sola riga riassumendo cos'è il CPU Throttling in Kubernetes.")
    ]

    try:
        response, elapsed, attempts = await invoke_with_retry(llm, messages)
        usage = getattr(response, "usage_metadata", None) or response.response_metadata.get("usage_metadata", {})
        
        print(f"[SUCCESSO al tentativo {attempts}]")
        print(f"Latenza: {elapsed:.2f} s")
        print(f"Token Input: {usage.get('input_tokens', 0)} | Token Output: {usage.get('output_tokens', 0)}")

        if isinstance(response.content, list):
            text_content = " ".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in response.content])
        else:
            text_content = str(response.content)
        print(f"Risposta: {text_content.strip()}\n")
        
        return True
    except Exception as e:
        print(f"[FALLITO] Impossibile completare il test base: {e}\n")
        return False


async def test_gemini_tool_calling():
    print("=" * 80)
    print(f"TEST 2: Tool Calling & Schema Binding ({MODEL_ID})")
    print("=" * 80)

    llm = ChatGoogleGenerativeAI(
        model=MODEL_ID,
        google_api_key=api_key,
        temperature=0.0,
        max_retries=3,
        timeout=60.0
    )

    tools = [get_cluster_status]
    llm_with_tools = llm.bind_tools(tools)

    messages = [
        SystemMessage(content="Sei un SRE Advisor. Usa gli strumenti a disposizione se necessario."),
        HumanMessage(content="Qual è lo stato del namespace 'default'? Controllalo con il tool appropriato.")
    ]

    try:
        response, elapsed, attempts = await invoke_with_retry(llm_with_tools, messages)
        print(f"[SUCCESSO al tentativo {attempts}]")
        print(f"Latenza: {elapsed:.2f} s")
        
        if response.tool_calls:
            print(f"Tool invocato correttamente dal modello: {response.tool_calls}")
        else:
            print(f"Risposta testuale senza tool: {response.content.strip()}")
        print("\n")
        return True
    except Exception as e:
        print(f"[FALLITO] Impossibile completare il test tool calling: {e}\n")
        return False


async def main():
    print("=" * 80)
    print(f"AVVIO SUITE DI DIAGNOSTICA PER {MODEL_ID.upper()}")
    print("=" * 80)

    ok_basic = await test_gemini_basic()
    ok_tools = await test_gemini_tool_calling()

    print("=" * 80)
    print("ESITO FINALE:")
    print(f"- Invocazione standard: {'SUPERATO' if ok_basic else 'NON SUPERATO'}")
    print(f"- Tool Calling:         {'SUPERATO' if ok_tools else 'NON SUPERATO'}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())