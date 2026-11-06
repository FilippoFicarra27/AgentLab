import argparse
import glob
import os
import re
import sys

USO_GUI = False
try:
    import tkinter
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        import matplotlib
        matplotlib.use("TkAgg")
        USO_GUI = True
except ImportError:
    pass

if not USO_GUI:
    import matplotlib
    matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.widgets import RadioButtons

MODELLI = ["Gemini 2.5 Flash", "Gemini 3.6 Flash", "Claude Opus 5.5", "Claude Sonnet 5.5", "GPT-4o", "GPT-4o Mini"]
COLORI = ["#ff0000", "#00ff00", "#0000ff", "#000000", "#a9a9a9", "#ff8c00"]
VARIANTI = ["base", "a", "b"]
MARKER = {"base": "o", "a": "D", "b": "s"}

OFFSET_VAR_2D = {"base": 0.0, "a": -0.026, "b": 0.026}
OFFSET_VAR_3D = {"base": (0.0, 0.0), "a": (-0.012, -0.008), "b": (0.012, 0.008)}


def a_numero(v):
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
        "livello": df[c_liv].astype(str).str.strip().str.upper(),
        "modello": df[c_mod].astype(str).str.strip(),
        "latenza": df[c_lat].map(a_numero),
        "tot_tok": df[c_tok].map(totale_token),
        "acc_giudice": df[c_acc].map(a_numero),
    })


def carica_dati():
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
    cartella_trovata = ""
    for c in cartelle_tentativi:
        if os.path.exists(c):
            trovati = sorted(
                glob.glob(os.path.join(c, "confronto_modelli_domanda*.xlsx")),
                key=lambda x: int(re.search(r"(\d+)\D*$", os.path.splitext(x)[0]).group(1)) if re.search(r"(\d+)\D*$", os.path.splitext(x)[0]) else 0
            )
            if trovati:
                files = trovati
                cartella_trovata = c
                break

    if not files:
        sys.exit(f"ERRORE: Nessun file trovato!\n" + "\n".join(f" - {p}" for p in cartelle_tentativi))

    print(f"Lette {len(files)} tabelle da: {cartella_trovata}")
    df = pd.concat([leggi_file(p) for p in files], ignore_index=True)
    dup = df.duplicated(["domanda", "variante", "livello", "modello"], keep="first")
    if dup.any():
        df = df[~dup]
    return df


