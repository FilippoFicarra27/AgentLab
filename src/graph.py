import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv()

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from src.state import ReconState
from src.agents.discovery import discovery_node
from src.agents.evaluator import evaluator_node
from src.agents.persister import persister_node
from src.agents.advisor import sre_advisor_node

def init_state_node(state: ReconState) -> dict:
    return {
        "discovered_pods": [],
        "app_mapping": {},
        "metrics_summary": {},
        "raw_prometheus_responses": {},
        "user_query": None,
        "advisor_response": None,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0
    }



def build_recon_graph(tools: list, is_platform: bool = False):
    workflow = StateGraph(ReconState)
    
    async def run_discovery(state: ReconState):
        return await discovery_node(state, tools)

    async def run_evaluator(state: ReconState):
        return await evaluator_node(state, tools)

    async def run_persister(state: ReconState):
        return await persister_node(state, tools)

    async def run_advisor(state: ReconState):
        return await sre_advisor_node(state, tools)

    workflow.add_node("init", init_state_node)
    workflow.add_node("discovery", run_discovery)
    workflow.add_node("evaluator", run_evaluator)
    workflow.add_node("persister", run_persister)
    workflow.add_node("advisor", run_advisor)
   

    workflow.set_entry_point("init")
    workflow.add_edge("init", "discovery")
    workflow.add_edge("discovery", "evaluator")
    workflow.add_edge("evaluator", "persister")
    workflow.add_edge("persister", "advisor")
    workflow.add_edge("advisor", END)
    
    if is_platform:
        return workflow.compile()
    else:
        checkpointer = MemorySaver()
        return workflow.compile(checkpointer=checkpointer)

is_platform = (
    os.getenv("LANGGRAPH_API") is not None 
    or os.getenv("LANGGRAPH_PORT") is not None 
    or any("langgraph" in arg for arg in sys.argv)
)

if is_platform:
    from src.tools.mcp_manager import load_mcp_tools
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    _, _platform_tools = loop.run_until_complete(load_mcp_tools())
    
    compiled_graph = build_recon_graph(_platform_tools, is_platform=True)
else:
    compiled_graph = None