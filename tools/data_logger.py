#!/usr/bin/env python3
"""
data_logger.py — Production-Grade Serial Data Acquisition for STM32 UART

Connects to the STM32G474RE Nucleo board over USB-UART (ST-Link VCP)
and logs incoming DSP + anomaly data to CSV files.

Expected UART format from firmware:
    MAV=0.1234,RMS=0.5678,SCORE=12,STATUS=NORMAL\r\n

Features:
    • Robust reconnection on USB disconnection
    • Malformed packet handling with error counters
    • Dual-mode logging: --mode healthy | faulty | live
    • Graceful shutdown on Ctrl+C
    • Timestamped CSV output with headers

Usage:
    python3 tools/data_logger.py --port /dev/ttyACM0 --baud 115200 --mode healthy
    python3 tools/data_logger.py --port /dev/ttyACM0 --output data/custom_log.csv

Dependencies:
    pip install pyserial
"""

import os
import sys
import csv
import time
import signal
import argparse
import datetime
from typing import Optional

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("ERROR: pyserial is required. Install it with:")
    print("       pip install pyserial")
    sys.exit(1)


# ─────────────────────── Configuration ───────────────────────────

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR     = os.path.join(PROJECT_ROOT, "data")

DEFAULT_PORT = "/dev/ttyACM0"
DEFAULT_BAUD = 115200
DEFAULT_MODE = "live"

# Reconnection
MAX_RECONNECT_ATTEMPTS = 10
RECONNECT_DELAY_SEC    = 2.0

# Packet validation
EXPECTED_FIELDS = {"MAV", "RMS", "SCORE", "STATUS"}

# CSV headers
CSV_HEADERS = ["timestamp", "elapsed_s", "mav", "rms", "score", "status"]


# ─────────────────────── Signal Handler ───────────────────────────

_running = True

def _signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    global _running
    _running = False
    print("\n  ⏹  Shutdown signal received. Finishing current write...")


# ─────────────────────── Packet Parser ───────────────────────────

def parse_uart_packet(line: str) -> Optional[dict]:
    """
    Parse a single UART line from the STM32 firmware.

    Expected format:
        MAV=0.1234,RMS=0.5678,SCORE=12,STATUS=NORMAL

    Returns
    -------
    dict with keys: mav (float), rms (float), score (int), status (str)
    None if the packet is malformed.
    """
    try:
        line = line.strip()
        if not line:
            return None

        fields = {}
        for pair in line.split(","):
            if "=" not in pair:
                return None
            key, value = pair.split("=", 1)
            fields[key.strip().upper()] = value.strip()

        # Validate all expected fields are present
        if not EXPECTED_FIELDS.issubset(fields.keys()):
            return None

        return {
            "mav":    float(fields["MAV"]),
            "rms":    float(fields["RMS"]),
            "score":  int(fields["SCORE"]),
            "status": fields["STATUS"],
        }

    except (ValueError, KeyError, AttributeError):
        return None


# ─────────────────────── Serial Connection ───────────────────────────

def open_serial(port: str, baud: int) -> Optional[serial.Serial]:
    """
    Open a serial connection with error handling.

    Returns
    -------
    serial.Serial instance or None on failure.
    """
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0,        # Read timeout (seconds)
            write_timeout=1.0,
        )
        # Flush any stale data in the buffer
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        return ser

    except serial.SerialException as e:
        print(f"  ✗ Serial error: {e}")
        return None
    except PermissionError:
        print(f"  ✗ Permission denied on {port}.")
        print(f"    Try: sudo chmod 666 {port}")
        print(f"    Or add yourself to the dialout group: sudo usermod -aG dialout $USER")
        return None


def list_available_ports():
    """Print all available serial ports."""
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("  ⚠  No serial ports detected.")
    else:
        print("  Available serial ports:")
        for p in ports:
            print(f"    • {p.device}  [{p.description}]")


# ─────────────────────── CSV Writer ───────────────────────────

