import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
import json
import os
import sys
import textwrap
import time
from benchmark_script import deterministic_oracle_answer
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
import requests
from src.agents.advisor import (
    ADVISOR_SYSTEM_PROMPT,
    extract_clean_text,
    extract_mcp_text,
    get_advisor_llm,
)
from src.graph import build_recon_graph
from src.tools.mcp_manager import load_mcp_tools
from tabulate import tabulate

load_dotenv()

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://127.0.0.1:9090")

MODELS_TO_BENCHMARK = [
    {"name": "Gemini 2.5 Flash", "id": "gemini-2.5-flash"},
    {"name": "Gemini 3.8 Flash", "id": "gemini-3.8-flash"},
    {"name": "Claude Opus 5.5", "id": "claude-opus-5-5"},
    {"name": "Claude Sonnet 5.5", "id": "claude-sonnet-5-5"},
]


def load_questions_file() -> dict:
  q_file = os.path.join(
      os.path.dirname(os.path.abspath(__file__)), "questions.json"
  )
  if not os.path.exists(q_file):
    raise FileNotFoundError(
        f"File questions.json non trovato nel percorso: {q_file}"
    )
  with open(q_file, "r", encoding="utf-8") as f:
    return json.load(f)


async def call_advisor_for_model(
    model_meta: dict,
    question: str,
    mapping: dict,
    metrics: dict,
    tools: list,
    max_steps: int = 4,
):
  model_id = model_meta["id"]
  llm = get_advisor_llm(model_id)

  tools_map = {t.name: t for t in tools}
  llm_with_tools = llm.bind_tools(tools) if tools else llm

  chat_messages = [
      SystemMessage(content=ADVISOR_SYSTEM_PROMPT),
      HumanMessage(
          content=(
              f"Topologia e Pod Attuali: {json.dumps(mapping)}\n"
              f"Metriche Istantanee Correnti: {json.dumps(metrics)}\n\n"
              f"Richiesta operatore: {question}"
          )
      ),
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

  usage = getattr(
      response, "usage_metadata", None
  ) or response.response_metadata.get("usage_metadata", {})
  prompt_tokens += usage.get("input_tokens", 0)
  completion_tokens += usage.get("output_tokens", 0)

  
  step_count = 0
  while response.tool_calls and tools and step_count < max_steps:
    step_count += 1

    if isinstance(response.content, list):
      clean_content = [
          b
          for b in response.content
          if isinstance(b, dict) and b.get("type") != "thinking"
      ]
      response_to_append = AIMessage(
          content=clean_content, tool_calls=response.tool_calls
      )
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
      usage_step = getattr(
          response, "usage_metadata", None
      ) or response.response_metadata.get("usage_metadata", {})
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

  app = build_recon_graph(tools)
  thread_config = {
      "configurable": {"thread_id": "session-benchmark-t0-interactive"}
  }

  initial_state = {
      "target_namespace": "default",
      "discovered_pods": [],
      "app_mapping": {},
      "metrics_summary": {},
      "raw_prometheus_responses": {},
      "final_report": "",
      "user_query": None,
      "advisor_response": None,
      "messages": [],
      "prompt_tokens": 0,
      "completion_tokens": 0,
      "total_tokens": 0,
  }

  print("\n" + "=" * 80)
  print("FASE 1: MONITORAGGIO INIZIALE (DISCOVERY -> EVALUATOR -> PERSISTER)")
  print("=" * 80)
  t0_start = time.perf_counter()

  await app.ainvoke(initial_state, config=thread_config)
  etl_duration = time.perf_counter() - t0_start

  frozen_state = app.get_state(thread_config).values
  app_mapping = frozen_state.get("app_mapping", {})
  metrics_summary = frozen_state.get("metrics_summary", {})

  
  etl_in_tokens = frozen_state.get("prompt_tokens", 0)
  etl_out_tokens = frozen_state.get("completion_tokens", 0)
  etl_total_tokens = frozen_state.get("total_tokens", 0)

  print(
      f"\n[OK] Monitoraggio iniziale completato in {etl_duration:.2f} s | Token"
      f" ETL spesi: {etl_total_tokens} (In: {etl_in_tokens}, Out:"
      f" {etl_out_tokens})"
  )
  print(f"Topologia scoperta: {list(app_mapping.keys())}")
  print("I dati sono stati persistiti su MongoDB ('agent_metrics').\n")

  while True:
    print("=" * 80)
    user_choice = await asyncio.to_thread(
        input,
        "Scegli una domanda da sottomettere (1-10) oppure premi INVIO / altro"
        " tasto per uscire: ",
    )
    user_choice = user_choice.strip()

    if not user_choice.isdigit():
      print("\nInput non numerico o vuoto. Uscita dalla sessione.")
      break

    q_num = int(user_choice)
    if q_num < 1 or q_num > 10:
      print(
          f"\nIl numero {q_num} non è compreso tra 1 e 10. Uscita dalla"
          " sessione."
      )
      break

    q_key = str(q_num)
    q_text = q_map.get(q_key, "")

    print("\n" + "-" * 110)
    print(f"ESECUZIONE DOMANDA [Q{q_num}]: {q_text}")
    print("-" * 110)

    t_script = time.perf_counter()
    oracle_res = deterministic_oracle_answer(
        q_num, app_mapping, metrics_summary
    )
    script_lat = time.perf_counter() - t_script

    print("Invocazione modelli in corso...")
    tasks = [
        call_advisor_for_model(m, q_text, app_mapping, metrics_summary, tools)
        for m in MODELS_TO_BENCHMARK
    ]
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
      total_pipeline_lat = res["latency_sec"] + etl_duration
      total_pipeline_in = res["prompt_tokens"] + etl_in_tokens
      total_pipeline_out = res["completion_tokens"] + etl_out_tokens
      total_pipeline_all = res["total_tokens"] + etl_total_tokens

      rows.append([
          res["system"],
          f"{res['latency_sec']:.2f} s  (tot: {total_pipeline_lat:.2f} s)",
          f"{res['prompt_tokens']}",
          f"{res['completion_tokens']}",
          f"{res['total_tokens']}",
          wrap_text(res["response"]),
      ])

    headers = [
        "Sistema",
        "Latenza Q (Tot con ETL)",
        "In Tok",
        "Out Tok",
        "Tot Tok ",
        "Risposta Completa",
    ]
    print("\n" + tabulate(rows, headers=headers, tablefmt="fancy_grid"))
    print("\n")

  print("\nBenchmark terminato.")


if __name__ == "__main__":
  asyncio.run(run())