class App:
    SPEC = [("latenza", "Latenza (s)", True), ("tot_tok", "Token totali", True),
            ("acc_giudice", "Accuratezza del giudice", False)]

    def __init__(self, df, libera=False, domanda_fissata=None):
        self.df = df
        self.libera = libera
        presenti = list(df["modello"].unique())
        self.modelli = [m for m in MODELLI if m in presenti] + [m for m in presenti if m not in MODELLI]
        self.colori = {m: (COLORI[MODELLI.index(m)] if m in MODELLI else plt.cm.tab20(i)) for i, m in enumerate(self.modelli)}
        self.livelli = sorted(df["livello"].unique())
        self.domande = sorted(df["domanda"].unique())
        self.q = domanda_fissata if (domanda_fissata in self.domande) else self.domande[0]
        self.punti, self.note = {}, {}

        self.fig = plt.figure(figsize=(15, 8.5))
        gs = self.fig.add_gridspec(2, 2, left=0.19, right=0.98, top=0.91, bottom=0.08, wspace=0.20, hspace=0.28)
        self.ax2d = [self.fig.add_subplot(gs[0, 0]), self.fig.add_subplot(gs[0, 1]), self.fig.add_subplot(gs[1, 0])]
        self.ax3d = self.fig.add_subplot(gs[1, 1], projection="3d")
        self.ax3d.view_init(elev=24, azim=-55)
        
        self.titolo = self.fig.text(0.19, 0.96, "", ha="left", va="top", fontsize=14, fontweight="bold")

        ax_r = self.fig.add_axes([0.02, 0.48, 0.13, 0.42])
        ax_r.set_title("Seleziona", fontsize=11, loc="left", fontweight="bold")
        self.radio = RadioButtons(ax_r, ["Domanda %d" % q for q in self.domande], active=self.domande.index(self.q))
        self.radio.on_clicked(lambda lab: self.aggiorna(int(re.search(r"\d+", lab).group(0))))
        self._ax_r = ax_r

        ax_l = self.fig.add_axes([0.02, 0.05, 0.15, 0.40])
        ax_l.axis("off")
        h = [Line2D([], [], marker="o", ls="", color=self.colori[m], markeredgecolor="#222", markeredgewidth=.5, label=m) for m in self.modelli]
        h += [Line2D([], [], marker=MARKER[v], ls="", color="#666", label={"base": "formulazione base", "a": "variante a", "b": "variante b"}[v]) for v in VARIANTI]
        h += [Line2D([], [], marker="o", ls="", color="#b0b0b0", markeredgecolor="#777", label="Ombra 3D (Z=0)")]
        ax_l.legend(handles=h, loc="upper left", frameon=True, facecolor="#fafafa", edgecolor="#ddd", fontsize=8.5)

        self.lim = {"latenza": (1.0, 380.0), "tot_tok": (800, 250000), "acc_giudice": (-0.04, 1.04)}

        if USO_GUI:
            self.fig.canvas.mpl_connect("motion_notify_event", self.hover)
            self.fig.canvas.mpl_connect("key_press_event", self.tasto)
        
        self.aggiorna(self.q)

    def scatter2d(self, ax, d, col, titolo, log):
        d = d.dropna(subset=[col])
        if log:
            d = d[d[col] > 0]
        n_mod = len(self.modelli)
        xs, ys, righe = [], [], []

        for liv_idx, liv in enumerate(self.livelli):
            if liv_idx % 2 == 0:
                ax.axhspan(liv_idx - 0.45, liv_idx + 0.45, color="#fbfcfd", zorder=0)

            for m_idx, m in enumerate(self.modelli):
                sub = d[(d["livello"] == liv) & (d["modello"] == m)]
                if sub.empty:
                    continue

                y_corsia = liv_idx + (m_idx - (n_mod - 1) / 2) * 0.12

                # Punti con micro-dodge e SENZA sfumatura (alpha=1.0 pieno)
                for _, row in sub.iterrows():
                    v = row["variante"]
                    y_punto = y_corsia + OFFSET_VAR_2D[v]
                    ax.scatter(row[col], y_punto, s=58, marker=MARKER[v], color=self.colori[m],
                               edgecolor="black", linewidth=0.5, alpha=0.8, zorder=3)
                    xs.append(row[col])
                    ys.append(y_punto)
                    righe.append(row.to_dict())

        for i in range(len(self.livelli) - 1):
            ax.axhline(i + 0.5, color="#d0d0d0", linestyle="--", linewidth=0.8, zorder=1)

        ax.set_yticks(range(len(self.livelli)))
        ax.set_yticklabels(self.livelli, fontweight="bold", fontsize=10)
        ax.set_ylim(len(self.livelli) - 0.48, -0.48)

        if log:
            ax.set_xscale("log")

        if col == "acc_giudice":
            ax.set_xlim(-0.04, 1.04)
            ticks = np.arange(0.0, 1.05, 0.1)
            ax.set_xticks(ticks)
            ax.set_xticklabels([f"{t:.1f}" for t in ticks], fontsize=8.5)
        elif col == "tot_tok":
            ax.set_xlim(800, 250000)
            t_valori = [1000, 2500, 5000, 10000, 25000, 50000, 100000, 200000]
            ax.set_xticks(t_valori)
            ax.set_xticklabels(["1k", "2.5k", "5k", "10k", "25k", "50k", "100k", "200k"], fontsize=8.5)
        elif col == "latenza":
            ax.set_xlim(1.0, 380.0)
            l_valori = [1, 2, 5, 10, 20, 50, 100, 200, 350]
            ax.set_xticks(l_valori)
            ax.set_xticklabels(["1", "2", "5", "10", "20", "50", "100", "200", "350"], fontsize=8.5)

        ax.set_xlabel(titolo, fontweight="bold")
        ax.grid(axis="x", color="#e5e5e5", linestyle=":", linewidth=0.7)
        ax.set_axisbelow(True)
        for lato in ("top", "right"):
            ax.spines[lato].set_visible(False)

        self.punti[ax] = (np.array(xs), np.array(ys), righe)
        ann = ax.annotate("", xy=(0, 0), xytext=(14, 14), textcoords="offset points", fontsize=9, zorder=10,
                          bbox=dict(boxstyle="round", fc="white", ec="#999", alpha=.95),
                          arrowprops=dict(arrowstyle="-", color="#999"))
        ann.set_visible(False)
        self.note[ax] = ann

    def scatter3d(self, d):
        ax = self.ax3d
        elev, azim = ax.elev, ax.azim
        ax.cla()
        
        d = d.dropna(subset=["latenza", "tot_tok", "acc_giudice"])
        d = d[(d["tot_tok"] > 0) & (d["latenza"] > 0)]
        hi_y = np.ceil(np.log10(380.0))

        # 1. Ombreggiature SOLO nelle proiezioni
        for _, r in d.iterrows():
            dx, dy = OFFSET_VAR_3D[r["variante"]]
            x = np.log10(r["tot_tok"]) + dx
            y = np.log10(r["latenza"]) + dy
            v = r["variante"]
            ax.scatter(x, y, 0.0, s=32, marker=MARKER[v], color="#b0b0b0",
                       edgecolor="#777777", linewidth=0.5, alpha=0.45, zorder=1)

        for _, r in d.iterrows():
            dx, dy = OFFSET_VAR_3D[r["variante"]]
            x = np.log10(r["tot_tok"]) + dx
            y = np.log10(r["latenza"]) + dy
            z = r["acc_giudice"]
            colore = self.colori.get(r["modello"], "#444")
            
            ax.plot([x, x], [y, y], [0.0, z], color=colore, linestyle=":", linewidth=0.5, alpha=0.30, zorder=2)
            ax.plot([x, x], [y, hi_y], [z, z], color=colore, linestyle=":", linewidth=0.5, alpha=0.25, zorder=2)

        
        for m in self.modelli:
            for v in VARIANTI:
                s = d[(d["modello"] == m) & (d["variante"] == v)]
                if s.empty:
                    continue
                dx, dy = OFFSET_VAR_3D[v]
                ax.scatter(np.log10(s["tot_tok"]) + dx, np.log10(s["latenza"]) + dy, s["acc_giudice"],
                           s=55, marker=MARKER[v], color=self.colori[m], edgecolor="black",
                           linewidth=0.5, depthshade=False, alpha=0.88, zorder=4)

        ax.set_xlim(np.log10(800), np.log10(250000))
        ax.set_xticks([3, 4, 5], ["$10^3$\n(1k)", "$10^4$\n(10k)", "$10^5$\n(100k)"])
        ax.set_xlabel("Token totali", fontweight="bold", labelpad=12)

        ax.set_ylim(np.log10(1.0), hi_y)
        ax.set_yticks([0, 1, 2], ["$10^0$\n(1s)", "$10^1$\n(10s)", "$10^2$\n(100s)"])
        ax.set_ylabel("Latenza (s)", fontweight="bold", labelpad=12)

        ax.set_zlim(0.0, 1.05)
        ax.set_zticks(np.arange(0.0, 1.05, 0.2))
        ax.set_zlabel("Accuratezza Giudice", fontweight="bold", labelpad=8)

        ax.xaxis.pane.set_facecolor("#fafbfc")
        ax.yaxis.pane.set_facecolor("#f8f9fa")
        ax.zaxis.pane.set_facecolor("#ffffff")
        ax.xaxis.pane.set_edgecolor("#e0e0e0")
        ax.yaxis.pane.set_edgecolor("#e0e0e0")
        ax.zaxis.pane.set_edgecolor("#e0e0e0")

        ax.view_init(elev=elev if elev is not None else 24, azim=azim if azim is not None else -55)

    def aggiorna(self, q):
        self.q = q
        d = self.df[self.df["domanda"] == q]
        for ax, (col, tit, log) in zip(self.ax2d, self.SPEC):
            ax.cla()
            self.scatter2d(ax, d, col, tit, log)
        self.scatter3d(d)
        self.titolo.set_text("Domanda %d" % q)
        idx = self.domande.index(q)
        if self.radio.value_selected != "Domanda %d" % q:
            self.radio.eventson = False
            self.radio.set_active(idx)
            self.radio.eventson = True
        if USO_GUI:
            self.fig.canvas.draw_idle()

    def hover(self, ev):
        for ax, ann in self.note.items():
            if ann.get_visible() and ax is not ev.inaxes:
                ann.set_visible(False)
                self.fig.canvas.draw_idle()
        if ev.inaxes not in self.punti or ev.x is None:
            return
        ax = ev.inaxes
        xs, ys, righe = self.punti[ax]
        if len(xs) == 0:
            return
        pix = ax.transData.transform(np.column_stack([xs, ys]))
        dist = np.hypot(pix[:, 0] - ev.x, pix[:, 1] - ev.y)
        i = int(dist.argmin())
        ann = self.note[ax]
        if dist[i] < 12:
            r = righe[i]
            ann.xy = (xs[i], ys[i])
            ann.set_text("%s (%s)\nFormulazione: %d%s\nLatenza: %.2f s\nToken: %d\nAccuratezza: %.2f" % (
                r["modello"], r["livello"], r["domanda"], "" if r["variante"] == "base" else r["variante"],
                r["latenza"], r["tot_tok"], r["acc_giudice"]))
            ann.set_visible(True)
        else:
            ann.set_visible(False)
        self.fig.canvas.draw_idle()

    def tasto(self, ev):
        i = self.domande.index(self.q)
        if ev.key in ("right", "down", "pageup"):
            self.aggiorna(self.domande[(i + 1) % len(self.domande)])
        elif ev.key in ("left", "up", "pagedown"):
            self.aggiorna(self.domande[(i - 1) % len(self.domande)])
        elif ev.key and ev.key.isdigit():
            q = 10 if ev.key == "0" else int(ev.key)
            if q in self.domande:
                self.aggiorna(q)


