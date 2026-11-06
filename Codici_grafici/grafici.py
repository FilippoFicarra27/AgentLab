import glob
import os
import re
import sys
 
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
 
plt.rcParams.update({
    'font.sans-serif': 'DejaVu Sans',
    'font.family': 'sans-serif',
    'figure.dpi': 300,
    'axes.labelsize': 11,
    'axes.titlesize': 12,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 10,
})
 
DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__))
if os.path.isdir(os.path.join(DIR_SCRIPT, "tabelle_excel")):
    CARTELLA_EXCEL = os.path.join(DIR_SCRIPT, "tabelle_excel")
elif os.path.isdir(os.path.join(DIR_SCRIPT, "..", "tabelle_excel")):
    CARTELLA_EXCEL = os.path.abspath(os.path.join(DIR_SCRIPT, "..", "tabelle_excel"))
else:
    CARTELLA_EXCEL = "tabelle_excel"

PATTERN = "confronto_modelli_domanda*.xlsx"         
CARTELLA_OUT = os.path.join(DIR_SCRIPT, "grafici_modelli")  

AGGREGA_VARIANTI = False  
LOG_TOKEN = True           
LOG_LATENZA = False       
 
MODELLI = ["Gemini 2.5 Flash", "Gemini 3.6 Flash", "Claude Sonnet 5.5", "Claude Opus 5.5", "GPT-4o Mini", "GPT-4o"]
VARIANTI = ["base", "a", "b"]
width = 0.25 
 

colors = {
    'L1': '#ff0000',  # Rosso
    'L2': '#00ff00',  # Verde
    'L3': '#0000ff'   # Blu
}
 

