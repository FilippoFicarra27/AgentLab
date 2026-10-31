import os
import json
from datetime import datetime, timezone

TRACKER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openai_usage_tracking.json")


OPENAI_RATES = {
    "gpt-4o-mini": {
        "input_rate": 0.15 / 1_000_000,
        "output_rate": 0.60 / 1_000_000,
    },
    "gpt-4o": {
        "input_rate": 2.50 / 1_000_000,
        "output_rate": 10.00 / 1_000_000,
    }
}

def load_tracking_data() -> dict:
    if not os.path.exists(TRACKER_FILE):
        return {
            "totale_complessivo_usd": 0.0,
            "totale_token_input": 0,
            "totale_token_output": 0,
            "dettaglio_modelli": {
                "gpt-4o-mini": {"costo_usd": 0.0, "in_tokens": 0, "out_tokens": 0, "calls": 0},
                "gpt-4o": {"costo_usd": 0.0, "in_tokens": 0, "out_tokens": 0, "calls": 0}
            },
            "sessioni": []
        }
    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def track_openai_call(model_id: str, prompt_tokens: int, completion_tokens: int, livello: str, q_num: int) -> float:
    """
    Calcola il costo della singola chiamata, lo registra nel file locale e restituisce il costo in USD.
    Ignora i modelli non OpenAI.
    """
    rate_info = OPENAI_RATES.get(model_id.lower())
    if not rate_info:
        return 0.0

    costo_chiamata = (prompt_tokens * rate_info["input_rate"]) + (completion_tokens * rate_info["output_rate"])
    
    data = load_tracking_data()
    
    
    data["totale_complessivo_usd"] = round(data.get("totale_complessivo_usd", 0.0) + costo_chiamata, 6)
    data["totale_token_input"] = data.get("totale_token_input", 0) + prompt_tokens
    data["totale_token_output"] = data.get("totale_token_output", 0) + completion_tokens
    
    
    if model_id.lower() not in data["dettaglio_modelli"]:
        data["dettaglio_modelli"][model_id.lower()] = {"costo_usd": 0.0, "in_tokens": 0, "out_tokens": 0, "calls": 0}
        
    m_data = data["dettaglio_modelli"][model_id.lower()]
    m_data["costo_usd"] = round(m_data["costo_usd"] + costo_chiamata, 6)
    m_data["in_tokens"] += prompt_tokens
    m_data["out_tokens"] += completion_tokens
    m_data["calls"] += 1
    
    
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "livello": livello,
        "question_id": q_num,
        "model": model_id,
        "in_tokens": prompt_tokens,
        "out_tokens": completion_tokens,
        "costo_usd": round(costo_chiamata, 6)
    }
    data.setdefault("sessioni", []).append(record)
    
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    return costo_chiamata

def get_budget_summary() -> str:
    """Restituisce una riga sintetica con la spesa accumulata fino a questo momento."""
    data = load_tracking_data()
    tot = data.get("totale_complessivo_usd", 0.0)
    mini_c = data.get("dettaglio_modelli", {}).get("gpt-4o-mini", {}).get("costo_usd", 0.0)
    gpt4o_c = data.get("dettaglio_modelli", {}).get("gpt-4o", {}).get("costo_usd", 0.0)
    return f"Spesa cumulata OpenAI: ${tot:.4f} (mini: ${mini_c:.4f} | 4o: ${gpt4o_c:.4f})"