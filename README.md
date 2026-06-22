# 🔧 STM32 NanoEdge AI — BLDC Motor Condition Monitoring

> Real-time anomaly detection on a Nucleo-G474RE using edge AI.  
> Learns normal motor behavior in 12 iterations, then actively monitors for faults — all on-device, no cloud required.

---

##  Overview

This project implements a **bare-metal edge AI condition monitoring system** for BLDC motors using an STM32G474RE microcontroller and STMicroelectronics' **NanoEdge AI Studio**.

An ACS724-50A Hall-effect current sensor captures the motor's current signature at 5 kHz. The STM32 samples this signal via a hardware-triggered ADC → DMA pipeline, feeds 256-sample windows into a trained anomaly detection model, and reports motor health over UART in real time.

### Key Features

-  **5 kHz deterministic sampling** — TIM2 TRGO → ADC1 → DMA, zero CPU overhead during acquisition
-  **On-device AI inference** — NanoEdge AI library runs anomaly detection on Cortex-M4F
-  **Two-phase state machine** — 12-iteration learning phase → continuous detection mode
-  **Python tooling** — serial data logger, feature extractor, and signal simulator

---

##  Hardware

| Component | Specification |
|-----------|---------------|
| **MCU** | STM32G474RET6 (Cortex-M4F, 170 MHz, FPU) |
| **Board** | NUCLEO-G474RE |
| **Sensor** | ACS724-50A Hall-effect current sensor |
| **ADC Input** | PB0 (ADC1 Channel 15) |
| **Sensor Output** | 2.5V at zero current ≈ 3103 ADC counts |
| **Motor** | 12V / 10A BLDC via SimonK 30A ESC |
| **UART** | LPUART1 (PA2/PA3) → ST-Link VCP, 115200 baud |

### Wiring

```
ACS724 VOUT ──→ PB0 (ADC1_IN15)
ACS724 VCC  ──→ 3.3V
ACS724 GND  ──→ GND
Motor Phase ──→ Through ACS724 sense path
```

---

##  Project Structure

```
Condition_Monitoring/
├── stm32cubemx/                  # ← The real firmware (build this!)
│   ├── Core/
│   │   ├── Inc/
│   │   │   ├── main.h            # HAL/BSP config headers
│   │   │   └── NanoEdgeAI.h      # NanoEdge AI API (from Studio)
│   │   └── Src/
│   │       └── main.c            # ★ Main firmware — AI state machine
│   ├── Drivers/                  # STM32 HAL & BSP drivers
│   ├── CMakeLists.txt            # Build config (links libneai.a)
│   ├── CMakePresets.json         # CMake presets for STM32
│   ├── libneai.a                 # NanoEdge AI compiled model
│   ├── stm32cubemx.ioc          # CubeMX project file
│   ├── STM32G474XX_FLASH.ld     # Linker script
│   └── startup_stm32g474xx.s    # Startup assembly
│
├── firmware/                     # Reference skeleton (mock HAL, not flashed)
│   └── Core/
│       ├── Inc/main.h            # Standalone config header
│       └── Src/main.c            # DSP functions & architecture reference
│
├── tools/                        # Python host-side utilities
│   ├── data_logger.py            # Serial capture → CSV for Studio
│   ├── feature_extractor.py      # MAV/RMS/FFT offline analysis
│   └── signal_simulator.py       # Synthetic test signal generator
│
├── data/                         # Captured training/test datasets
│   ├── healthy_baseline.csv
│   ├── abnormal.csv
│   ├── baseline.csv
│   └── faulty_baseline.csv
│
├── logger.py                     # Quick-start serial logger
└── README.md
```

---

## ⚙️ Firmware Architecture

### Signal Acquisition Pipeline

```
TIM2 (5 kHz TRGO)
    │
    ▼
ADC1 (12-bit, CH15/PB0)
    │
    ▼
DMA1 CH1 (256-sample buffer)
    │
    ▼
HAL_ADC_ConvCpltCallback()
    │  sets dma_full_cplt = 1
    ▼
Main Loop (while(1))
    │
    ├─ Stop DMA
    ├─ Convert uint16 → float
    ├─ AI Learn or Detect
    ├─ Print result via UART
    └─ Restart DMA
```

### AI State Machine

The firmware operates in two phases:

```c
if (learn_count < 12) {
    // Phase 1: Learning — build the baseline model
    neai_anomalydetection_learn(ai_input_buffer);
    printf("AI Learning Phase... %d/12\r\n", learn_count);
}
else {
    // Phase 2: Detection — monitor for anomalies
    neai_anomalydetection_detect(ai_input_buffer, &similarity_score);

    if (similarity_score > 80)
        printf("Motor Status: NORMAL (%d%% match)\r\n", similarity_score);
    else
        printf("!! ANOMALY DETECTED !! (%d%% match)\r\n", similarity_score);
}
```

