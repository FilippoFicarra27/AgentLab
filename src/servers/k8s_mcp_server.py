import json
from mcp.server.fastmcp import FastMCP
from kubernetes import client, config
from pymongo import MongoClient, ASCENDING, DESCENDING
from datetime import datetime, timezone, timedelta
# Inizializza il server MCP con il nome "kubernetes-mcp-server"
mcp = FastMCP("kubernetes-mcp-server")

def init_k8s():
    try:
        config.load_kube_config()
    except Exception as e:
        pass


@mcp.tool()
def get_app_pod_mapping(namespace: str = "default") -> str:
    """Restituisce la mappa JSON tra ogni Deployment e l'elenco dei suoi Pod attivi."""
    init_k8s()
    apps_v1 = client.AppsV1Api()
    core_v1 = client.CoreV1Api()
    try:
        deployments = apps_v1.list_namespaced_deployment(namespace=namespace)
        pods = core_v1.list_namespaced_pod(namespace=namespace)
        
        mapping = {}
        for dep in deployments.items:
            app_name = dep.metadata.name
            match_labels = dep.spec.selector.match_labels or {}
            
            matched_pods = []
            for pod in pods.items:
                pod_labels = pod.metadata.labels or {}
                if all(pod_labels.get(k) == v for k, v in match_labels.items()):
                    matched_pods.append(pod.metadata.name)
            mapping[app_name] = matched_pods
            
        return json.dumps(mapping)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def save_metrics_to_mongodb(app_name: str, metrics: dict, pods: list = None, raw_prometheus_responses: dict = None) -> str:
    """
    Salva il documento delle metriche di un'applicazione su MongoDB nella collection 'agent_metrics'.
    - app_name: nome dell'applicazione o deployment
    - metrics: dizionario numerico contenente cpu_cores, memory_bytes, memory_mb, disk_write_bps, network_rx_bps
    - pods: lista opzionale dei nomi dei pod
    - raw_prometheus_responses: dizionario opzionale con i dati grezzi ricevuti da Prometheus
    """
    try:
        client = MongoClient("mongodb://localhost:27017/")
        db = client["k8s_observability"]
        collection = db["agent_metrics"]
        collection.create_index([("app_name", ASCENDING), ("timestamp", DESCENDING)])

        # Conversione di sicurezza se arrivano serializzati in stringa
        metrics_dict = json.loads(metrics) if isinstance(metrics, str) else (metrics or {})
        raw_dict = json.loads(raw_prometheus_responses) if isinstance(raw_prometheus_responses, str) else (raw_prometheus_responses or {})

        pod_list = pods or []
        doc = {
            "app_name": app_name,
            "timestamp": datetime.now().astimezone(),
            "pods": pod_list,
            "pod_count": len(pod_list),
            "metrics": metrics_dict,
            "raw_prometheus_responses": raw_dict
        }
        res = collection.insert_one(doc)
        return f"Dati salvati con successo per {app_name}, ID: {res.inserted_id}"
    except Exception as e:
        return f"Errore MongoDB: {str(e)}"
@mcp.tool()
def get_historical_metrics(app_name: str, hours: int = 0, days: int = 0) -> str:
    """
    Recupera lo storico delle metriche salvate su MongoDB per una specifica applicazione
    nelle ultime N ore o negli ultimi N giorni per analizzare trend temporali.
    - app_name: nome dell'applicazione (es. 'cache-app', 'worker-app', 'demo-app')
    - hours: intervallo in ore da consultare nel passato (es. 2, 6, 12).
    - days: intervallo in giorni da consultare nel passato (es. 1, 2, 7). Se specificato, ha la precedenza o si somma alle ore.
    """
    try:
        client = MongoClient("mongodb://localhost:27017/")
        db = client["k8s_observability"]
        collection = db["agent_metrics"]
        
        # Se non viene passato nulla, default a 3 ore
        total_hours = int(hours) + (int(days) * 24)
        if total_hours <= 0:
            total_hours = 3

        since_time = datetime.now(timezone.utc) - timedelta(hours=total_hours)
        
        cursor = collection.find(
            {
                "app_name": app_name,
                "timestamp": {"$gte": since_time}
            },
            {"_id": 0, "timestamp": 1, "metrics": 1, "pod_count": 1}
        ).sort("timestamp", ASCENDING)
        
        records = []
        for r in cursor:
            ts = r.get("timestamp")
            records.append({
                "timestamp": ts.isoformat() if isinstance(ts, datetime) else str(ts),
                "metrics": r.get("metrics", {}),
                "pod_count": r.get("pod_count", 0)
            })
            
        if not records:
            return f"Nessun dato storico trovato per '{app_name}' nelle ultime {total_hours} ore ({days} giorni)."
            
        # Se ci sono molti record (ad es. esecuzioni frequenti su più giorni),
        # limitiamo l'output o facciamo campionamento per non sforare la context window
        if len(records) > 50:
            step = len(records) // 30
            records = records[::step]

        return json.dumps(records)
    except Exception as e:
        return f"Errore lettura archivio MongoDB: {str(e)}"









#Ora come ora questi tool non vengono forniti all'agente. Ma li mantengo per estensioni future

#@mcp.tool()
#def get_pods(namespace: str = "default") -> str:
#    """Restituisce l'elenco dei pod in esecuzione in un determinato namespace Kubernetes."""
#    init_k8s()
#    v1 = client.CoreV1Api()
#    try:
#        pods = v1.list_namespaced_pod(namespace=namespace)
#        output = [f"{p.metadata.name}\t{p.status.phase}\t{p.status.pod_ip}" for p in pods.items]
#        return "NAME\tSTATUS\tIP\n" + "\n".join(output) if output else "No pods found."
#    except Exception as e:
#        return f"Errore recupero pod: {str(e)}"

#@mcp.tool()
#def get_deployments(namespace: str = "default") -> str:
#    """Restituisce l'elenco dei deployment presenti in un determinato namespace Kubernetes."""
#    init_k8s()
#    apps_v1 = client.AppsV1Api()
#    try:
#        deps = apps_v1.list_namespaced_deployment(namespace=namespace)
#        output = [f"{d.metadata.name}\t{d.status.ready_replicas}/{d.spec.replicas}" for d in deps.items]
#        return "NAME\tREADY\n" + "\n".join(output) if output else "No deployments found."
#    except Exception as e:
#        return f"Errore recupero deployment: {str(e)}"

#@mcp.tool()
#def get_services(namespace: str = "default") -> str:
#    """Restituisce i service e i relativi ClusterIP in un determinato namespace Kubernetes."""
#    init_k8s()
#    v1 = client.CoreV1Api()
#    try:
#        svcs = v1.list_namespaced_service(namespace=namespace)
#        output = [f"{s.metadata.name}\t{s.spec.type}\t{s.spec.cluster_ip}" for s in svcs.items]
#        return "NAME\tTYPE\tCLUSTER-IP\n" + "\n".join(output) if output else "No services found."
#    except Exception as e:
#        return f"Errore recupero service: {str(e)}"


if __name__ == "__main__":
    # Avvia il server su protocollo standard stdio
    mcp.run(transport="stdio")