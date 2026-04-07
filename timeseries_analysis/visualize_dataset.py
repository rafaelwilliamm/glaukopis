import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# Resolve CSV path relative to this script's directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(SCRIPT_DIR, "timeseries_seed_101.csv")

def visualize_data(csv_file=CSV_FILE):
    df = pd.read_csv(csv_file)

    fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)
    fig.suptitle("Análise de Série Temporal — Engajamento Su-27 (Seed 101)", fontsize=14, fontweight='bold')

    # ── 1. Trajetória X: Tendência vs Realidade ──────────────────────────────
    ax1 = axes[0]
    ax1.plot(df['time'], df['TGT_01_pos_x'], label='Posição Real (Tendência)', color='green', linewidth=2, zorder=5)
    
    # If missile launched, also show interceptor trajectory
    missile_data = df[df['missile_launched'] == True]
    if not missile_data.empty:
        ax1.plot(missile_data['time'], missile_data['INTERCEPTOR_01_pos_x'],
                 label='Interceptor (Trajetória)', color='orange', linewidth=1.5, linestyle='--')
    
    # Mark track confirmation moment
    confirmed = df[df['track_status'] == 'CONFIRMED']
    if not confirmed.empty:
        t_confirm = confirmed['time'].iloc[0]
        ax1.axvline(t_confirm, color='blue', linestyle=':', alpha=0.7, label=f'Track CONFIRMED (t={t_confirm:.1f}s)')
    
    ax1.set_ylabel('Posição X (m)')
    ax1.set_title('Tendência — Posição do Alvo no Eixo X')
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)

    # ── 2. SNR ao longo do tempo ──────────────────────────────────────────────
    ax2 = axes[1]
    ax2.plot(df['time'], df['snr_db'], label='SNR (dB)', color='purple', linewidth=1.2, alpha=0.8)
    ax2.axhline(y=13, color='red', linestyle='--', linewidth=1.5, label='Limiar CFAR (~13 dB)')
    ax2.fill_between(df['time'], df['snr_db'], 13,
                     where=(df['snr_db'] > 13), color='green', alpha=0.15, label='Detectado')
    ax2.fill_between(df['time'], df['snr_db'], 13,
                     where=(df['snr_db'] <= 13), color='red', alpha=0.15, label='Abaixo do limiar')
    ax2.set_ylabel('SNR (dB)')
    ax2.set_title('Ruído — Sinal-Ruído do Radar ao Longo do Tempo')
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)

    # ── 3. RCS instantâneo (variação estocástica) ─────────────────────────────
    ax3 = axes[2]
    ax3.plot(df['time'], df['TGT_01_rcs_instantaneous'], label='RCS Instantâneo (Swerling)', color='red', linewidth=0.8, alpha=0.7)
    ax3.plot(df['time'], df['TGT_01_rcs_mean'], label='RCS Médio (Tendência)', color='darkred', linewidth=2, linestyle='--')
    ax3.set_ylabel('RCS (m²)')
    ax3.set_xlabel('Tempo (s)')
    ax3.set_title('Série Estocástica — RCS do Alvo (Modelo Swerling)')
    ax3.legend(fontsize=9)
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()
    output_path = os.path.join(SCRIPT_DIR, "time_series_plot.png")
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Gráfico salvo em: {output_path}")
    plt.show()

if __name__ == "__main__":
    visualize_data()