**Phase 1 (Learning):** The first 12 DMA buffers train the on-device model to recognize "normal" motor current patterns.

**Phase 2 (Detection):** Every subsequent buffer is compared against the learned baseline. A similarity score below 80% triggers an anomaly alert.

---

##  Build & Flash

### Prerequisites

- [STM32CubeIDE](https://www.st.com/en/development-tools/stm32cubeide.html) or VS Code with [STM32 Extension](https://marketplace.visualstudio.com/items?itemName=stmicroelectronics.stm32-vscode-extension)
- [STM32CubeMX](https://www.st.com/en/development-tools/stm32cubemx.html) (for peripheral re-configuration)
- ARM GCC Toolchain (`arm-none-eabi-gcc`)
- CMake ≥ 3.22

### Build

```bash
cd stm32cubemx
mkdir -p build && cd build
cmake --preset Debug ..
cmake --build .
```

Or via VS Code: `Ctrl+Shift+P` → `STM32: Build`

### Flash

```bash
# Via ST-Link (OpenOCD or STM32CubeProgrammer)
STM32_Programmer_CLI -c port=SWD -d build/Condition_Monitoring.elf -s
```

Or via VS Code: `Ctrl+Shift+P` → `STM32: Flash`

### Verify Serial Output

```bash
# Linux
sudo screen /dev/ttyACM0 115200

# Expected output during learning:
# AI Learning Phase... 1/12
# AI Learning Phase... 2/12
# ...
# AI Learning Phase... 12/12

# Expected output during detection:
# Motor Status: NORMAL (95% match)
# Motor Status: NORMAL (92% match)
# !! ANOMALY DETECTED !! (34% match)
```

---

##  Python Tools

### Data Logger (`tools/data_logger.py`)

Captures raw ADC data from the STM32 serial port and saves to CSV for NanoEdge AI Studio training:

```bash
python tools/data_logger.py --port /dev/ttyACM0 --baud 115200 --output data/capture.csv
```

### Feature Extractor (`tools/feature_extractor.py`)

Offline DSP analysis — computes MAV, RMS, and FFT from captured CSV data:

```bash
python tools/feature_extractor.py --input data/healthy_baseline.csv
```

### Signal Simulator (`tools/signal_simulator.py`)

Generates synthetic motor current signals for testing without hardware:

```bash
python tools/signal_simulator.py --mode healthy --samples 5000
python tools/signal_simulator.py --mode faulty --samples 5000
```

---

##  NanoEdge AI Studio Workflow

1. **Collect Data** — Flash the data logger firmware, capture healthy & faulty motor data
2. **Import to Studio** — Load CSV files into NanoEdge AI Studio
3. **Benchmark** — Studio finds the optimal ML model for your sensor data
4. **Export Library** — Download `libneai.a` + `NanoEdgeAI.h` for your target MCU
5. **Deploy** — Drop files into `stm32cubemx/`, build, and flash

   <img width="1600" height="1000" alt="WhatsApp Image 2026-06-18 at 10 37 13 AM" src="https://github.com/user-attachments/assets/d43aa7eb-5b1f-4d28-bbe8-968e37efc18b" />
   <img width="1600" height="1000" alt="WhatsApp Image 2026-06-18 at 10 36 41 AM" src="https://github.com/user-attachments/assets/928f831f-bc66-4dcf-ad49-2c605630a913" />
   <img width="1600" height="1000" alt="WhatsApp Image 2026-06-18 at 10 36 11 AM" src="https://github.com/user-attachments/assets/4e34bd4c-bbef-4250-928c-c73a1ebd948d" />
   <img width="1600" height="1000" alt="WhatsApp Image 2026-06-15 at 4 18 41 PM" src="https://github.com/user-attachments/assets/025f637e-fdc5-4c88-a3ec-d986834fc799" />


The exported library provides three core functions:

```c
neai_anomalydetection_init(false);                         // Initialize (learn from scratch)
neai_anomalydetection_learn(float *input);                 // Train on normal data
neai_anomalydetection_detect(float *input, uint8_t *sim);  // Detect anomalies
```

---

##  ADC Configuration

| Parameter | Value |
|-----------|-------|
| Resolution | 12-bit (0–4095) |
| Clock | PCLK/4 |
| Trigger | TIM2 TRGO (Update Event) |
| Sampling Time | 2.5 cycles |
| DMA Mode | Circular → Stop/Restart per buffer |
| Buffer Size | 256 samples |
| Effective Rate | 5,000 Hz |

### Timer Calculation

```
f_sample = SYSCLK / (PSC + 1) / (ARR + 1)
         = 170 MHz / 170 / 200
         = 5,000 Hz
```

---

##  License

This project uses the NanoEdge AI library under STMicroelectronics' license terms.  
All other code is provided as-is for educational and prototyping purposes.

---

##  Author

**Albin** — [github.com/albin1923](https://github.com/albin1923)
