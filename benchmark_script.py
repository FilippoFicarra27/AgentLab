import time
from datetime import datetime, timedelta, timezone
import requests
from kubernetes import client, config
from pymongo import MongoClient, ASCENDING, DESCENDING
from tabulate import tabulate


PROMETHEUS_URL = "http://127.0.0.1:9090/api/v1/query"
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "k8s_observability"
COLLECTION_NAME = "agent_metrics"
NAMESPACE = "default"

def init_mongo():
    """Inizializza la connessione a MongoDB e crea gli indici necessari."""
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
   
    collection.create_index([("app_name", ASCENDING), ("timestamp", DESCENDING)])
    print("MongoDB inizializzato correttamente!")
    return collection

def get_k8s_app_pod_mapping():
    """1. Legge le applicazioni (Deployments) e le mappa con i rispettivi Pod."""
    try:
        config.load_kube_config()
    except Exception:
        config.load_incluster_config()
        
    apps_v1 = client.AppsV1Api()
    core_v1 = client.CoreV1Api()

    deployments = apps_v1.list_namespaced_deployment(namespace=NAMESPACE)
    pods = core_v1.list_namespaced_pod(namespace=NAMESPACE)

    
    app_mapping = {}
    for dep in deployments.items:
        app_name = dep.metadata.name
        match_labels = dep.spec.selector.match_labels or {}
        
        matched_pods = []
        for pod in pods.items:
            pod_labels = pod.metadata.labels or {}
            
            if all(pod_labels.get(k) == v for k, v in match_labels.items()):
                matched_pods.append(pod.metadata.name)
        
        app_mapping[app_name] = matched_pods

    print("App Scoperte: ")
    print(app_mapping)
    return app_mapping