def a_numero(v):
    """Converte celle numeriche o testuali ('85,30', '~45.00 s') in float."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    if isinstance(v, (int, float, np.integer, np.floating)):
        return float(v)
    m = re.search(r"[-+]?\d[\d.,]*", str(v))
    if not m:
        return np.nan
    t = m.group(0)
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    return float(t)
 
 
def totale_token(v):
    """'8.114 + 4.844 = 12.958' (anche con '~') -> 12958. Il punto è il separatore delle migliaia."""
    if isinstance(v, (int, float, np.integer, np.floating)) and not pd.isna(v):
        return float(v)
    nums = [int(n.replace(".", "")) for n in re.findall(r"\d[\d.]*", str(v))]
    if len(nums) >= 3:
        return float(nums[-1])
    if len(nums) == 2:
        return float(nums[0] + nums[1])
    return float(nums[0]) if nums else np.nan
 
 
def trova_colonna(colonne, *prefissi):
    for c in colonne:
        if any(str(c).strip().lower().startswith(p) for p in prefissi):
            return c
    raise KeyError("Colonna non trovata: " + " / ".join(prefissi))
 
 
def leggi_file(path):
    try:
        df = pd.read_excel(path, sheet_name="Dati")
    except ValueError:
        df = pd.read_excel(path, sheet_name=0)
    c = df.columns
    c_liv, c_mod, c_var = trova_colonna(c, "livello"), trova_colonna(c, "modello"), trova_colonna(c, "var")
    c_lat, c_tok = trova_colonna(c, "latenza"), trova_colonna(c, "token")
    c_acc = trova_colonna(c, "acc. giudice", "acc giudice")
    df = df[df[c_liv].astype(str).str.match(r"^L\d+$")].copy()
    var = df[c_var].map(lambda v: str(int(v)) if isinstance(v, float) and float(v).is_integer() else str(v).strip())
    return pd.DataFrame({
        "domanda": var.str.extract(r"^(\d+)", expand=False).astype(int),
        "variante": var.str.replace(r"^\d+", "", regex=True).replace("", "base"),
        "livello": df[c_liv].astype(str).str.strip(),
        "modello": df[c_mod].astype(str).str.strip(),
        "latenza": df[c_lat].map(a_numero),
        "tot_tok": df[c_tok].map(totale_token),
        "acc_giudice": df[c_acc].map(a_numero),
    })
 
 
files = glob.glob(os.path.join(CARTELLA_EXCEL, PATTERN))
if not files:
    sys.exit(f"Nessun file trovato in {CARTELLA_EXCEL} con il pattern {PATTERN}")
df = pd.concat([leggi_file(p) for p in files], ignore_index=True)
dup = df.duplicated(["domanda", "variante", "livello", "modello"], keep="first")
if dup.any():
    print(f"Attenzione: {dup.sum()} righe duplicate ignorate")
    df = df[~dup]
print(f"Lette {len(df)} righe da {len(files)} file")
 
modelli = [m for m in MODELLI if m in set(df["modello"])] + [m for m in df["modello"].unique() if m not in MODELLI]
livelli = sorted(df["livello"].unique())
 
celle = []  
pos = 0.0
for q in sorted(df["domanda"].unique()):
    if AGGREGA_VARIANTI:
        celle.append((q, None, f"Q{q}", pos))
        pos += 1.0
    else:
        for v in VARIANTI:
            if ((df["domanda"] == q) & (df["variante"] == v)).any():
                celle.append((q, v, f"Q{q}" + ("" if v == "base" else v), pos))
                pos += 1.0
        pos += 1.0  
 
questions = [c[2] for c in celle]
x = np.array([c[3] for c in celle])
 
 
def costruisci_dati(colonna):
    """Ritorna {modello: {livello: [valore per ogni domanda]}}, come i dizionari dello script originale."""
    dati = {}
    for m in modelli:
        dm = df[df["modello"] == m]
        dati[m] = {}
        for lv in livelli:
            valori = []
            for q, v, _, _ in celle:
                s = dm[(dm["livello"] == lv) & (dm["domanda"] == q)]
                if v is not None:
                    s = s[s["variante"] == v]
                valori.append(s[colonna].mean() if not s.empty else np.nan)
            dati[m][lv] = valori
    return dati
 

latency_data = costruisci_dati("latenza")
token_data = costruisci_dati("tot_tok")
accuracy_data = costruisci_dati("acc_giudice")
 

def genera_istogramma(dati_modello, nome_modello, metrica, y_label, nome_file, usa_log=False, y_max=None):
    plt.figure(figsize=(10, 5) if AGGREGA_VARIANTI else (16, 5))
 
    if not AGGREGA_VARIANTI:
        for i, q in enumerate(sorted({c[0] for c in celle})):
            xs = [c[3] for c in celle if c[0] == q]
            if i % 2 == 0:
                plt.axvspan(min(xs) - 0.5, max(xs) + 0.5, color='#f0f0f0', zorder=0)
 
    def serie(livello):
        v = np.array(dati_modello[livello], dtype=float)
        return np.where(v > 0, v, np.nan) if usa_log else v  
 
    # 3 barre per ciascuna domanda (L1, L2, L3)
    plt.bar(x - width, serie("L1"), width, label='L1: Zero-Context', color=colors['L1'], edgecolor='black', linewidth=0.5, zorder=3)
    plt.bar(x, serie("L2"), width, label='L2: Agentic Recon', color=colors['L2'], edgecolor='black', linewidth=0.5, zorder=3)
    plt.bar(x + width, serie("L3"), width, label='L3: Deterministic Pre-Harnessing', color=colors['L3'], edgecolor='black', linewidth=0.5, zorder=3)
 
    if usa_log:
        plt.yscale('log')
    if y_max is not None:
        plt.ylim(0, y_max)
 
    plt.xlabel('Domanda di Benchmark')
    plt.ylabel(y_label)
    plt.title(f"{metrica} - {nome_modello}")
    if AGGREGA_VARIANTI:
        plt.xticks(x, questions)
    else:
        plt.xticks(x, questions, rotation=90, fontsize=8)
    plt.xlim(x.min() - 0.7, x.max() + 0.7)
    plt.grid(axis='y', linestyle='--', alpha=0.6, zorder=0)
    plt.legend(frameon=True, facecolor='white', framealpha=0.9)
    plt.tight_layout()
 
    plt.savefig(nome_file, dpi=300)
    plt.close()
    print(f"Salvato: {nome_file}")
 
 
os.makedirs(CARTELLA_OUT, exist_ok=True)
 
 
def slug(nome):
    return nome.lower().replace(" ", "_").replace(".", "_")
 

for modello, dati in latency_data.items():
    genera_istogramma(
        dati_modello=dati,
        nome_modello=modello,
        metrica="Latenza di Query",
        y_label="Latenza (secondi)" + (" (Scala Logaritmica)" if LOG_LATENZA else ""),
        nome_file=os.path.join(CARTELLA_OUT, f"latenza_{slug(modello)}.png"),
        usa_log=LOG_LATENZA
    )
 

for modello, dati in token_data.items():
    genera_istogramma(
        dati_modello=dati,
        nome_modello=modello,
        metrica="Token Totali Consumati",
        y_label="Token Totali" + (" (Scala Logaritmica)" if LOG_TOKEN else ""),
        nome_file=os.path.join(CARTELLA_OUT, f"token_{slug(modello)}.png"),
        usa_log=LOG_TOKEN
    )
 

for modello, dati in accuracy_data.items():
    genera_istogramma(
        dati_modello=dati,
        nome_modello=modello,
        metrica="Accuratezza (Giudice)",
        y_label="Accuratezza del giudice",
        nome_file=os.path.join(CARTELLA_OUT, f"accuratezza_{slug(modello)}.png"),
        usa_log=False,
        y_max=1.08
    )
 
print(f"\nTutti i {3 * len(modelli)} istogrammi sono stati creati con successo!")