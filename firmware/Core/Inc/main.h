/**
 ******************************************************************************
 * @file    main.h
 * @brief   Buffer sizes, flags, and macro configurations for
 *          Edge AI Condition Monitoring — STM32G474RE
 ******************************************************************************
 *
 * Target MCU   : STM32G474RET6 (Cortex-M4F, 170 MHz)
 * Board        : NUCLEO-G474RE
 * ADC Config   : 12-bit, TIM2-triggered, DMA Circular
 * ML Framework : NanoEdge AI Studio (static library)
 *
 ******************************************************************************
 */

#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

/* ─────────────────────── Includes ─────────────────────── */
#include <stdint.h>
#include <string.h>
#include <stdio.h>

/* Uncomment when building with real HAL drivers */
// #include "stm32g4xx_hal.h"

/* Uncomment when CMSIS-DSP library is linked */
// #include "arm_math.h"

/* ─────────────────────── ADC / DMA Configuration ─────────────────────── */

/**
 * @brief Number of samples in ONE HALF of the double buffer.
 *        Each half is processed independently while DMA fills the other.
 */
#define ADC_HALF_BUFFER_SIZE     512U

/**
 * @brief Total raw ADC buffer size (double-buffered).
 *        DMA fills this array in circular mode: [0..511] then [512..1023] repeat.
 */
#define ADC_BUFFER_SIZE          (ADC_HALF_BUFFER_SIZE * 2U)    /* 1024 */

/**
 * @brief ADC resolution in bits.
 */
#define ADC_RESOLUTION_BITS      12U

/**
 * @brief Maximum raw ADC count (2^12 - 1 = 4095).
 */
#define ADC_MAX_COUNT            ((1U << ADC_RESOLUTION_BITS) - 1U)   /* 4095 */

/**
 * @brief Reference voltage in volts.
 */
#define VREF                     3.3f

/**
 * @brief Conversion factor: raw ADC count → voltage.
 *        V = raw * (VREF / ADC_MAX_COUNT)
 */
#define ADC_TO_VOLTAGE(raw)      ((float)(raw) * (VREF / (float)ADC_MAX_COUNT))

/* ─────────────────────── Sampling Configuration ─────────────────────── */

/**
 * @brief Target ADC sampling rate in Hz.
 *        Achieved via TIM2: SYSCLK / (PSC+1) / (ARR+1)
 *        e.g., 170 MHz / 1 / 34000 = 5000 Hz
 */
#define SAMPLING_RATE_HZ         5000U

/**
 * @brief TIM2 prescaler value (PSC register).
 */
#define TIM2_PRESCALER           0U      /* No prescaling: 170 MHz */

/**
 * @brief TIM2 auto-reload value (ARR register).
 *        170,000,000 / (0+1) / 34000 = 5000 Hz
 */
#define TIM2_PERIOD              33999U  /* ARR = 34000 - 1 */

/* ─────────────────────── Processing Window ─────────────────────── */

/**
 * @brief Number of samples in the feature extraction window.
 *        Matches ADC_HALF_BUFFER_SIZE for direct half-buffer processing.
 */
#define FEATURE_WINDOW_SIZE      ADC_HALF_BUFFER_SIZE   /* 512 */

/* ─────────────────────── UART Configuration ─────────────────────── */

/**
 * @brief UART baud rate for debug output and data transmission.
 */
#define UART_BAUD_RATE           115200U

/**
 * @brief Maximum UART transmit buffer size (bytes).
 */
#define UART_TX_BUFFER_SIZE      256U

/* ─────────────────────── NanoEdge AI ─────────────────────── */

/**
 * @brief Number of input features expected by the NanoEdge AI model.
 *        This value is set by NanoEdge AI Studio during library generation.
 *        Update this when replacing stubs with the actual library.
 */
#define NEAI_INPUT_SIZE          FEATURE_WINDOW_SIZE     /* 512 */

/**
 * @brief Anomaly detection threshold.
 *        Values above this from neai_anomaly_detection_detect() are anomalous.
 *        Tune this after training in NanoEdge AI Studio.
 */
#define NEAI_ANOMALY_THRESHOLD   80U

/* ─────────────────────── Status Flags ─────────────────────── */

/**
 * @brief Classification result codes from the inference engine.
 */
typedef enum {
    STATUS_NORMAL   = 0x00,     /**< Operating within healthy baseline */
    STATUS_ANOMALY  = 0x01,     /**< Anomaly detected — investigate */
    STATUS_ERROR    = 0xFF,     /**< Inference error or uninitialized */
} system_status_t;

/* ─────────────────────── Global Flags (extern) ─────────────────────── */

/**
 * @brief Non-blocking flag set by DMA ISR, cleared by main loop.
 *        0 = no new data, 1 = half-buffer ready for processing.
 */
extern volatile uint8_t  data_ready_flag;

/**
 * @brief Offset into raw_adc_buffer[] indicating which half is ready.
 *        Set by ISR: 0 (first half) or ADC_HALF_BUFFER_SIZE (second half).
 */
extern volatile uint16_t buffer_offset;

/* ─────────────────────── Function Prototypes ─────────────────────── */

void SystemClock_Config(void);
void MX_GPIO_Init(void);
void MX_DMA_Init(void);
void MX_ADC1_Init(void);
void MX_TIM2_Init(void);
void MX_USART2_UART_Init(void);

void DSP_ConvertToVoltage(const uint16_t *raw, float *voltage, uint16_t length);
float DSP_ComputeMAV(const float *data, uint16_t length);
float DSP_ComputeRMS(const float *data, uint16_t length);

void NEAI_Init(void);
uint8_t NEAI_Detect(float *input_buffer);

void UART_TransmitResults(float mav, float rms, uint8_t anomaly_score);

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
