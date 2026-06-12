#!/usr/bin/env python3
"""
signal_simulator.py — Synthetic Waveform Generator for Edge AI Condition Monitoring

Generates two datasets mimicking a BLDC motor current sensor output:
  • Healthy Baseline:  Clean 50 Hz sine, 1.0 A amplitude, low-noise
  • Faulty  Baseline:  Elevated amplitude (1.8 A) + 3rd/5th/7th harmonics + high-noise
                        Simulates structural friction or electrical short conditions

Sampling: 5 kHz (Ts = 0.2 ms)
Duration: 2 seconds per dataset  →  10 000 samples each
Output:   data/healthy_baseline.csv, data/faulty_baseline.csv

Usage:
    python3 tools/signal_simulator.py
"""

import os
import sys
import numpy as np
import csv

# ─────────────────────────── Configuration ───────────────────────────

SAMPLING_RATE_HZ    = 5000          # 5 kHz ADC sampling rate
DURATION_SECONDS    = 2.0           # 2 seconds of data
FUNDAMENTAL_FREQ_HZ = 50.0         # 50 Hz mains / motor fundamental

# Healthy parameters
HEALTHY_AMPLITUDE   = 1.0           # Peak current (Amps)
HEALTHY_NOISE_STD   = 0.05          # Gaussian noise σ

# Faulty parameters
FAULTY_AMPLITUDE    = 1.8           # Elevated peak current
FAULTY_NOISE_STD    = 0.15          # Higher noise floor
FAULTY_HARMONICS    = {
    3: 0.25,                        # 3rd harmonic (150 Hz), 25% of fundamental
    5: 0.15,                        # 5th harmonic (250 Hz), 15%
    7: 0.10,                        # 7th harmonic (350 Hz), 10%
}

# Output paths (relative to project root)
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR     = os.path.join(PROJECT_ROOT, "data")

HEALTHY_CSV  = os.path.join(DATA_DIR, "healthy_baseline.csv")
FAULTY_CSV   = os.path.join(DATA_DIR, "faulty_baseline.csv")

# Reproducibility
RNG_SEED = 42


# ─────────────────────────── Core Generator ───────────────────────────

def generate_time_vector(fs: float, duration: float) -> np.ndarray:
    """Generate a time vector from 0 to duration at sampling rate fs."""
    num_samples = int(fs * duration)
    return np.linspace(0, duration, num_samples, endpoint=False)


def generate_healthy_signal(t: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """
    Generate a clean 50 Hz sinusoidal waveform with low Gaussian noise.

    Parameters
    ----------
    t   : Time vector (seconds)
    rng : NumPy random generator instance

    Returns
    -------
    signal : 1-D array of current values (Amps)
    """
    fundamental = HEALTHY_AMPLITUDE * np.sin(2 * np.pi * FUNDAMENTAL_FREQ_HZ * t)
    noise = rng.normal(0, HEALTHY_NOISE_STD, size=len(t))
    return fundamental + noise


def generate_faulty_signal(t: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """
    Generate a degraded waveform with elevated amplitude, harmonic distortion,
    and increased noise — simulating structural friction or electrical short.

    Parameters
    ----------
    t   : Time vector (seconds)
    rng : NumPy random generator instance

    Returns
    -------
    signal : 1-D array of current values (Amps)
    """
    fundamental = FAULTY_AMPLITUDE * np.sin(2 * np.pi * FUNDAMENTAL_FREQ_HZ * t)

    # Inject odd-order harmonics (common in non-linear motor faults)
    harmonics = np.zeros_like(t)
    for order, relative_amp in FAULTY_HARMONICS.items():
        harmonics += (FAULTY_AMPLITUDE * relative_amp) * np.sin(
            2 * np.pi * (FUNDAMENTAL_FREQ_HZ * order) * t
        )

    noise = rng.normal(0, FAULTY_NOISE_STD, size=len(t))
    return fundamental + harmonics + noise


# ─────────────────────────── CSV Writer ───────────────────────────

def save_to_csv(filepath: str, t: np.ndarray, signal: np.ndarray) -> None:
    """
    Write time and signal columns to a CSV file.

    Format:
        time_s, current_A
        0.0000, 0.0123
        ...
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time_s", "current_A"])
        for ts, val in zip(t, signal):
            writer.writerow([f"{ts:.6f}", f"{val:.6f}"])

    file_size_kb = os.path.getsize(filepath) / 1024
    print(f"  ✓ Saved {len(t):,} samples → {filepath}  ({file_size_kb:.1f} KB)")


# ─────────────────────────── Main Entry Point ───────────────────────────

def main() -> None:
    print("=" * 65)
    print("  Edge AI Condition Monitoring — Signal Simulator")
    print("=" * 65)
    print(f"  Sampling Rate : {SAMPLING_RATE_HZ:,} Hz")
    print(f"  Duration      : {DURATION_SECONDS} s")
    print(f"  Fundamental   : {FUNDAMENTAL_FREQ_HZ} Hz")
    print(f"  Total Samples : {int(SAMPLING_RATE_HZ * DURATION_SECONDS):,} per dataset")
    print("-" * 65)

    rng = np.random.default_rng(RNG_SEED)
    t = generate_time_vector(SAMPLING_RATE_HZ, DURATION_SECONDS)

    # ── Healthy Baseline ──
    print("\n[1/2] Generating Healthy Baseline...")
    print(f"      Amplitude = {HEALTHY_AMPLITUDE} A, Noise σ = {HEALTHY_NOISE_STD}")
    healthy = generate_healthy_signal(t, rng)
    save_to_csv(HEALTHY_CSV, t, healthy)

    # ── Faulty Baseline ──
    print("\n[2/2] Generating Faulty Baseline...")
    print(f"      Amplitude = {FAULTY_AMPLITUDE} A, Noise σ = {FAULTY_NOISE_STD}")
    print(f"      Harmonics : {FAULTY_HARMONICS}")
    faulty = generate_faulty_signal(t, rng)
    save_to_csv(FAULTY_CSV, t, faulty)

    # ── Summary Statistics ──
    print("\n" + "-" * 65)
    print("  Signal Statistics:")
    print(f"    Healthy │ mean={np.mean(healthy):+.4f} A  std={np.std(healthy):.4f} A  "
          f"peak={np.max(np.abs(healthy)):.4f} A")
    print(f"    Faulty  │ mean={np.mean(faulty):+.4f} A  std={np.std(faulty):.4f} A  "
          f"peak={np.max(np.abs(faulty)):.4f} A")
    print("=" * 65)
    print("  ✓ Signal simulation complete. Data ready for NanoEdge AI Studio.\n")


if __name__ == "__main__":
    main()
