import asyncio
from dotenv import load_dotenv
import json
import os
import sys
import textwrap
import time
from benchmark_script import deterministic_oracle_answer, main as run_deterministic_baseline
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from src.agents.advisor import extract_clean_text, extract_mcp_text, get_advisor_llm
from src.tools.mcp_manager import load_mcp_tools
from tabulate import tabulate

load_dotenv()

MODELS_TO_BENCHMARK = [
    {"name": "Gemini 2.5 Flash", "id": "gemini-2.5-flash"},
    {"name": "Gemini 3.8 Flash", "id": "gemini-3.8-flash"},
    {"name": "Claude Opus 5.5", "id": "claude-opus-5-5"},
    {"name": "Claude Sonnet 5.5", "id": "claude-sonnet-5-5"},
]

LEVEL1_SYSTEM_PROMPT = """Sei un SRE Advisor esperto in Kubernetes.
Il tuo compito è rispondere alle richieste dell'amministratore di sistema analizzando i carichi di lavoro del cluster.
Non hai a disposizione metriche pre-calcolate né un riepilogo della topologia nel tuo contesto iniziale.
Per rispondere in modo accurato, devi utilizzare autonomamente gli strumenti MCP forniti (interrogando le API di Kubernetes, Prometheus o i database di metriche).
Fornisci raccomandazioni concrete, basando le risposte esclusivamente sui dati reali ricavati tramite i tool. Se per qualunque motivo non sei in grado di formulare una risposta 
conclusiva (ad esempio per complessità del calcolo, ambiguità delle metriche o dati insufficienti), non limitarti a 
dire "non posso rispondere perché mancano informazioni": dichiara chiaramente il motivo dell'impossibilità e consiglia 
esplicitamente all'operatore di sottomettere la richiesta a un modello più avanzato."""


def load_questions_file() -> dict:
  q_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "questions.json")
  if not os.path.exists(q_file):
    raise FileNotFoundError(f"File questions.json non trovato: {q_file}")
  with open(q_file, "r", encoding="utf-8") as f:
    return json.load(f)


async def call_advisor_for_model(model_meta: dict, question: str, tools: list, max_steps: int = 4):
  model_id = model_meta["id"]
  llm = get_advisor_llm(model_id)

  tools_map = {t.name: t for t in tools}
  llm_with_tools = llm.bind_tools(tools) if tools else llm

  
  chat_messages = [
      SystemMessage(content=LEVEL1_SYSTEM_PROMPT),
      HumanMessage(content=f"Richiesta operatore: {question}"),
  ]

  t0 = time.perf_counter()
  prompt_tokens = 0
  completion_tokens = 0

  try:
    response = await llm_with_tools.ainvoke(chat_messages)
  except Exception as e:
    return {
        "system": model_meta["name"],
        "latency_sec": time.perf_counter() - t0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "response": f"[ERRORE DI CHIAMATA]: {str(e)}",
    }

  usage = getattr(response, "usage_metadata", None) or response.response_metadata.get("usage_metadata", {})
  prompt_tokens += usage.get("input_tokens", 0)
  completion_tokens += usage.get("output_tokens", 0)

  
  step_count = 0
  while response.tool_calls and tools and step_count < max_steps:
    step_count += 1

    if isinstance(response.content, list):
      clean_content = [b for b in response.content if isinstance(b, dict) and b.get("type") != "thinking"]
      response_to_append = AIMessage(content=clean_content, tool_calls=response.tool_calls)
    else:
      response_to_append = response

    chat_messages.append(response_to_append)

    for call in response.tool_calls:
      t_name = call.get("name")
      if t_name in tools_map:
        try:
          raw_out = await tools_map[t_name].ainvoke(call["args"])
          chat_messages.append(
              ToolMessage(
                  content=extract_mcp_text(raw_out),
                  name=t_name,
                  tool_call_id=call["id"],
              )
          )
        except Exception as tool_err:
          chat_messages.append(
              ToolMessage(
                  content=f"Errore esecuzione tool: {tool_err}",
                  name=t_name,
                  tool_call_id=call["id"],
              )
          )

    try:
      response = await llm_with_tools.ainvoke(chat_messages)
      usage_step = getattr(response, "usage_metadata", None) or response.response_metadata.get("usage_metadata", {})
      prompt_tokens += usage_step.get("input_tokens", 0)
      completion_tokens += usage_step.get("output_tokens", 0)
    except Exception as e:
      return {
          "system": model_meta["name"],
          "latency_sec": time.perf_counter() - t0,
          "prompt_tokens": prompt_tokens,
          "completion_tokens": completion_tokens,
          "total_tokens": prompt_tokens + completion_tokens,
          "response": f"[ERRORE STEP {step_count}]: {str(e)}",
      }


  if response.tool_calls and not extract_clean_text(response.content):
    chat_messages.append(
        HumanMessage(content="Hai raggiunto il limite di passaggi. Sintetizza ora una risposta finale all'operatore sulla base di tutti i dati raccolti finora, senza usare ulteriori strumenti.")
    )
    try:
        
        final_summary_response = await llm.ainvoke(chat_messages)
        clean_text = extract_clean_text(final_summary_response.content)
        if clean_text:
            response = final_summary_response
    except Exception:
        pass

  latency = time.perf_counter() - t0
  clean_text = extract_clean_text(response.content)

  return {
      "system": model_meta["name"],
      "latency_sec": latency,
      "prompt_tokens": prompt_tokens,
      "completion_tokens": completion_tokens,
      "total_tokens": prompt_tokens + completion_tokens,
      "response": clean_text,
  }


