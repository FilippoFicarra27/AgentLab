import matplotlib.pyplot as plt
import numpy as np

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

questions = [f"Q{i}" for i in range(1, 11)]
x = np.arange(len(questions))
width = 0.25  # Larghezza delle barre

# Palette colori per i livelli
colors = {
    'L1': '#ff0000',  # Rosso tenue
    'L2': '#00ff00',  # Arancione
    'L3': '#0000ff'   # Verde
}

# ==============================================================================
# 1. DATASET LATENZE (in secondi)
# ==============================================================================
latency_data = {
    "Gemini 2.5 Flash": {
        "L1": [29.24, 24.66, 28.76, 7.18, 13.62, 52.09, 19.41, 27.45, 8.31, 30.59],
        "L2": [3.63, 2.66, 1.43, 1.63, 1.71, 10.48, 12.05, 3.52, 17.03, 2.81],
        "L3": [3.65, 3.93, 2.16, 1.74, 1.84, 11.16, 43.03, 6.67, 35.98, 2.29]
    },
    "Gemini 3.8 Flash": {
        "L1": [46.85, 16.07, 27.46, 69.61, 192.89, 110.95, 26.61, 38.11, 74.18, 47.45],
        "L2": [9.05, 7.49, 23.23, 5.84, 4.26, 16.44, 18.54, 23.41, 13.27, 10.56],
        "L3": [9.25, 10.29, 10.03, 8.78, 6.12, 20.79, 48.28, 10.03, 56.02, 11.69]
    },
    "Claude Sonnet 5.5": {
        "L1": [26.80, 17.43, 29.87, 17.58, 32.13, 33.70, 27.16, 50.26, 55.52, 66.46],
        "L2": [7.53, 15.36, 4.66, 5.27, 5.27, 11.73, 17.30, 25.23, 16.52, 11.06],
        "L3": [6.81, 32.35, 5.32, 4.80, 4.10, 13.52, 43.96, 12.07, 41.76, 12.25]
    },
    "Claude Opus 5.5": {
        "L1": [24.11, 19.76, 49.25, 23.18, 39.38, 32.66, 28.20, 40.38, 46.51, 87.48],
        "L2": [13.13, 9.12, 13.87, 8.82, 8.20, 17.87, 21.25, 28.94, 34.30, 20.40],
        "L3": [11.81, 11.04, 12.37, 7.73, 9.03, 17.02, 51.34, 22.83, 90.39, 41.66]
    }
}

# ==============================================================================
# 2. DATASET TOKEN TOTALI
# ==============================================================================
token_data = {
    "Gemini 2.5 Flash": {
        "L1": [89078, 11035, 60674, 2726, 7387, 15440, 10643, 8798, 1023, 4553],
        "L2": [1644, 1902, 1664, 1767, 1820, 4110, 5730, 2175, 9462, 2022],
        "L3": [1739, 2005, 1805, 1827, 1886, 3834, 4747, 3008, 4964, 2015]
    },
    "Gemini 3.8 Flash": {
        "L1": [5398, 4540, 5544, 8773, 9230, 13832, 9198, 13984, 58404, 15498],
        "L2": [2023, 2072, 1959, 2225, 2025, 3933, 5806, 3012, 4411, 2904],
        "L3": [2010, 2142, 2057, 2084, 2047, 3839, 4812, 2950, 8072, 2899]
    },
    "Claude Sonnet 5.5": {
        "L1": [90683, 8163, 90549, 10867, 185278, 93505, 137285, 141512, 38976, 198899],
        "L2": [3232, 7895, 3141, 3326, 3183, 4201, 8489, 10465, 8759, 3988],
        "L3": [3277, 7694, 3270, 3313, 3213, 4250, 7082, 4268, 8684, 4142]
    },
    "Claude Opus 5.5": {
        "L1": [5930, 8051, 13676, 11995, 17262, 10481, 10783, 11192, 20167, 40752],
        "L2": [3637, 3487, 3833, 3509, 3357, 4406, 8631, 8046, 22575, 4646],
        "L3": [3631, 3587, 3873, 3420, 3578, 4325, 7337, 4854, 55829, 15090]
    }
}

# ==============================================================================
# FUNZIONE DI GENERAZIONE ISTOGRAMMA
# ==============================================================================
def genera_istogramma(dati_modello, nome_modello, metrica, y_label, nome_file, usa_log=False):
    plt.figure(figsize=(10, 5))
    
    # 3 barre per ciascuna domanda (L1, L2, L3)
    plt.bar(x - width, dati_modello["L1"], width, label='L1: Zero-Context', color=colors['L1'], edgecolor='black', linewidth=0.5)
    plt.bar(x, dati_modello["L2"], width, label='L2: Agentic Recon', color=colors['L2'], edgecolor='black', linewidth=0.5)
    plt.bar(x + width, dati_modello["L3"], width, label='L3: Deterministic Pre-Harnessing', color=colors['L3'], edgecolor='black', linewidth=0.5)
    
    if usa_log:
        plt.yscale('log')
        
    plt.xlabel('Domanda di Benchmark')
    plt.ylabel(y_label)
    plt.title(f"{metrica} - {nome_modello}")
    plt.xticks(x, questions)
    plt.grid(axis='y', linestyle='--', alpha=0.6)
    plt.legend(frameon=True, facecolor='white', framealpha=0.9)
    plt.tight_layout()
    
    plt.savefig(nome_file, dpi=300)
    plt.close()
    print(f"Salvato: {nome_file}")

# ==============================================================================
# GENERAZIONE DEI 4 ISTOGRAMMI DI LATENZA
# ==============================================================================
for modello, dati in latency_data.items():
    file_slug = modello.lower().replace(" ", "_").replace(".", "_")
    genera_istogramma(
        dati_modello=dati,
        nome_modello=modello,
        metrica="Latenza di Query",
        y_label="Latenza (secondi)",
        nome_file=f"latenza_{file_slug}.png",
        usa_log=False
    )

# ==============================================================================
# GENERAZIONE DEI 4 ISTOGRAMMI DEI TOKEN (SCALA LOGARITMICA)
# ==============================================================================
for modello, dati in token_data.items():
    file_slug = modello.lower().replace(" ", "_").replace(".", "_")
    genera_istogramma(
        dati_modello=dati,
        nome_modello=modello,
        metrica="Token Totali Consumati",
        y_label="Token Totali (Scala Logaritmica)",
        nome_file=f"token_{file_slug}.png",
        usa_log=True
    )

print("\nTutti gli 8 istogrammi sono stati creati con successo!")