def main():
    ap = argparse.ArgumentParser(description="Visualizzatore Scatter Domanda SRE")
    ap.add_argument("--domanda", type=int, help="domanda iniziale (1-10)")
    ap.add_argument("--salva", metavar="FILE.png", help="salva il layout della domanda scelta e termina")
    ap.add_argument("--scala-libera", action="store_true", help="scale degli assi calibrate sulla singola domanda")
    ap.add_argument("--dpi", type=int, default=150)
    a, _ = ap.parse_known_args()

    q_scelta = a.domanda
    if q_scelta is None and sys.stdin.isatty():
        try:
            inp = input("\nInserisci il numero della domanda da visualizzare (1-10) [premi Invio per Domanda 1]: ").strip()
            if inp.isdigit() and 1 <= int(inp) <= 10:
                q_scelta = int(inp)
        except Exception:
            pass

    df = carica_dati()
    app = App(df, libera=a.scala_libera, domanda_fissata=q_scelta)

    dir_script = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
    cartella_out = os.path.join(dir_script, "Grafici_domande")
    os.makedirs(cartella_out, exist_ok=True)

    if a.salva:
        destinazione = a.salva if os.path.isabs(a.salva) else os.path.join(cartella_out, a.salva)
        app.fig.savefig(destinazione, dpi=a.dpi)
        print("Salvato con successo in:", destinazione)
    elif USO_GUI:
        plt.show()
    else:
        file_out = os.path.join(cartella_out, f"domanda_{app.q}.png")
        app.fig.savefig(file_out, dpi=a.dpi)
        print(f"\n[INFO] Grafico salvato automaticamente in:\n -> {file_out}")


if __name__ == "__main__":
    main()