def query_prometheus(query: str):
    """Esegue una query PromQL su Prometheus e restituisce il JSON grezzo."""
    try:
        resp = requests.get(PROMETHEUS_URL, params={"query": query}, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[WARN] Errore nella query '{query}': {e}")
        return {"status": "error", "data": {"result": []}}

def parse_metric_by_pod(prom_json):
    """Estrae un dizionario {pod_name: float(valore)} dal risultato Prometheus."""
    data_map = {}
    if prom_json.get("status") == "success":
        results = prom_json.get("data", {}).get("result", [])
        for item in results:
            pod = item.get("metric", {}).get("pod")
            value = item.get("value", [None, "0"])[1]
            if pod:
                try:
                    data_map[pod] = float(value)
                except ValueError:
                    data_map[pod] = 0.0

    print("metriche scoperte per il pod: ")
    print(data_map)
    print("\n")
    return data_map

def query_prometheus_direct(query: str):
    """Query Prometheus di fallback per lo script deterministico."""
    data = query_prometheus(query)
    if data.get("status") == "success":
        return data.get("data", {}).get("result", [])
    return []

def query_mongo_historical(app_name: str, hours: int = 2):
    """Interroga lo storico reale su MongoDB per il calcolo del delta percentuale (Q7)."""
    try:
        client = MongoClient("mongodb://localhost:27017/")
        db = client["k8s_observability"]
        collection = db["agent_metrics"]
        since_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        cursor = collection.find(
            {"app_name": app_name, "timestamp": {"$gte": since_time}},
            {"_id": 0, "timestamp": 1, "metrics": 1}
        ).sort("timestamp", ASCENDING)
        
        return list(cursor)
    except Exception:
        return []

def deterministic_oracle_answer(q_id: int, mapping: dict, metrics: dict) -> str:
    """Calcola la risposta deterministica (Ground Truth) in modo completamente dinamico."""
    if not mapping or not metrics:
        return "Dati dello snapshot non disponibili"

    # Q1
    if q_id == 1:
        top = max(metrics.items(), key=lambda x: x[1].get("cpu_cores", 0.0))
        return f"{top[0]} ({top[1].get('cpu_cores', 0.0):.4f} cores)"

    # Q2
    elif q_id == 2:
        top_replicas_app = max(mapping.items(), key=lambda x: len(x[1]))[0]
        val = metrics.get(top_replicas_app, {}).get("memory_mb", 0.0)
        return f"{top_replicas_app}: {val:.2f} MB"

    # Q3
    elif q_id == 3:
        writers = {k: v.get("disk_write_bps", 0.0) for k, v in metrics.items() if v.get("disk_write_bps", 0.0) > 0}
        if writers:
            top = max(writers.items(), key=lambda x: x[1])
            return f"{top[0]} ({top[1]:.2f} B/s)"
        return "Nessuna applicazione presenta scritture attive su disco"

    # Q4
    elif q_id == 4:
        top_app, pods = max(mapping.items(), key=lambda x: len(x[1]))
        return f"App: {top_app} | Repliche: {len(pods)} | Pods: {pods}"

    # Q5
    elif q_id == 5:
        threshold = 10240.0
        anomalies = {k: v.get("network_rx_bps", 0.0) for k, v in metrics.items() if v.get("network_rx_bps", 0.0) > threshold}
        if anomalies:
            formatted = ", ".join([f"{k} ({v/1024.0:.2f} KB/s)" for k, v in anomalies.items()])
            return f"Applicazioni sopra soglia: {formatted}"
        return "Nessuna applicazione supera 10 KB/s in ricezione"

    # Q6
    elif q_id == 6:
        scores = {}
        for app, m in metrics.items():
            cpu = m.get("cpu_cores", 0.0)
            mem = m.get("memory_mb", 0.0)
            disk = m.get("disk_write_bps", 0.0)
            score = (0.50 * cpu) + (0.25 * (mem / 128.0)) + (0.25 * (disk / 1048576.0))
            scores[app] = round(score, 4)
        top = max(scores.items(), key=lambda x: x[1])
        return f"Punteggio più alto: {top[0]} (Score: {top[1]}) | Tutti: {scores}"

    # Q7
    elif q_id == 7:
        top_mem_app = max(metrics.items(), key=lambda x: x[1].get("memory_mb", 0.0))[0]
        current_mem = metrics.get(top_mem_app, {}).get("memory_mb", 0.0)
        history = query_mongo_historical(top_mem_app, hours=2)
        
        if len(history) >= 2:
            old_mem = history[0].get("metrics", {}).get("memory_mb", 0.0)
            if old_mem > 0:
                delta_pct = ((current_mem - old_mem) / old_mem) * 100.0
                return f"App: {top_mem_app} | Delta: {delta_pct:+.2f}% (da {old_mem:.2f} a {current_mem:.2f} MB)"
        return f"App: {top_mem_app} (Memoria attuale: {current_mem:.2f} MB) | Dati storici insufficienti per calcolo delta"

    # Q8
    elif q_id == 8:
        top_cpu_app = max(metrics.items(), key=lambda x: x[1].get("cpu_cores", 0.0))[0]
        used_cpu = metrics.get(top_cpu_app, {}).get("cpu_cores", 0.0)
        limit_cpu = 0.600
        sat_pct = (used_cpu / limit_cpu) * 100.0
        risk = "ELEVATO (throttling probabile)" if sat_pct > 80.0 else "BASSO"
        return f"App: {top_cpu_app} | Uso: {used_cpu:.4f} cores | Saturazione: {sat_pct:.2f}% | Rischio: {risk}"

    # Q9
    elif q_id == 9:
        res = query_prometheus_direct('sum(increase(kube_pod_container_status_restarts_total{namespace="default"}[1h]))')
        restarts = float(res[0]["value"][1]) if res else 0.0
        return f"{int(restarts)} riavvii imprevisti rilevati nell'ultima ora"

    # Q10
    elif q_id == 10:
        sorted_apps = sorted(metrics.items(), key=lambda x: x[1].get("cpu_cores", 0.0))
        safest = sorted_apps[0][0]
        isolate = sorted_apps[-1][0]
        return f"Co-locare preferibilmente con '{safest}' (minor CPU: {sorted_apps[0][1]['cpu_cores']:.4f} cores) ed ISOLARE da '{isolate}' (maggior CPU: {sorted_apps[-1][1]['cpu_cores']:.4f} cores)"

    return "Domanda non supportata dallo script"



def main():
    print("=" * 60)
    print("AVVIO BENCHMARK DETERMINISTICO (Ground Truth)")
    print("=" * 60)
    
    t_start = time.perf_counter()
    sample_time = datetime.now(timezone.utc)

    print("[1/4] Lettura da Kubernetes e mapping App -> Pods...")
    app_mapping = get_k8s_app_pod_mapping()
    
    print("[2/4] Esecuzione query PromQL hardware...")
    
    cpu_query = f'sum(rate(container_cpu_usage_seconds_total{{namespace="{NAMESPACE}", container!=""}}[2m])) by (pod)'
    
    mem_query = f'sum(container_memory_working_set_bytes{{namespace="{NAMESPACE}", container!=""}}) by (pod)'

    disk_query = f'sum(rate(container_fs_writes_bytes_total{{namespace="{NAMESPACE}", container!=""}}[2m])) by (pod)'
    
    net_query = f'sum(rate(container_network_receive_bytes_total{{namespace="{NAMESPACE}"}}[2m])) by (pod)'

    raw_cpu = query_prometheus(cpu_query)
    raw_mem = query_prometheus(mem_query)
    raw_disk = query_prometheus(disk_query)
    raw_net = query_prometheus(net_query)

    pod_cpu = parse_metric_by_pod(raw_cpu)
    pod_mem = parse_metric_by_pod(raw_mem)
    pod_disk = parse_metric_by_pod(raw_disk)
    pod_net = parse_metric_by_pod(raw_net)

    mongo_collection = init_mongo()
    app_stats = []

    print("[3/4] Aggregazione metriche e salvataggio su MongoDB...")
    for app_name, pod_list in app_mapping.items():
        total_cpu = sum(pod_cpu.get(p, 0.0) for p in pod_list)
        total_mem_bytes = sum(pod_mem.get(p, 0.0) for p in pod_list)
        total_disk_bps = sum(pod_disk.get(p, 0.0) for p in pod_list)
        total_net_bps = sum(pod_net.get(p, 0.0) for p in pod_list)

        doc = {
            "app_name": app_name,
            "timestamp": sample_time,
            "pods": pod_list,
            "pod_count": len(pod_list),
            "metrics": {
                "cpu_cores": total_cpu,
                "memory_bytes": total_mem_bytes,
                "memory_mb": round(total_mem_bytes / (1024 * 1024), 2),
                "disk_write_bps": total_disk_bps,
                "network_rx_bps": total_net_bps
            },
            
            "raw_prometheus_responses": {
                "cpu": raw_cpu,
                "mem": raw_mem,
                "disk": raw_disk,
                "net": raw_net
            }
        }
        
        mongo_collection.insert_one(doc)

        app_stats.append({
            "app": app_name,
            "pods": len(pod_list),
            "cpu_cores": total_cpu,
            "memory_mb": total_mem_bytes / (1024 * 1024),
            "disk_write_bps": total_disk_bps,      
            "network_rx_bps": total_net_bps,        
            "disk_bps": total_disk_bps,             
            "net_bps": total_net_bps                
        })

    top_cpu = max(app_stats, key=lambda x: x["cpu_cores"]) if app_stats else None
    top_mem = max(app_stats, key=lambda x: x["memory_mb"]) if app_stats else None
    top_disk = max(app_stats, key=lambda x: x["disk_bps"]) if app_stats else None
    top_net = max(app_stats, key=lambda x: x["net_bps"]) if app_stats else None

    t_end = time.perf_counter()
    elapsed_time = t_end - t_start

    print("\n" + "=" * 60)
    print("REPORT PRESTAZIONI DELLE APPLICAZIONI")
    print("=" * 60)
    
    headers = ["Applicazione", "Pods", "CPU (cores)", "RAM (MB)", "Disk Write (B/s)", "Net RX (B/s)"]
    table_rows = [
        [
            s["app"],
            s["pods"],
            f"{s['cpu_cores']:.4f}",
            f"{s['memory_mb']:.2f}",
            f"{s['disk_bps']:.2f}",
            f"{s['net_bps']:.2f}"
        ]
        for s in app_stats
    ]
    print(tabulate(table_rows, headers=headers, tablefmt="fancy_grid"))

    print("\nCLASSIFICA CONSUMI (Top Consumers):")
    if top_cpu:
        print(f" - Maggior consumo di CPU:      {top_cpu['app']} ({top_cpu['cpu_cores']:.4f} cores)")
        print(f" - Maggior consumo di RAM:      {top_mem['app']} ({top_mem['memory_mb']:.2f} MB)")
        print(f" - Maggior scrittura su DISCO: {top_disk['app']} ({top_disk['disk_bps']:.2f} B/s)")
        print(f" - Maggior traffico di RETE:    {top_net['app']} ({top_net['net_bps']:.2f} B/s)")

    print("\nMETRICHE PRESTAZIONALI DELLO SCRIPT:")
    print(f" Tempo totale impiegato: {elapsed_time:.4f} secondi")
    print(f" Costo API / Token:       0 token (0.00$)")
    print(f" Dati salvati in MongoDB: {DB_NAME}.{COLLECTION_NAME}")
    print("=" * 60)

    
    metrics_summary = {s["app"]: s for s in app_stats}
    return app_mapping, metrics_summary

if __name__ == "__main__":
    main()