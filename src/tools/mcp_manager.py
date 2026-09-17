import os
import sys
from langchain_mcp_adapters.client import MultiServerMCPClient

def get_mcp_config():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    k8s_server_script = os.path.join(base_dir, "src", "servers", "k8s_mcp_server.py")
    
    # Eredita e arricchisce l'ambiente per il server Python
    python_env = dict(os.environ)
    python_env["PYTHONUNBUFFERED"] = "1"
    python_env["PYTHONPATH"] = base_dir

    return {
        #Server MCP Kubernetes nativo
        "kubernetes": {
            "transport": "stdio",
            "command": sys.executable,
            "args": ["-u", k8s_server_script],
            "env": python_env
        },
        #Server MCP Prometheus
        "prometheus": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "prometheus-mcp-server"],
            "env": {
                "PROMETHEUS_BASE_URL": "http://127.0.0.1:9090",
                "PATH": os.environ.get("PATH", "")
            }
        }
    }

async def load_mcp_tools():
    config = get_mcp_config()
    client = MultiServerMCPClient(config)
    
    all_tools = await client.get_tools()
    return client, all_tools