import json
from mcp.server.fastmcp import FastMCP
from kubernetes import client, config

# Inizializza il server MCP con il nome "kubernetes-mcp-server"
mcp = FastMCP("kubernetes-mcp-server")

def init_k8s():
    try:
        config.load_kube_config()
    except Exception as e:
        pass

@mcp.tool()
def get_pods(namespace: str = "default") -> str:
    """Restituisce l'elenco dei pod in esecuzione in un determinato namespace Kubernetes."""
    init_k8s()
    v1 = client.CoreV1Api()
    try:
        pods = v1.list_namespaced_pod(namespace=namespace)
        output = [f"{p.metadata.name}\t{p.status.phase}\t{p.status.pod_ip}" for p in pods.items]
        return "NAME\tSTATUS\tIP\n" + "\n".join(output) if output else "No pods found."
    except Exception as e:
        return f"Errore recupero pod: {str(e)}"

@mcp.tool()
def get_deployments(namespace: str = "default") -> str:
    """Restituisce l'elenco dei deployment presenti in un determinato namespace Kubernetes."""
    init_k8s()
    apps_v1 = client.AppsV1Api()
    try:
        deps = apps_v1.list_namespaced_deployment(namespace=namespace)
        output = [f"{d.metadata.name}\t{d.status.ready_replicas}/{d.spec.replicas}" for d in deps.items]
        return "NAME\tREADY\n" + "\n".join(output) if output else "No deployments found."
    except Exception as e:
        return f"Errore recupero deployment: {str(e)}"

@mcp.tool()
def get_services(namespace: str = "default") -> str:
    """Restituisce i service e i relativi ClusterIP in un determinato namespace Kubernetes."""
    init_k8s()
    v1 = client.CoreV1Api()
    try:
        svcs = v1.list_namespaced_service(namespace=namespace)
        output = [f"{s.metadata.name}\t{s.spec.type}\t{s.spec.cluster_ip}" for s in svcs.items]
        return "NAME\tTYPE\tCLUSTER-IP\n" + "\n".join(output) if output else "No services found."
    except Exception as e:
        return f"Errore recupero service: {str(e)}"

if __name__ == "__main__":
    # Avvia il server su protocollo standard stdio
    mcp.run(transport="stdio")