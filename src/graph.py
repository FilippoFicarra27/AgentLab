import os
import sys
import asyncio
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from src.state import ReconState
from src.agents.discovery import discovery_node
from src.agents.evaluator import evaluator_node
from src.agents.persister import persister_node
from src.agents.advisor import sre_advisor_node

def build_recon_graph(tools: list): #i tool vengono recuperati dal main.py
    workflow = StateGraph(ReconState) #creazione del workflow. Tutti i nodi condividono lo stato comune 
    
    # Wrapper async espliciti per consentire l'awaiting corretto in LangGraph
    async def run_discovery(state: ReconState): #funge da adapter
        return await discovery_node(state, tools)

    async def run_evaluator(state: ReconState): #funge da adapter
        return await evaluator_node(state, tools)

    async def run_persister(state: ReconState):
        return await persister_node(state, tools)

    async def run_advisor(state: ReconState):
        return await sre_advisor_node(state)


    workflow.add_node("discovery", run_discovery)
    workflow.add_node("evaluator", run_evaluator)
    workflow.add_node("persister", run_persister)
    workflow.add_node("advisor", run_advisor)


    workflow.set_entry_point("discovery")
    workflow.add_edge("discovery", "evaluator")
    workflow.add_edge("evaluator", "persister")
    workflow.add_edge("persister", "advisor")
    workflow.add_edge("advisor", END)
    
    is_platform = (
        os.getenv("LANGGRAPH_API") is not None 
        or os.getenv("LANGGRAPH_PORT") is not None 
        or any("langgraph" in arg for arg in sys.argv)
    )
    
    # Il grafo si congela esattamente PRIMA di entrare nel nodo advisor
    if is_platform:
        return workflow.compile(interrupt_before=["advisor"])
    else:
        checkpointer = MemorySaver()
        return workflow.compile(checkpointer=checkpointer, interrupt_before=["advisor"])