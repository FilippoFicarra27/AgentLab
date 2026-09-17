from typing import TypedDict, List, Dict, Any, Annotated
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class ReconState(TypedDict):
    # Namespace target su Kubernetes
    target_namespace: str
    
    # Workload scoperti tramite Kubernetes MCP
    #contiene l'elenco dei pod scoperti dal nodo Discorvery quando 
    # si fa la kubectl get pods
    discovered_pods: List[str]
    
    # Risultati delle query raccolte da Prometheus MCP
    #Viene popolato dal nodo Evaluator dopo aver effettuato le query PROMQL
    metrics_summary: Dict[str, Any]
    
    # Report diagnostico finale generato dall'agente al termine della 
    # correlazione tra dati Kubernetes e monitoraggio su Prometheus.
    final_report: str
    
    # Cronologia messaggi del workflow
    messages: Annotated[List[AnyMessage], add_messages]