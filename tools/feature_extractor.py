#!/usr/bin/env python3
"""
feature_extractor.py — Windowed MAV & RMS Feature Analysis

Loads the synthetic healthy and faulty baseline CSVs, applies a sliding
512-sample window, and computes two statistical features at each step:

  • MAV (Mean Absolute Value):  MAV = (1/N) × Σ|x[i]|
  • RMS (Root Mean Square):     RMS = √( (1/N) × Σ x[i]² )

Generates a comparative plot showing which feature provides the widest
mathematical distance (separation) between healthy and faulty profiles.

Usage:
    python3 tools/feature_extractor.py
"""

import os
import sys
import numpy as np
import csv
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for headless execution
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

# ─────────────────────────── Configuration ───────────────────────────

WINDOW_SIZE = 512                   # Samples per feature window
STEP_SIZE   = 64                    # Sliding step (75% overlap with 512-window)

# Paths
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR     = os.path.join(PROJECT_ROOT, "data")
PLOTS_DIR    = os.path.join(PROJECT_ROOT, "plots")

HEALTHY_CSV  = os.path.join(DATA_DIR, "healthy_baseline.csv")
FAULTY_CSV   = os.path.join(DATA_DIR, "faulty_baseline.csv")
OUTPUT_PLOT  = os.path.join(PLOTS_DIR, "feature_comparison.png")


# ─────────────────────────── CSV Loader ───────────────────────────

def load_signal(filepath: str) -> tuple[np.ndarray, np.ndarray]:
    """
    Load a CSV file with columns: time_s, current_A

    Returns
    -------
    time   : 1-D array of timestamps (seconds)
    signal : 1-D array of current values (Amps)
    """
    if not os.path.isfile(filepath):
        print(f"  ✗ File not found: {filepath}")
        print("    Run signal_simulator.py first to generate baseline data.")
        sys.exit(1)

    time_vals = []
    signal_vals = []

    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            time_vals.append(float(row["time_s"]))
            signal_vals.append(float(row["current_A"]))

    return np.array(time_vals), np.array(signal_vals)


# ─────────────────────────── Feature Functions ───────────────────────────

def compute_mav(window: np.ndarray) -> float:
    """
    Mean Absolute Value (MAV)

        MAV = (1/N) × Σ |x[i]|     for i = 0 .. N-1

    Widely used in EMG / vibration analysis. Linear amplitude estimator.
    """
    return np.mean(np.abs(window))


def compute_rms(window: np.ndarray) -> float:
    """
    Root Mean Square (RMS)

        RMS = √( (1/N) × Σ x[i]² )     for i = 0 .. N-1

    Power-proportional amplitude estimator. More sensitive to peaks
    and transients than MAV.
    """
    return np.sqrt(np.mean(window ** 2))


# ─────────────────────────── Sliding Window Engine ───────────────────────────

