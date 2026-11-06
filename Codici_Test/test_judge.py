import os
import json
from dotenv import load_dotenv
from evaluator_judge import valuta_con_groq_judge

load_dotenv()

# Verifica presenza chiave prima del test
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    print("[ERRORE CRITICO] GROQ_API_KEY non trovata nel file .env!")
    exit(1)
print(f"[OK] GROQ_API_KEY caricata correttamente (prefisso: {api_key[:8]}...)\n")

domanda_test = (
    "Quale applicazione tra quelle monitorate assorbe il maggior rate di CPU, "
    "e quanti core impiega complessivamente?"
)
ground_truth_test = (
    "L'applicazione con il maggior consumo di CPU è 'worker-app' con un assorbimento "
    "complessivo pari a 0.368 core (368m) distribuito su 2 repliche."
)

casi_di_test = [
    {
        "nome": "1. Risposta Perfetta ed Esaustiva (C=1.0, P=0.8-1.0)",
        "risposta": (
            "Dall'analisi delle metriche di utilizzo CPU nel cluster, l'applicazione con il "
            "maggior carico è 'worker-app'. Essa impiega complessivamente circa 0.368 core (368 millicore). "
            "Il carico è ripartito su due repliche attive: worker-app-pod-1 (185m) e worker-app-pod-2 (183m)."
        ),
        "score_atteso": "Alto (>= 0.80)"
    },
    {
        "nome": "2. Risposta Corretta ma Minimale/Secca (C=1.0, P=0.3-0.4)",
        "risposta": "worker-app, 0.37 core.",
        "score_atteso": "Basso/Medio (0.30 - 0.40)"
    },
    {
        "nome": "3. Risposta con Target Corretto ma Valore Completamente Sbagliato (C=0.5, P=0.5-0.7)",
        "risposta": "L'applicazione con il maggior consumo di CPU è worker-app e consuma circa 2.5 core.",
        "score_atteso": "Basso (0.25 - 0.35)"
    },
    {
        "nome": "4. Risposta Errata / Allucinata (C=0.0 -> A=0.0)",
        "risposta": "L'applicazione con maggior consumo è frontend-service con 0.12 core.",
        "score_atteso": "Zero esatto (0.00)"
    },
    {
        "nome": "5. Risposta Fallita / Vuota (Fallback immediato del codice)",
        "risposta": "[ERRORE DI CHIAMATA]: Connection timeout",
        "score_atteso": "Zero esatto (0.00) senza chiamata API"
    }
]

print("=" * 80)
print("TEST UNITARIO ISOLATO: LLM-AS-A-JUDGE (Llama 3.3 70B su Groq)")
print("=" * 80)

for caso in casi_di_test:
    print(f"\n--- Scenario: {caso['nome']} ---")
    score = valuta_con_groq_judge(
        domanda=domanda_test,
        ground_truth=ground_truth_test,
        risposta_candidata=caso["risposta"]
    )
    print(f"Punteggio Calcolato: {score:.2f}  |  Atteso: {caso['score_atteso']}")

print("\n" + "=" * 80)
print("Test completato con successo.")