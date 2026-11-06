import argparse
import glob
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

MODELLI = ["Gemini 2.5 Flash", "Gemini 3.6 Flash", "Claude Opus 5.5", "Claude Sonnet 5.5", "GPT-4o", "GPT-4o Mini"]

MAPPA_METRICHE = {
    "accuratezza": ("Acc. Giudice", "YlGn", ".2f", "Accuratezza del Giudice [0.0 - 1.0]"),
    "latenza": ("Latenza (s)", "OrRd", ".1f", "Latenza Media (s)"),
    "token": ("Tot_Tok", "PuBu", ".0f", "Token Totali Consumati")
}


def parse_tok(v):
    if isinstance(v, (int, float)) and not pd.isna(v):
        return float(v)
    nums = [int(n.replace(".", "")) for n in re.findall(r"\d[\d.]*", str(v))]
    return float(nums[-1]) if len(nums) >= 3 else (float(nums[0] + nums[1]) if len(nums) == 2 else float(nums[0]) if nums else np.nan)


def carica_cubo():
    dir_script = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
    cartella_target = os.path.abspath(os.path.join(dir_script, "..", "tabelle_excel"))
    
    cartelle_tentativi = [
        cartella_target,
        os.path.abspath(os.path.join(os.getcwd(), "tabelle_excel")),
        os.path.abspath(os.path.join(os.getcwd(), "..", "tabelle_excel")),
        os.path.abspath(os.path.join(dir_script, "tabelle_excel")),
        dir_script,
        os.getcwd()
    ]
    
    files = []
    cartella_usata = ""
    for c in cartelle_tentativi:
        if os.path.exists(c):
            trovati = sorted(
                glob.glob(os.path.join(c, "confronto_modelli_domanda*.xlsx")),
                key=lambda x: int(re.search(r"(\d+)\D*$", os.path.splitext(x)[0]).group(1)) if re.search(r"(\d+)\D*$", os.path.splitext(x)[0]) else 0
            )
            if trovati:
                files = trovati
                cartella_usata = c
                break

    if not files:
        sys.exit(f"ERRORE: Nessun file Excel trovato nelle cartelle testate:\n" + "\n".join(f" - {p}" for p in cartelle_tentativi))

    all_dfs = []
    for f in files:
        try:
            df = pd.read_excel(f, sheet_name="Dati").dropna(subset=["Modello", "Latenza (s)", "Acc. Giudice"])
        except ValueError:
            df = pd.read_excel(f, sheet_name=0).dropna(subset=["Modello", "Latenza (s)", "Acc. Giudice"])
            
        var = df["Var."].astype(str).str.strip()
        df["Domanda"] = var.str.extract(r"^(\d+)", expand=False).astype(int)
        df["Variante"] = var.str.replace(r"^\d+", "", regex=True).replace("", "base")
        df["Task"] = df.apply(lambda r: f"Q{r['Domanda']}" if r["Variante"] == "base" else f"Q{r['Domanda']}{r['Variante']}", axis=1)
        df["Tot_Tok"] = df["Token (In + Out = Tot)"].map(parse_tok)
        all_dfs.append(df[["Domanda", "Variante", "Task", "Livello", "Modello", "Latenza (s)", "Tot_Tok", "Acc. Giudice"]])

    df_raw = pd.concat(all_dfs, ignore_index=True)
    dup = df_raw.duplicated(["Domanda", "Variante", "Livello", "Modello"], keep="first")
    if dup.any():
        df_raw = df_raw[~dup]
        
    print(f"Lette {len(df_raw)} celle da {len(files)} file Excel in: {cartella_usata}")
    return df_raw


def ottieni_limiti_globali(df, metrica_key):
    """
    Calcola il minimo e massimo assoluti sull'intero dataset per una data metrica.
    In questo modo la scala colore sarà rigidamente globale e indipendente dal livello o dalla domanda.
    """
    col_metrica, _, _, _ = MAPPA_METRICHE[metrica_key]
    if metrica_key == "accuratezza":
        return 0.0, 1.0
    valori_validi = df[col_metrica].dropna()
    return float(valori_validi.min()), float(valori_validi.max())