def extract_features(
    signal: np.ndarray,
    window_size: int = WINDOW_SIZE,
    step_size: int = STEP_SIZE,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Slide a window across the signal and compute MAV and RMS at each position.

    Parameters
    ----------
    signal      : Input signal array
    window_size : Number of samples per window
    step_size   : Step between consecutive windows

    Returns
    -------
    window_indices : Center index of each window
    mav_values     : MAV for each window
    rms_values     : RMS for each window
    """
    num_windows = (len(signal) - window_size) // step_size + 1

    window_indices = np.zeros(num_windows)
    mav_values = np.zeros(num_windows)
    rms_values = np.zeros(num_windows)

    for i in range(num_windows):
        start = i * step_size
        end = start + window_size
        window = signal[start:end]

        window_indices[i] = start + window_size // 2  # Center of window
        mav_values[i] = compute_mav(window)
        rms_values[i] = compute_rms(window)

    return window_indices, mav_values, rms_values


# ─────────────────────────── Visualization ───────────────────────────

def plot_feature_comparison(
    h_idx: np.ndarray, h_mav: np.ndarray, h_rms: np.ndarray,
    f_idx: np.ndarray, f_mav: np.ndarray, f_rms: np.ndarray,
    fs: float = 5000.0,
) -> None:
    """
    Generate a 2×2 subplot comparing MAV and RMS features between
    healthy and faulty signals. Includes separation analysis.
    """
    os.makedirs(PLOTS_DIR, exist_ok=True)

    # Convert sample indices to time
    h_time = h_idx / fs
    f_time = f_idx / fs

    # ── Compute separation metrics ──
    mav_sep = np.mean(f_mav) - np.mean(h_mav)
    rms_sep = np.mean(f_rms) - np.mean(h_rms)
    mav_sep_ratio = np.mean(f_mav) / np.mean(h_mav)
    rms_sep_ratio = np.mean(f_rms) / np.mean(h_rms)

    # ── Color Palette ──
    c_healthy = "#22c55e"    # Green
    c_faulty  = "#ef4444"    # Red
    c_bg      = "#0f172a"    # Slate-900
    c_panel   = "#1e293b"    # Slate-800
    c_text    = "#e2e8f0"    # Slate-200
    c_grid    = "#334155"    # Slate-700
    c_accent  = "#38bdf8"    # Sky-400

    fig, axes = plt.subplots(2, 2, figsize=(16, 10), facecolor=c_bg)
    fig.suptitle(
        "Edge AI Condition Monitoring — Feature Extraction Analysis",
        fontsize=16, fontweight="bold", color=c_text, y=0.96,
    )

    for ax in axes.flat:
        ax.set_facecolor(c_panel)
        ax.tick_params(colors=c_text, labelsize=9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        for spine in ax.spines.values():
            spine.set_color(c_grid)
        ax.grid(True, alpha=0.3, color=c_grid, linewidth=0.5)
        ax.xaxis.label.set_color(c_text)
        ax.yaxis.label.set_color(c_text)

    # ── [0,0] MAV Comparison ──
    ax0 = axes[0, 0]
    ax0.plot(h_time, h_mav, color=c_healthy, linewidth=1.2, alpha=0.85, label="Healthy")
    ax0.plot(f_time, f_mav, color=c_faulty, linewidth=1.2, alpha=0.85, label="Faulty")
    ax0.axhline(np.mean(h_mav), color=c_healthy, linestyle="--", alpha=0.5, linewidth=0.8)
    ax0.axhline(np.mean(f_mav), color=c_faulty, linestyle="--", alpha=0.5, linewidth=0.8)
    ax0.set_xlabel("Time (s)")
    ax0.set_ylabel("MAV (A)")
    ax0.set_title("Mean Absolute Value (MAV)", color=c_accent, fontsize=12, fontweight="bold")
    ax0.legend(facecolor=c_panel, edgecolor=c_grid, labelcolor=c_text, fontsize=9)

    # ── [0,1] RMS Comparison ──
    ax1 = axes[0, 1]
    ax1.plot(h_time, h_rms, color=c_healthy, linewidth=1.2, alpha=0.85, label="Healthy")
    ax1.plot(f_time, f_rms, color=c_faulty, linewidth=1.2, alpha=0.85, label="Faulty")
    ax1.axhline(np.mean(h_rms), color=c_healthy, linestyle="--", alpha=0.5, linewidth=0.8)
    ax1.axhline(np.mean(f_rms), color=c_faulty, linestyle="--", alpha=0.5, linewidth=0.8)
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("RMS (A)")
    ax1.set_title("Root Mean Square (RMS)", color=c_accent, fontsize=12, fontweight="bold")
    ax1.legend(facecolor=c_panel, edgecolor=c_grid, labelcolor=c_text, fontsize=9)

    # ── [1,0] Separation Bar Chart ──
    ax2 = axes[1, 0]
    features = ["MAV", "RMS"]
    healthy_means = [np.mean(h_mav), np.mean(h_rms)]
    faulty_means = [np.mean(f_mav), np.mean(f_rms)]

    x = np.arange(len(features))
    bar_width = 0.3

    bars_h = ax2.bar(x - bar_width/2, healthy_means, bar_width,
                     label="Healthy", color=c_healthy, alpha=0.85, edgecolor="white", linewidth=0.5)
    bars_f = ax2.bar(x + bar_width/2, faulty_means, bar_width,
                     label="Faulty", color=c_faulty, alpha=0.85, edgecolor="white", linewidth=0.5)

    # Add value labels
    for bar in bars_h:
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                 f"{bar.get_height():.3f}", ha="center", va="bottom",
                 color=c_text, fontsize=9, fontweight="bold")
    for bar in bars_f:
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                 f"{bar.get_height():.3f}", ha="center", va="bottom",
                 color=c_text, fontsize=9, fontweight="bold")

    ax2.set_xticks(x)
    ax2.set_xticklabels(features)
    ax2.set_ylabel("Mean Feature Value (A)")
    ax2.set_title("Feature Mean Comparison", color=c_accent, fontsize=12, fontweight="bold")
    ax2.legend(facecolor=c_panel, edgecolor=c_grid, labelcolor=c_text, fontsize=9)

    # ── [1,1] Separation Metrics ──
    ax3 = axes[1, 1]
    ax3.axis("off")

    metrics_text = (
        f"┌─────────────────────────────────────────┐\n"
        f"│     FEATURE SEPARATION ANALYSIS         │\n"
        f"├─────────────────────────────────────────┤\n"
        f"│                                         │\n"
        f"│  Window Size  : {WINDOW_SIZE} samples              │\n"
        f"│  Step Size    : {STEP_SIZE} samples               │\n"
        f"│  Overlap      : {100*(1 - STEP_SIZE/WINDOW_SIZE):.1f}%                      │\n"
        f"│                                         │\n"
        f"│  ── MAV ──                              │\n"
        f"│  Healthy mean : {np.mean(h_mav):.4f} A               │\n"
        f"│  Faulty  mean : {np.mean(f_mav):.4f} A               │\n"
        f"│  Abs. Δ       : {mav_sep:.4f} A               │\n"
        f"│  Ratio (F/H)  : {mav_sep_ratio:.2f}×                  │\n"
        f"│                                         │\n"
        f"│  ── RMS ──                              │\n"
        f"│  Healthy mean : {np.mean(h_rms):.4f} A               │\n"
        f"│  Faulty  mean : {np.mean(f_rms):.4f} A               │\n"
        f"│  Abs. Δ       : {rms_sep:.4f} A               │\n"
        f"│  Ratio (F/H)  : {rms_sep_ratio:.2f}×                  │\n"
        f"│                                         │\n"
        f"│  ▶ Winner: {'RMS' if rms_sep > mav_sep else 'MAV'}"
        f" (wider separation)        │\n"
        f"└─────────────────────────────────────────┘"
    )

    ax3.text(
        0.05, 0.95, metrics_text,
        transform=ax3.transAxes, fontsize=10, fontfamily="monospace",
        verticalalignment="top", color=c_text,
        bbox=dict(boxstyle="round,pad=0.5", facecolor=c_panel, edgecolor=c_grid, alpha=0.9),
    )

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(OUTPUT_PLOT, dpi=150, facecolor=c_bg, bbox_inches="tight")
    plt.close()

    file_size_kb = os.path.getsize(OUTPUT_PLOT) / 1024
    print(f"  ✓ Plot saved → {OUTPUT_PLOT}  ({file_size_kb:.1f} KB)")


# ─────────────────────────── Main Entry Point ───────────────────────────

def main() -> None:
    print("=" * 65)
    print("  Edge AI Condition Monitoring — Feature Extractor")
    print("=" * 65)
    print(f"  Window Size : {WINDOW_SIZE} samples")
    print(f"  Step Size   : {STEP_SIZE} samples")
    print(f"  Overlap     : {100*(1 - STEP_SIZE/WINDOW_SIZE):.1f}%")
    print("-" * 65)

    # ── Load Signals ──
    print("\n[1/4] Loading healthy baseline...")
    h_time, h_signal = load_signal(HEALTHY_CSV)
    print(f"      Loaded {len(h_signal):,} samples")

    print("[2/4] Loading faulty baseline...")
    f_time, f_signal = load_signal(FAULTY_CSV)
    print(f"      Loaded {len(f_signal):,} samples")

    # ── Extract Features ──
    print("\n[3/4] Extracting windowed features...")
    h_idx, h_mav, h_rms = extract_features(h_signal)
    f_idx, f_mav, f_rms = extract_features(f_signal)

    num_windows_h = len(h_mav)
    num_windows_f = len(f_mav)
    print(f"      Healthy: {num_windows_h} windows computed")
    print(f"      Faulty:  {num_windows_f} windows computed")

    # ── Print Numerical Summary ──
    print("\n" + "-" * 65)
    print("  Feature Statistics:")
    print(f"    {'':12s} {'MAV (A)':>12s}  {'RMS (A)':>12s}")
    print(f"    {'Healthy μ':12s} {np.mean(h_mav):12.6f}  {np.mean(h_rms):12.6f}")
    print(f"    {'Healthy σ':12s} {np.std(h_mav):12.6f}  {np.std(h_rms):12.6f}")
    print(f"    {'Faulty  μ':12s} {np.mean(f_mav):12.6f}  {np.mean(f_rms):12.6f}")
    print(f"    {'Faulty  σ':12s} {np.std(f_mav):12.6f}  {np.std(f_rms):12.6f}")
    print(f"    {'Δ (F-H)':12s} {np.mean(f_mav)-np.mean(h_mav):12.6f}  "
          f"{np.mean(f_rms)-np.mean(h_rms):12.6f}")
    print(f"    {'Ratio F/H':12s} {np.mean(f_mav)/np.mean(h_mav):12.2f}  "
          f"{np.mean(f_rms)/np.mean(h_rms):12.2f}")

    winner = "RMS" if (np.mean(f_rms) - np.mean(h_rms)) > (np.mean(f_mav) - np.mean(h_mav)) else "MAV"
    print(f"\n  ▶ Recommended Feature: {winner} (widest healthy↔faulty separation)")

    # ── Generate Plot ──
    print("\n[4/4] Generating comparison plot...")
    plot_feature_comparison(h_idx, h_mav, h_rms, f_idx, f_mav, f_rms)

    print("\n" + "=" * 65)
    print("  ✓ Feature extraction complete.")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