class CSVLogger:
    """Thread-safe CSV logger with automatic header management."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.file = None
        self.writer = None
        self.row_count = 0
        self._open()

    def _open(self):
        """Open or create the CSV file."""
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)

        file_exists = os.path.isfile(self.filepath) and os.path.getsize(self.filepath) > 0

        self.file = open(self.filepath, "a", newline="")
        self.writer = csv.writer(self.file)

        if not file_exists:
            self.writer.writerow(CSV_HEADERS)
            self.file.flush()

    def write_row(self, timestamp: str, elapsed: float, data: dict):
        """Append a parsed data row to the CSV."""
        if self.writer is None:
            return

        self.writer.writerow([
            timestamp,
            f"{elapsed:.3f}",
            f"{data['mav']:.6f}",
            f"{data['rms']:.6f}",
            data["score"],
            data["status"],
        ])
        self.row_count += 1

        # Flush every 10 rows for reliability
        if self.row_count % 10 == 0:
            self.file.flush()

    def close(self):
        """Flush and close the CSV file."""
        if self.file:
            self.file.flush()
            self.file.close()
            self.file = None
            self.writer = None


# ─────────────────────── Main Acquisition Loop ───────────────────────────

def resolve_output_path(mode: str, output: Optional[str]) -> str:
    """Determine the output CSV filepath based on mode and --output flag."""
    if output:
        if not os.path.isabs(output):
            return os.path.join(PROJECT_ROOT, output)
        return output

    mode_map = {
        "healthy": os.path.join(DATA_DIR, "healthy_baseline.csv"),
        "faulty":  os.path.join(DATA_DIR, "faulty_baseline.csv"),
        "live":    os.path.join(DATA_DIR, f"live_capture_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv"),
    }
    return mode_map.get(mode, mode_map["live"])


def run_acquisition(port: str, baud: int, output_path: str):
    """
    Main serial acquisition loop with reconnection logic.

    Reads lines from the STM32 UART, parses them, and logs to CSV.
    Handles disconnections gracefully with automatic reconnection.
    """
    global _running

    print(f"\n  Serial Port  : {port}")
    print(f"  Baud Rate    : {baud}")
    print(f"  Output File  : {output_path}")
    print(f"  Press Ctrl+C to stop.\n")

    logger = CSVLogger(output_path)
    start_time = time.monotonic()

    # Statistics
    total_packets    = 0
    valid_packets    = 0
    malformed_packets = 0
    anomalies_detected = 0

    ser = None
    reconnect_count = 0

    while _running:
        # ── Connect / Reconnect ──
        if ser is None or not ser.is_open:
            print(f"  🔌 Connecting to {port}...")
            ser = open_serial(port, baud)

            if ser is None:
                reconnect_count += 1
                if reconnect_count > MAX_RECONNECT_ATTEMPTS:
                    print(f"\n  ✗ Max reconnection attempts ({MAX_RECONNECT_ATTEMPTS}) exceeded.")
                    list_available_ports()
                    break

                print(f"  ⏳ Retry {reconnect_count}/{MAX_RECONNECT_ATTEMPTS} "
                      f"in {RECONNECT_DELAY_SEC}s...")
                time.sleep(RECONNECT_DELAY_SEC)
                continue

            reconnect_count = 0
            print(f"  ✓ Connected to {port}")

        # ── Read Line ──
        try:
            raw_line = ser.readline()
            if not raw_line:
                continue  # Timeout, no data

            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            total_packets += 1

            # ── Parse ──
            data = parse_uart_packet(line)

            if data is None:
                malformed_packets += 1
                if malformed_packets <= 5:
                    print(f"  ⚠  Malformed packet #{malformed_packets}: {line[:80]}")
                elif malformed_packets == 6:
                    print(f"  ⚠  Suppressing further malformed packet warnings...")
                continue

            valid_packets += 1
            elapsed = time.monotonic() - start_time
            timestamp = datetime.datetime.now().isoformat(timespec="milliseconds")

            # ── Log to CSV ──
            logger.write_row(timestamp, elapsed, data)

            # ── Track Anomalies ──
            if data["status"] == "ANOMALY":
                anomalies_detected += 1

            # ── Live Console Output ──
            status_icon = "🔴" if data["status"] == "ANOMALY" else "🟢"
            if valid_packets % 10 == 1 or data["status"] == "ANOMALY":
                print(f"  {status_icon} [{valid_packets:>6}] "
                      f"MAV={data['mav']:.4f}  RMS={data['rms']:.4f}  "
                      f"SCORE={data['score']:>3}  {data['status']}")

        except serial.SerialException as e:
            print(f"\n  ✗ Serial error: {e}")
            print(f"  🔌 Device disconnected. Attempting reconnection...")
            if ser:
                try:
                    ser.close()
                except Exception:
                    pass
            ser = None
            continue

        except UnicodeDecodeError:
            malformed_packets += 1
            continue

    # ── Shutdown ──
    print("\n" + "─" * 55)
    print("  Session Summary:")
    print(f"    Total Packets     : {total_packets:,}")
    print(f"    Valid Packets     : {valid_packets:,}")
    print(f"    Malformed Packets : {malformed_packets:,}")
    print(f"    Anomalies         : {anomalies_detected:,}")
    print(f"    Duration          : {time.monotonic() - start_time:.1f}s")
    print(f"    Output File       : {output_path}")
    print(f"    Rows Written      : {logger.row_count:,}")
    print("─" * 55)

    logger.close()

    if ser and ser.is_open:
        ser.close()
        print("  ✓ Serial port closed.")

    print("  ✓ Data logger shutdown complete.\n")


# ─────────────────────── CLI Entry Point ───────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Edge AI Condition Monitoring — Serial Data Logger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 data_logger.py --port /dev/ttyACM0 --mode healthy\n"
            "  python3 data_logger.py --port /dev/ttyACM0 --mode faulty\n"
            "  python3 data_logger.py --port COM3 --baud 115200 --output data/test.csv\n"
        ),
    )

    parser.add_argument(
        "--port", type=str, default=DEFAULT_PORT,
        help=f"Serial port device (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--baud", type=int, default=DEFAULT_BAUD,
        help=f"Baud rate (default: {DEFAULT_BAUD})",
    )
    parser.add_argument(
        "--mode", type=str, default=DEFAULT_MODE,
        choices=["healthy", "faulty", "live"],
        help="Logging mode — determines output filename (default: live)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Custom output CSV path (overrides --mode filename)",
    )
    parser.add_argument(
        "--list-ports", action="store_true",
        help="List available serial ports and exit",
    )

    args = parser.parse_args()

    print("=" * 55)
    print("  Edge AI Condition Monitoring — Data Logger")
    print("=" * 55)

    if args.list_ports:
        list_available_ports()
        return

    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    output_path = resolve_output_path(args.mode, args.output)
    run_acquisition(args.port, args.baud, output_path)


if __name__ == "__main__":
    main()
