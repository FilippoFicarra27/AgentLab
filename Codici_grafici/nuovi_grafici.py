import argparse
import glob
import os
import re
import sys


import matplotlib
if "--mostra" not in sys.argv:
    matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D


MODELLI = ["Gemini 2.5 Flash", "Gemini 3.6 Flash", "Claude Opus 5.5", "Claude Sonnet 5.5", "GPT-4o", "GPT-4o Mini"]
COLORI = ["#ff0000", "#00ff00", "#0000ff", "#000000", "#a9a9a9", "#ff8c00"]
VARIANTI = ["base", "a", "b"]
MARKER = {"base": "o", "a": "D", "b": "s"}


OFFSET_VAR_2D = {"base": 0.0, "a": -0.026, "b": 0.026}
OFFSET_VAR_3D = {"base": (0.0, 0.0), "a": (-0.012, -0.008), "b": (0.012, 0.008)}



def a_numero(x):
    """Converte celle numeriche o testuali ('85,30', '~45.00 s') in float; NaN se impossibile."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return np.nan
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    m = re.search(r"[-+]?\d[\d.,]*", str(x))
    if not m:
        return np.nan
    t = m.group(0)
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    return float(t)


def parse_token(x):
    """'8.114 + 4.844 = 12.958' (anche con '~') -> (in, out, tot). Il punto è il separatore delle migliaia."""
    if isinstance(x, (int, float, np.integer, np.floating)) and not pd.isna(x):
        return np.nan, np.nan, float(x)
    nums = [int(n.replace(".", "")) for n in re.findall(r"\d[\d.]*", str(x))]
    if len(nums) >= 3:
        return nums[0], nums[1], float(nums[-1])
    if len(nums) == 2:
        return nums[0], nums[1], float(nums[0] + nums[1])
    if len(nums) == 1:
        return np.nan, np.nan, float(nums[0])
    return np.nan, np.nan, np.nan


def trova_colonna(colonne, *prefissi):
    for c in colonne:
        nome = str(c).strip().lower()
        if any(nome.startswith(p) for p in prefissi):
            return c
    raise KeyError("Colonna non trovata: " + " / ".join(prefissi))


def leggi_file(path):
    try:
        df = pd.read_excel(path, sheet_name="Dati")
    except ValueError:
        df = pd.read_excel(path, sheet_name=0)
    col = df.columns
    c_liv, c_mod, c_var = trova_colonna(col, "livello"), trova_colonna(col, "modello"), trova_colonna(col, "var")
    c_lat, c_tok, c_acc = trova_colonna(col, "latenza"), trova_colonna(col, "token"), trova_colonna(col, "acc. giudice", "acc giudice")
    df = df[df[c_liv].astype(str).str.match(r"^L\d+$")].copy()
    out = pd.DataFrame()
    var = df[c_var].map(lambda v: str(int(v)) if isinstance(v, float) and float(v).is_integer() else str(v).strip())
    out["domanda"] = var.str.extract(r"^(\d+)", expand=False).astype(int)
    out["variante"] = var.str.replace(r"^\d+", "", regex=True).replace("", "base")
    out["livello"] = df[c_liv].astype(str).str.strip().str.upper()
    out["modello"] = df[c_mod].astype(str).str.strip()
    out["latenza"] = df[c_lat].map(a_numero)
    toks = df[c_tok].map(parse_token)
    out["in_tok"], out["out_tok"], out["tot_tok"] = (toks.map(lambda t: t[i]) for i in range(3))
    out["acc_giudice"] = df[c_acc].map(a_numero)
    out["file"] = os.path.basename(path)
    return out


def carica(cartella, pattern):
    dir_script = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
    
    path_tentativi = [
        os.path.join(cartella, pattern),
        os.path.join(dir_script, cartella, pattern),
        os.path.join(dir_script, "..", cartella, pattern),
        os.path.join(dir_script, "..", "..", cartella, pattern),
        os.path.join(dir_script, pattern),
        os.path.join(".", pattern),
    ]
    
    files = []
    cartella_trovata = cartella
    for p in path_tentativi:
        trovati = sorted(
            glob.glob(p),
            key=lambda x: int(re.search(r"(\d+)\D*$", os.path.splitext(x)[0]).group(1)) if re.search(r"(\d+)\D*$", os.path.splitext(x)[0]) else 0
        )
        if trovati:
            files = trovati
            cartella_trovata = os.path.dirname(p)
            break

    if not files:
        sys.exit(f"Nessun file trovato per '{pattern}'.\nPercorsi testati:\n  - " + "\n  - ".join(path_tentativi))
    
    df = pd.concat([leggi_file(p) for p in files], ignore_index=True)
    chiave = ["domanda", "variante", "livello", "modello"]
    dup = df.duplicated(chiave, keep="first")
    if dup.any():
        print("Attenzione: %d righe duplicate ignorate" % dup.sum())
        df = df[~dup]
    mancanti = df[["latenza", "tot_tok", "acc_giudice"]].isna().any(axis=1).sum()
    if mancanti:
        print("Attenzione: %d righe con valori non leggibili (verranno saltate nei grafici)" % mancanti)
    print("Lette %d righe da %d file (da %s)" % (len(df), len(files), cartella_trovata))
    return df


def ordine_modelli(df):
    presenti = list(df["modello"].unique())
    ordine = [m for m in MODELLI if m in presenti] + [m for m in presenti if m not in MODELLI]
    colori = {m: (COLORI[MODELLI.index(m)] if m in MODELLI else plt.cm.tab20(i)) for i, m in enumerate(ordine)}
    return ordine, colori


def legenda(ax, ordine, colori, **kw):
    h = [Line2D([], [], marker="o", ls="", color=colori[m], markeredgecolor="#222", markeredgewidth=.5, label=m) for m in ordine]
    h += [Line2D([], [], marker=MARKER[v], ls="", color="#666", label={"base": "base", "a": "variante a", "b": "variante b"}[v]) for v in VARIANTI]
    h += [Line2D([], [], marker="o", ls="", color="#b0b0b0", markeredgecolor="#777", label="Ombra 3D (Z=0)")]
    ax.legend(handles=h, fontsize=8, frameon=False, **kw)


def scatter_2d(ax, df, colonna, titolo, ordine, colori, log=False, xlim=None):
    d = df.dropna(subset=[colonna, "latenza", "tot_tok", "acc_giudice"])
    if log:
        escluse = (d[colonna] <= 0).sum()
        d = d[d[colonna] > 0]
        if escluse:
            print("  %s: %d punti con valore 0 non mostrati (scala logaritmica)" % (titolo, escluse))
            
    livelli = sorted(df["livello"].unique())
    n_mod = len(ordine)

    for liv_idx, liv in enumerate(livelli):
       
        if liv_idx % 2 == 0:
            ax.axhspan(liv_idx - 0.45, liv_idx + 0.45, color="#fbfcfd", zorder=0)

        for m_idx, m in enumerate(ordine):
            sub = d[(d["livello"] == liv) & (d["modello"] == m)]
            if sub.empty:
                continue

            
            y_corsia = liv_idx + (m_idx - (n_mod - 1) / 2) * 0.12

            
            for _, row in sub.iterrows():
                v = row["variante"]
                
                y_punto = y_corsia + OFFSET_VAR_2D[v]
                ax.scatter(row[colonna], y_punto, s=44, marker=MARKER[v], color=colori[m],
                           alpha=0.7, edgecolor="black", linewidth=0.5, zorder=3)
            
    for i in range(len(livelli) - 1):
        ax.axhline(i + 0.5, color="#d0d0d0", linestyle="--", linewidth=0.8, zorder=1)
        
    ax.set_yticks(range(len(livelli)))
    ax.set_yticklabels(livelli, fontweight="bold", fontsize=10)
    ax.set_ylim(len(livelli) - 0.48, -0.48)  # L1 in alto

    if log:
        ax.set_xscale("log")

    
    if colonna == "acc_giudice":
        ax.set_xlim(-0.04, 1.04)
        ticks = np.arange(0.0, 1.05, 0.1)
        ax.set_xticks(ticks)
        ax.set_xticklabels([f"{t:.1f}" for t in ticks], fontsize=8.5)

    elif colonna == "tot_tok":
        ax.set_xlim(800, 250000)
        t_valori = [1000, 2500, 5000, 10000, 25000, 50000, 100000, 200000]
        t_labels = ["1k", "2.5k", "5k", "10k", "25k", "50k", "100k", "200k"]
        ax.set_xticks(t_valori)
        ax.set_xticklabels(t_labels, fontsize=8.5)

    elif colonna == "latenza":
        ax.set_xlim(1.0, 380.0)
        l_valori = [1, 2, 5, 10, 20, 50, 100, 200, 350]
        l_labels = ["1", "2", "5", "10", "20", "50", "100", "200", "350"]
        ax.set_xticks(l_valori)
        ax.set_xticklabels(l_labels, fontsize=8.5)
    elif xlim:
        ax.set_xlim(*xlim)

    ax.set_xlabel(titolo, fontweight="bold")
    ax.grid(axis="x", color="#e5e5e5", linestyle=":", linewidth=0.7)
    ax.set_axisbelow(True)
    for lato in ("top", "right"):
        ax.spines[lato].set_visible(False)


def scatter_3d(ax, df, ordine, colori, livello=None):
    d = df.dropna(subset=["latenza", "tot_tok", "acc_giudice"])
    d = d[(d["tot_tok"] > 0) & (d["latenza"] > 0)]
    if livello:
        d = d[d["livello"] == livello]

    hi_y = np.ceil(np.log10(380.0))

    
    
    for _, r in d.iterrows():
        dx, dy = OFFSET_VAR_3D[r["variante"]]
        x = np.log10(r["tot_tok"]) + dx
        y = np.log10(r["latenza"]) + dy
        v = r["variante"]
        ax.scatter(x, y, 0.0, s=28, marker=MARKER[v], color="#b0b0b0",
                   edgecolor="#777777", linewidth=0.5, alpha=0.45, zorder=1)

    
    for _, r in d.iterrows():
        dx, dy = OFFSET_VAR_3D[r["variante"]]
        x = np.log10(r["tot_tok"]) + dx
        y = np.log10(r["latenza"]) + dy
        z = r["acc_giudice"]
        c = colori.get(r["modello"], "#444")
        
        ax.plot([x, x], [y, y], [0.0, z], color=c, linestyle=":", linewidth=0.5, alpha=0.30, zorder=2)
        ax.plot([x, x], [y, hi_y], [z, z], color=c, linestyle=":", linewidth=0.5, alpha=0.25, zorder=2)

    
    for m in ordine:
        for v in VARIANTI:
            s = d[(d["modello"] == m) & (d["variante"] == v)]
            if s.empty:
                continue
            dx, dy = OFFSET_VAR_3D[v]
            ax.scatter(np.log10(s["tot_tok"]) + dx, np.log10(s["latenza"]) + dy, s["acc_giudice"],
                       s=40, marker=MARKER[v], color=colori[m], alpha=0.88,
                       edgecolor="black", linewidth=0.5, depthshade=False, zorder=4)

   
    ax.set_xlim(np.log10(800), np.log10(250000))
    ax.set_xticks([3, 4, 5], ["$10^3$\n(1k)", "$10^4$\n(10k)", "$10^5$\n(100k)"])
    ax.set_xlabel("Token totali", fontweight="bold", labelpad=10)

    ax.set_ylim(np.log10(1.0), hi_y)
    ax.set_yticks([0, 1, 2], ["$10^0$\n(1s)", "$10^1$\n(10s)", "$10^2$\n(100s)"])
    ax.set_ylabel("Latenza (s)", fontweight="bold", labelpad=10)

    ax.set_zlim(0.0, 1.05)
    ax.set_zticks(np.arange(0.0, 1.05, 0.2))
    ax.set_zlabel("Accuratezza Giudice", fontweight="bold", labelpad=8)
    
    ax.xaxis.pane.set_facecolor("#fafbfc")
    ax.yaxis.pane.set_facecolor("#f8f9fa")
    ax.zaxis.pane.set_facecolor("#ffffff")
    ax.xaxis.pane.set_edgecolor("#e0e0e0")
    ax.yaxis.pane.set_edgecolor("#e0e0e0")
    ax.zaxis.pane.set_edgecolor("#e0e0e0")

    ax.view_init(elev=24, azim=-55)


def main():
    DIR_SCRIPT = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
    
    if os.path.isdir(os.path.join(DIR_SCRIPT, "tabelle_excel")):
        cartella_default = os.path.join(DIR_SCRIPT, "tabelle_excel")
    elif os.path.isdir(os.path.join(DIR_SCRIPT, "..", "tabelle_excel")):
        cartella_default = os.path.abspath(os.path.join(DIR_SCRIPT, "..", "tabelle_excel"))
    else:
        cartella_default = "tabelle_excel"

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cartella", default=cartella_default)
    ap.add_argument("--pattern", default="confronto_modelli_domanda*.xlsx")
    ap.add_argument("--out", default=os.path.join(DIR_SCRIPT, "grafici"))
    ap.add_argument("--livello", help="mostra solo questo livello nel grafico 3D (es. L2)")
    ap.add_argument("--mostra", action="store_true", help="apre le finestre dei grafici oltre a salvare i PNG")
    ap.add_argument("--dpi", type=int, default=200)
    a = ap.parse_args()

    df = carica(a.cartella, a.pattern)
    os.makedirs(a.out, exist_ok=True)
    ordine, colori = ordine_modelli(df)
    n_liv = df["livello"].nunique()
    specifiche = [
        ("latenza", "Latenza (s)", True, None, "scatter_latenza.png"),
        ("tot_tok", "Token totali", True, None, "scatter_token.png"),
        ("acc_giudice", "Accuratezza del giudice", False, (-0.04, 1.04), "scatter_accuratezza.png")
    ]

    
    for col, tit, log, xlim, nome in specifiche:
        fig, ax = plt.subplots(figsize=(8, 2.6 + .9 * n_liv))
        scatter_2d(ax, df, col, tit, ordine, colori, log, xlim)
        legenda(ax, ordine, colori, loc="center left", bbox_to_anchor=(1.01, .5))
        fig.savefig(os.path.join(a.out, nome), dpi=a.dpi, bbox_inches="tight")
        if not a.mostra:
            plt.close(fig)

    
    fig = plt.figure(figsize=(9, 7))
    ax = fig.add_subplot(projection="3d")
    scatter_3d(ax, df, ordine, colori, a.livello)
    legenda(ax, ordine, colori, loc="upper left", bbox_to_anchor=(0, .95))
    fig.savefig(os.path.join(a.out, "scatter_3d.png"), dpi=a.dpi, bbox_inches="tight")
    if not a.mostra:
        plt.close(fig)

    
    fig = plt.figure(figsize=(15, 10))
    for i, (col, tit, log, xlim, _) in enumerate(specifiche):
        ax = fig.add_subplot(2, 2, i + 1)
        scatter_2d(ax, df, col, tit, ordine, colori, log, xlim)
    ax = fig.add_subplot(2, 2, 4, projection="3d")
    scatter_3d(ax, df, ordine, colori, a.livello)
    legenda(fig.axes[0], ordine, colori, loc="lower left", bbox_to_anchor=(0, 1.02), ncol=5)
    fig.subplots_adjust(hspace=.28, wspace=.18)
    fig.savefig(os.path.join(a.out, "quadro_insieme.png"), dpi=a.dpi, bbox_inches="tight")
    print(f"Grafici generali salvati con successo in: {a.out}/")
    
    if a.mostra:
        plt.show()


if __name__ == "__main__":
    main()