def slice_fissa_livello(df, livello="L2", metrica_key="accuratezza", includi_sottodomande=True, cartella_out="Grafici_olap"):
    os.makedirs(cartella_out, exist_ok=True)
    col_metrica, cmap, fmt, label_metrica = MAPPA_METRICHE[metrica_key]
    vmin_glob, vmax_glob = ottieni_limiti_globali(df, metrica_key)
    
    d = df[df["Livello"] == livello]
    colonna_x = "Task" if includi_sottodomande else "Domanda"
    
    pivot = d.pivot_table(index="Modello", columns=colonna_x, values=col_metrica, aggfunc="mean")
    
    if includi_sottodomande:
        ordine_task = [f"Q{q}{v if v!='base' else ''}" for q in range(1, 11) for v in ["base", "a", "b"]]
        colonne_presenti = [c for c in ordine_task if c in pivot.columns]
        pivot = pivot[colonne_presenti]
    else:
        pivot = pivot[sorted(pivot.columns)]

    print(f"\n=======================================================")
    print(f" SLICE OLAP: LIVELLO = {livello} | METRICA = {col_metrica}")
    print(f" Scala colore globale: min={vmin_glob:.2f}, max={vmax_glob:.2f}")
    print(f" Sottodomande incluse: {'Sì (30 varianti)' if includi_sottodomande else 'No (10 macro-domande)'}")
    print(f"=======================================================")
    print(pivot.round(2 if metrica_key != "token" else 0))

    larghezza = 20 if includi_sottodomande else 11
    fig, ax = plt.subplots(figsize=(larghezza, 5.5))
    
    # vmin e vmax globali assegnano il colore solo in base alla grandezza del valore
    sns.heatmap(pivot, annot=True, fmt=fmt, cmap=cmap, cbar_kws={'label': label_metrica}, 
                linewidths=0.8, ax=ax, vmin=vmin_glob, vmax=vmax_glob, 
                annot_kws={"size": 9 if includi_sottodomande else 11})
    
    titolo_extra = "Tutte le 30 Sottodomande (Q1, Q1a, Q1b, ...)" if includi_sottodomande else "10 Domande di Benchmark (Media)"
    ax.set_title(f"Slice OLAP: {label_metrica} a Livello Fisso [{livello}]\n({titolo_extra})", fontsize=12, fontweight="bold", pad=12)
    ax.set_ylabel("Modello LLM", fontweight="bold")
    ax.set_xlabel("Domande e Sottovarianti" if includi_sottodomande else "Domanda (Q1 - Q10)", fontweight="bold")
    if includi_sottodomande:
        plt.xticks(rotation=45, ha='right')

    plt.tight_layout()
    tag_sub = "dettaglio30" if includi_sottodomande else "macro10"
    file_png = os.path.join(cartella_out, f"olap_livello_{livello}_{metrica_key}_{tag_sub}.png")
    plt.savefig(file_png, dpi=300)
    plt.close(fig)
    print(f"-> Grafico salvato: {file_png}")


def slice_fissa_modello(df, modello="Claude Sonnet 5.5", metrica_key="accuratezza", includi_sottodomande=False, cartella_out="Grafici_olap"):
    os.makedirs(cartella_out, exist_ok=True)
    col_metrica, cmap, fmt, label_metrica = MAPPA_METRICHE[metrica_key]
    vmin_glob, vmax_glob = ottieni_limiti_globali(df, metrica_key)
    
    d = df[df["Modello"] == modello]
    colonna_x = "Task" if includi_sottodomande else "Domanda"
    
    pivot = d.pivot_table(index="Livello", columns=colonna_x, values=col_metrica, aggfunc="mean").reindex(["L1", "L2", "L3"])
    
    print(f"\n=======================================================")
    print(f" SLICE OLAP: MODELLO = {modello} | METRICA = {col_metrica}")
    print(f" Scala colore globale: min={vmin_glob:.2f}, max={vmax_glob:.2f}")
    print(f"=======================================================")
    print(pivot.round(2 if metrica_key != "token" else 0))

    fig, ax = plt.subplots(figsize=(18 if includi_sottodomande else 12, 4.5))
    sns.heatmap(pivot, annot=True, fmt=fmt, cmap=cmap, cbar_kws={'label': label_metrica}, 
                linewidths=1, ax=ax, vmin=vmin_glob, vmax=vmax_glob, 
                annot_kws={"size": 9 if includi_sottodomande else 11})
    
    ax.set_title(f"Evoluzione Harnessing per {modello}: {label_metrica} (L1 -> L2 -> L3)", fontsize=12, fontweight="bold", pad=12)
    ax.set_ylabel("Livello", fontweight="bold")
    ax.set_xlabel("Domanda / Sottovariante", fontweight="bold")
    if includi_sottodomande:
        plt.xticks(rotation=45, ha='right')

    plt.tight_layout()
    tag_sub = "dettaglio30" if includi_sottodomande else "macro10"
    file_png = os.path.join(cartella_out, f"olap_modello_{modello.replace(' ', '_').lower()}_{metrica_key}_{tag_sub}.png")
    plt.savefig(file_png, dpi=300)
    plt.close(fig)
    print(f"-> Grafico salvato: {file_png}")


