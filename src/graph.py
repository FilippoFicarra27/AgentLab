#importa le classi fondamentali per la modellazione del grafo
from langgraph.graph import StateGraph, END

#Importa lo stato condiviso tra i nodi
from src.state import ReconState

#Importa la funzione asincrona definita nel nodo Discovery, per l'ispezione
#delle risorse su Kubernetes
from src.agents.discovery import discovery_node

#Importa la funzione asincrona definita sul nodo Evaluator, per l'interrogazione
#su Prometheus e il report finale
from src.agents.evaluator import evaluator_node

import os
import sys
import asyncio

def build_recon_graph(tools: list): #i tool vengono recuperati dal main.py
    workflow = StateGraph(ReconState) #creazione del workflow. Tutti i nodi condividono lo stato comune 
    
    # Wrapper async espliciti per consentire l'awaiting corretto in LangGraph
    async def run_discovery(state: ReconState): #funge da adapter
        return await discovery_node(state, tools)

    async def run_evaluator(state: ReconState): #funge da adapter
        return await evaluator_node(state, tools)

    workflow.add_node("discovery", run_discovery)
    workflow.add_node("evaluator", run_evaluator)
    
    workflow.set_entry_point("discovery")
    workflow.add_edge("discovery", "evaluator")
    workflow.add_edge("evaluator", END)
    
    return workflow.compile()

is_platform = (
    os.getenv("LANGGRAPH_API") is not None 
    or os.getenv("LANGGRAPH_PORT") is not None 
    or any("langgraph" in arg for arg in sys.argv)
)

if is_platform:
    print("Compilazione per LangGraph Studio / Dev Server.")
    from src.tools.mcp_manager import load_mcp_tools
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    _, _studio_tools = loop.run_until_complete(load_mcp_tools())
    
    
    compiled_graph = build_recon_graph(_studio_tools)
else:
    
    compiled_graph = None