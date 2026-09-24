### INSTALLAZIONE WSL ###
1. Eseguire come amministratore una powerShell, ed inserire il comando di installazione standard:

```powershell
wsl --install
```
Riavviare il computer quando richiesto da Windows.

2. Dopo il riavvio, il terminale di Ubuntu si aprirà automaticamente (in alternativa, si può cercare nel menu Start digitando Ubuntu): Attendere il completamento dell'installazione.

3. Collegare Docker Desktop a WSL. Aprire Docker Desktop su Windows. Spostandosi su Settings -> Resources -> WSL integration, bisogna Assicurarsi che sia spuntata l'opzione "Enable integration with my default WSL distro".Sotto "Enable integration with additional distros", attivare la levetta accanto a Ubuntu. Cliccare su Apply & Restart.

### CONFIGURAZIONE PROGETTO ###
1. Installazione degli strumenti di sistema su Ubuntu
Aprire il terminale di Ubuntu ed eseguire:

```powershell
# Aggiorna i repository di sistema
sudo apt update && sudo apt install -y curl nodejs npm python3-pip python3-venv git

# Installazione kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

# Installazione kind
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.22.0/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/

# Installazione Helm (gestore di pacchetti per Kubernetes)
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 |

```

2. Creazione del Cluster Kubernetes e configurazione permessi

```powershell
# Creazione del cluster Kind (in questo esempio è denominato thesis-cluster)
kind create cluster --name thesis-cluster

# Assicurare i permessi di lettura sul file di configurazione
chmod 644 ~/.kube/config

# Verifica che il cluster sia attivo (il custer dovrebbe apparire in stato Ready).
kubectl get nodes
```

3. Installazione dello stack di monitoraggio (Prometheus)

```powershell
# Aggiunge il repository Prometheus
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Crea il namespace dedicato
kubectl create namespace monitoring

# Installa lo stack kube-prometheus (Prometheus + Grafana + Node Exporter)
helm install prometheus prometheus-community/kube-prometheus-stack -n monitoring

# Attendere che tutti i pod del monitoraggio siano in stato Running (può richiedere 1-2 minuti)
kubectl get pods -n monitoring
```


4. Deploy dell'applicazione target (demo-app)
Creare e applicare l'applicazione di esempio che l'agente dovrà monitorare:

```powershell
# Creare le applicazioni con il comando:
kubectl apply -f ~/AgentLab/k8s/workloads.yaml

# Verificare i due pod siano attivi
kubectl get pods
```


5. Configurazione del progetto Python e Virtualenv
Spostarsi nella cartella del progetto:

```powershell
cd ~/AgentLab

# Se non esiste, creare l'ambiente virtuale
python3 -m venv .venv

# Attivare l'ambiente virtuale
source .venv/bin/activate

# Installare le librerie richieste
pip install requirements.txt
```


6. Configurazione delle variabili d'ambiente (.env)
Creare il file .env dentro ~/AgentLab:

```powershell
nano .env
```
Incollare le configurazioni (sostituendo la propria chiave Google Gemini):

GOOGLE_API_KEY=inserire_la_chiave_gemini
PROMETHEUS_ENDPOINT=http://127.0.0.1:9090
Salvare premendo Ctrl + O, poi Invio, e chiudere con Ctrl + X.


7. Esecuzione del sistema (Uso quotidiano)

Prima dell'esecuzione, avviare un'istanza MongoDb in Docker:

```powershell
docker run -d --name thesis-mongo -p 27017:27017 mongo:latest
```

Ad ogni sessione di lavoro servono due terminali:

Terminale 1: Tunnel verso Prometheus (da lasciare aperto)

```powershell
kubectl port-forward --address 0.0.0.0 svc/prometheus-kube-prometheus-prometheus -n monitoring 9090:9090
```

Terminale 2: Avvio dell'Agente
```powershell
cd ~/AgentLab
source .venv/bin/activate
python3 main.py
```
Nel caso in cui non si voglia attivare l'agente eseguendo il main.py, ma direttamente da LangSmit:
    1. Inserire nel file .env le seguenti informazioni:
    ```powershell
    LANGCHAIN_TRACING_V2=true
    LANGCHAIN_ENDPOINT="https://api.smith.langchain.com"
    LANGCHAIN_API_KEY=La_propria_API_KEY
    LANGCHAIN_PROJECT="AgentLab"
    ```
    2.Digitare su terminale wsl:
    ```powershell
    cd ~/AgentLab
    source .venv/bin/activate
    langgraph dev
    ```