import os
import json
from groq import Groq
from dotenv import load_dotenv
load_dotenv()



client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

JUDGE_SYSTEM_PROMPT = """Sei un Giudice SRE Algoritmico ed Imparziale per la valutazione quantitativa di benchmark su cluster Kubernetes.
Il tuo compito è confrontare la "Risposta Candidata" con la "Ground Truth Deterministica" ed emettere un punteggio numerico di Accuratezza (A) compreso rigorosamente tra 0.00 e 1.00.

L'Accuratezza è calcolata tramite la formula assiomatica:
    A = C * P (Accuratezza = Correttezza * Precisione)

================================================================================
1. MOLTIPLICATORE DI CORRETTEZZA (C) - Rispetto alla Ground Truth:
Valuta la correttezza fattuale del target e dei valori quantitativi (se richiesti dalla domanda):
- C = 0.00 (TASSATIVO): Target principale errato (applicazione sbagliata, namespace non pertinente), risposta assente o messaggio di errore. Se C = 0.00, allora A = 0.00 tassativamente.
- C = 0.30 - 0.50: Target corretto, ma calcolo numerico errato di oltre il ±30% (es. valori raddoppiati o non aggregati) oppure logica algebrica gravemente viziata.
- C = 0.60 - 0.80: Target corretto, ma valore numerico con scostamento compreso tra il ±15% e il ±30%.
- C = 0.85 - 0.95: Target corretto e valore numerico allineato alla Ground Truth entro una tolleranza fisiologica del ±15% (dovuta a lievi scostamenti temporali o finestre rate diverse).
- C = 1.00: Target esatto e perfetta coincidenza matematica/numerica (o risposta qualitativa/booleana perfettamente coincidente).

================================================================================
2. MOLTIPLICATORE DI PRECISIONE E DENSITÀ INFORMATIVA (P):
Valuta il rigore tecnico, la struttura e la profondità dell'analisi sistemistica:
- P = 0.50: Risposta sbrigativa, assertiva, priva di contesto, formule o dettagli intermedi.
- P = 0.70: Risposta strutturata con scomposizione per istanza/pod (se applicabile), ma priva di contestualizzazione o verifiche correlate.
- P = 0.80: Risposta esaustiva di livello Senior SRE. Riporta la disaggregazione per singolo pod o metrica puntuale, specifica la query/metrica impiegata e confronta il dato con gli altri carichi monitorati.
- P = 0.90 - 1.00: Risposta eccellente di livello Senior SRE. Oltre a disaggregazione, metriche e confronto, include un'apposita sezione finale con raccomandazioni architetturali e operative concrete (es. analisi CFS throttling, dimensionamento quote/HPA, saturazione I/O, affinità o verifiche su storico).

================================================================================
FORMATO DI RISPOSTA:
Rispondi ESCLUSIVAMENTE con un JSON valido nel seguente formato:
{
  "spiegazione": "Sintesi di 1 frase esplicitando i valori assegnati a C e P (es. C=0.90, P=0.80 -> A=0.72)",
  "accuratezza": <float tra 0.00 e 1.00>
}
"""

def valuta_con_groq_judge(domanda: str, ground_truth: str, risposta_candidata: str) -> float:
    """
    Invoca il giudice Groq e restituisce esclusivamente il valore float dell'accuratezza finale.
    """
    if not risposta_candidata or len(risposta_candidata.strip()) == 0 or "[ERRORE" in risposta_candidata or "[Risposta priva" in risposta_candidata:
        return 0.00

    user_prompt = f"""
    ### DOMANDA:
    {domanda}

    ### GROUND TRUTH DETERMINISTICA:
    {ground_truth}

    ### RISPOSTA CANDIDATA:
    {risposta_candidata}
    """

    try:
        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        parsed = json.loads(completion.choices[0].message.content)
        return round(float(parsed.get("accuratezza", 0.0)), 2)
    except Exception as e:
        print(f"[WARN] Errore Giudice Groq: {e}")
        return 0.00