def slice_fissa_domanda(df, domanda=2, metrica_key="accuratezza", cartella_out="Grafici_olap"):
    os.makedirs(cartella_out, exist_ok=True)
    col_metrica, cmap, fmt, label_metrica = MAPPA_METRICHE[metrica_key]
    vmin_glob, vmax_glob = ottieni_limiti_globali(df, metrica_key)
    
    d = df[df["Domanda"] == domanda]

    pivot = d.pivot_table(index="Modello", columns=["Livello", "Variante"], values=col_metrica, aggfunc="mean")
    
    print(f"\n=======================================================")
    print(f" SLICE OLAP: DOMANDA = {domanda} | METRICA = {col_metrica}")
    print(f" Scala colore globale: min={vmin_glob:.2f}, max={vmax_glob:.2f}")
    print(f"=======================================================")
    print(pivot.round(2 if metrica_key != "token" else 0))

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=True)
    for i, liv in enumerate(["L1", "L2", "L3"]):
        sub = d[d["Livello"] == liv].pivot_table(index="Modello", columns="Variante", values=col_metrica, aggfunc="mean")
        col_var = [c for c in ["base", "a", "b"] if c in sub.columns]
        sub = sub[col_var]
        
        sns.heatmap(sub, annot=True, fmt=fmt, cmap=cmap, cbar=(i == 2), 
                    cbar_kws={'label': label_metrica} if i == 2 else None,
                    linewidths=1, ax=axes[i], vmin=vmin_glob, vmax=vmax_glob)
        axes[i].set_title(f"Livello {liv}", fontsize=11, fontweight="bold")
        axes[i].set_xlabel("Sottovariante di Formulazione", fontweight="bold")
        if i == 0:
            axes[i].set_ylabel("Modello LLM", fontweight="bold")
        else:
            axes[i].set_ylabel("")

    plt.suptitle(f"Analisi di Sensitività alle Sottovarianti - Domanda {domanda} ({label_metrica})", fontsize=13, fontweight="bold", y=1.02)
    plt.tight_layout()
    file_png = os.path.join(cartella_out, f"olap_domanda_{domanda}_sottovarianti_{metrica_key}.png")
    plt.savefig(file_png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"-> Grafico salvato: {file_png}")


def main():
    ap = argparse.ArgumentParser(description="Navigatore Cubo OLAP Multidimensionale")
    ap.add_argument("--livello", help="Fissa il livello (es. L1, L2, L3)")
    ap.add_argument("--modello", help="Fissa il modello (es. 'Claude Sonnet 5.5')")
    ap.add_argument("--domanda", type=int, help="Fissa la domanda (1-10)")
    ap.add_argument("--metrica", choices=["accuratezza", "latenza", "token"], default="accuratezza", help="Misura da analizzare")
    ap.add_argument("--sottodomande", action="store_true", help="Mostra tutte e 30 le sottovarianti invece di aggregare")
    args = ap.parse_args()

    dir_script = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
    cartella_out = os.path.join(dir_script, "Grafici_olap")

    df = carica_cubo()

    if args.livello:
        slice_fissa_livello(df, args.livello.upper(), args.metrica, args.sottodomande, cartella_out)
        return
    if args.modello:
        slice_fissa_modello(df, args.modello, args.metrica, args.sottodomande, cartella_out)
        return
    if args.domanda:
        slice_fissa_domanda(df, args.domanda, args.metrica, cartella_out)
        return

    print("\n" + "="*60)
    print("NAVIGATORE CUBO OLAP: SCELTA METRICA & SOTTODOMANDE")
    print("="*60)
    
    print("1. Quale METRICA vuoi analizzare?")
    print("   [1] Accuratezza del Giudice (default)")
    print("   [2] Latenza (secondi)")
    print("   [3] Token Totali consumati")
    m_choice = input("   Scelta (1-3) [default: 1]: ").strip()
    metrica_scelta = {"2": "latenza", "3": "token"}.get(m_choice, "accuratezza")

    print("\n2. Quale variabile vuoi tenere FERMA?")
    print("   [1] Fissa il LIVELLO (esplora Modelli vs Domande)")
    print("   [2] Fissa il MODELLO (esplora evoluzione L1 -> L2 -> L3)")
    print("   [3] Fissa la DOMANDA (analizza la varianza tra base, a, b)")
    v_choice = input("   Scelta (1-3) [default: 1]: ").strip() or "1"

    if v_choice == "1":
        liv = input("\nQuale livello vuoi fissare? (L1, L2, L3) [default: L2]: ").strip().upper() or "L2"
        sub_choice = input("Vuoi includere tutte le 30 sottodomande estese? (s/n) [default: s]: ").strip().lower()
        inc_sub = False if sub_choice == "n" else True
        slice_fissa_livello(df, liv, metrica_scelta, inc_sub, cartella_out)

    elif v_choice == "2":
        print("\nModelli disponibili:")
        for idx, m in enumerate(MODELLI, 1):
            print(f"   [{idx}] {m}")
        num_m = input("Seleziona numero modello [default: 4 - Claude Sonnet]: ").strip()
        mod_scelto = MODELLI[int(num_m) - 1] if num_m.isdigit() and 1 <= int(num_m) <= len(MODELLI) else "Claude Sonnet 5.5"
        sub_choice = input("Vuoi includere le 30 sottodomande estese? (s/n) [default: n]: ").strip().lower()
        inc_sub = True if sub_choice == "s" else False
        slice_fissa_modello(df, mod_scelto, metrica_scelta, inc_sub, cartella_out)

    elif v_choice == "3":
        num_q = input("\nQuale domanda vuoi fissare? (1-10) [default: 2]: ").strip()
        q_scelta = int(num_q) if num_q.isdigit() and 1 <= int(num_q) <= 10 else 2
        slice_fissa_domanda(df, q_scelta, metrica_scelta, cartella_out)


if __name__ == "__main__":
    main()