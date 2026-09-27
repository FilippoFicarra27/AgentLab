from typing import TypedDict, List, Dict, Any, Annotated, Optional
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class ReconState(TypedDict):
    target_namespace: str
    discovered_pods: List[str]
    app_mapping: Dict[str, List[str]]
    metrics_summary: Dict[str, Any]
    raw_prometheus_responses: Dict[str, Any]
    final_report: str
    messages: Annotated[List[AnyMessage], add_messages]
    user_query: Optional[str]
    advisor_response: Optional[str]  
    total_tokens: Optional[int]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]