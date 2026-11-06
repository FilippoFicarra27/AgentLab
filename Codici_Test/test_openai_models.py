import os
import asyncio
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage
from src.agents.advisor import get_advisor_llm, extract_clean_text
from cost_tracker import track_openai_call, get_budget_summary

load_dotenv()


api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("[ERRORE CRITICO] OPENAI_API_KEY non trovata nel file .env!")
    exit(1)
print(f"[OK] OPENAI_API_KEY rilevata (prefisso: {api_key[:8]}...)\n")

MODELS_TO_TEST = [
    {"name": "GPT-4o Mini", "id": "gpt-4o-mini"},
    {"name": "GPT-4o", "id": "gpt-4o"}
]

test_prompt = "Rispondi esclusivamente con la parola 'OK' e nient'altro."

async def test_single_model(model_meta: dict):
    model_id = model_meta["id"]
    model_name = model_meta["name"]
    print(f"--- Test in corso per: {model_name} ({model_id}) ---")
    
    try:
        llm = get_advisor_llm(model_id)
        messages = [
            SystemMessage(content="Sei un assistente di test."),
            HumanMessage(content=test_prompt)
        ]
        
        response = await llm.ainvoke(messages)
        
        usage = getattr(response, "usage_metadata", None) or response.response_metadata.get("usage_metadata", {})
        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)
        clean_text = extract_clean_text(response.content)
        
        print(f"  Risposta ricevuta: '{clean_text}'")
        print(f"  Token In: {prompt_tokens} | Token Out: {completion_tokens}")
        
        costo = track_openai_call(
            model_id=model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            livello="TEST",
            q_num=0
        )
        print(f"  Costo registrato: ${costo:.6f}\n")
        return True
        
    except Exception as e:
        print(f"  [ERRORE CHIAMATA {model_name}]: {e}\n")
        return False

async def main():
    print("=" * 80)
    print("TEST ISOLATO CHIAMATE OPENAI & BILLING TRACKER")
    print("=" * 80 + "\n")
    
    results = []
    for m in MODELS_TO_TEST:
        success = await test_single_model(m)
        results.append(success)
        
    print("=" * 80)
    if all(results):
        print("[SUCCESSO] Entrambi i modelli OpenAI rispondono correttamente.")
        print(f"[MONITOR SPESA AGGIORNATO]: {get_budget_summary()}")
    else:
        print("[FALLIMENTO] Almeno uno dei modelli ha riscontrato un errore.")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())