def wrap_text(t: str, width: int = 65) -> str:
  lines = []
  for line in t.split("\n"):
    wrapped = textwrap.wrap(line, width=width)
    if wrapped:
      lines.extend(wrapped)
    else:
      lines.append("")
  return "\n".join(lines).strip()


async def run():
  q_map = load_questions_file()

  print("Connessione ai server MCP in corso...")
  client, tools = await load_mcp_tools()
  print(f"Tool caricati con successo ({len(tools)} disponibili).")

  
  print("\n" + "=" * 80)
  print("FASE 0: ESECUZIONE COMPLETA SCRIPT DETERMINISTICO (BASELINE ORACLE)")
  print("=" * 80)
  app_mapping, metrics_summary = run_deterministic_baseline()

  print("\n" + "=" * 80)
  print("LIVELLO 1: BENCHMARK ZERO-CONTEXT (UNCONSTRAINED AGENTS - REACT MULTI-STEP)")
  print("Gli agenti riceveranno solo le domande senza alcun contesto pre-calcolato.")
  print("=" * 80 + "\n")

  while True:
    print("=" * 80)
    user_choice = await asyncio.to_thread(
        input,
        "Scegli una domanda da sottomettere (1-10) oppure premi INVIO / altro tasto per uscire: ",
    )
    user_choice = user_choice.strip()

    if not user_choice.isdigit():
      print("\nUscita dalla sessione.")
      break

    q_num = int(user_choice)
    if q_num < 1 or q_num > 10:
      print(f"\nIl numero {q_num} non è compreso tra 1 e 10. Uscita.")
      break

    q_key = str(q_num)
    q_text = q_map.get(q_key, "")

    print("\n" + "-" * 110)
    print(f"ESECUZIONE DOMANDA [Q{q_num}] (ZERO CONTEXT): {q_text}")
    print("-" * 110)

    
    t_script = time.perf_counter()
    oracle_res = deterministic_oracle_answer(q_num, app_mapping, metrics_summary)
    script_lat = time.perf_counter() - t_script

    print("Invocazione parallela modelli in corso...")
    tasks = [call_advisor_for_model(m, q_text, tools, max_steps=4) for m in MODELS_TO_BENCHMARK]
    llm_results = await asyncio.gather(*tasks)

    rows = [[
        "Script Deterministico",
        f"{script_lat * 1000:.2f} ms",
        0,
        0,
        0,
        wrap_text(oracle_res),
    ]]

    for res in llm_results:
      rows.append([
          res["system"],
          f"{res['latency_sec']:.2f} s",
          res["prompt_tokens"],
          res["completion_tokens"],
          res["total_tokens"],
          wrap_text(res["response"]),
      ])

    headers = [
        "Sistema",
        "Latenza",
        "In Tok",
        "Out Tok",
        "Tot Tok",
        "Risposta Completa",
    ]
    print("\n" + tabulate(rows, headers=headers, tablefmt="fancy_grid"))
    print("\n")

  print("\nBenchmark Livello 1 terminato.")


if __name__ == "__main__":
  asyncio.run(run())