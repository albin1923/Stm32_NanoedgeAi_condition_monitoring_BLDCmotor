/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : DATA LOGGER — STM32 NUCLEO-G474RE
  *
  *  Hardware:
  *    • MCU:    STM32G474RET6 (Cortex-M4F, 170 MHz)
  *    • Sensor: ACS724-50A on PB0 (ADC1_IN15), zero-current = 2.5V ≈ 3103 counts
  *    • Motor:  12V/10A BLDC via SimonK 30A ESC
  *    • UART:   LPUART1 (PA2/PA3) → ST-Link VCP, 115200 baud
  *
  *  Pipeline (Data Logger Mode):
  *    TIM2 (5 kHz TRGO) → ADC1 (12-bit, PB0) → DMA1_CH1 (Circular, 256 samples)
  *    → Print raw ADC values over UART for NanoEdge AI Studio data collection
  *
  *  NanoEdge AI functions are COMMENTED OUT until the library is ready.
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "NanoEdgeAI.h"
#include <stdio.h>
#include <string.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* ── Sensor / ADC Constants ── */
#define ADC_ZERO_POINT        3103U   /* ACS724 zero-current offset (2.5V on 3.3V/12-bit) */
#define DMA_BUFFER_SIZE       256U    /* Must match NEAI_INPUT_SIGNAL_LENGTH */
// #define LEARNING_ITERATIONS   70U     /* Number of learn() calls for baseline — disabled for data logger */

/* ── State Machine States (disabled for data logger) ── */
// #define STATE_IDLE            0U
// #define STATE_LEARNING        1U
// #define STATE_TRANSITION      2U
// #define STATE_DETECTION       3U

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

COM_InitTypeDef BspCOMInit;
ADC_HandleTypeDef hadc1;
DMA_HandleTypeDef hdma_adc1;

TIM_HandleTypeDef htim2;

/* USER CODE BEGIN PV */

/**
 * @brief Raw ADC DMA circular buffer — filled automatically by hardware.
 *        DMA fires HAL_ADC_ConvHalfCpltCallback when [0..127] is complete,
 *        and HAL_ADC_ConvCpltCallback when [128..255] is complete.
 */
static uint16_t adc_dma_buffer[DMA_BUFFER_SIZE];

/**
 * @brief Float buffer for NanoEdge AI input — AC-coupled (zero-mean).
 *        Size matches NEAI_INPUT_SIGNAL_LENGTH (256).
 */
static float ai_input_buffer[DMA_BUFFER_SIZE];

/**
 * @brief Volatile flags set by DMA ISR, polled in main loop.
 *        dma_half_cplt: first half [0..127] ready
 *        dma_full_cplt: second half [128..255] ready (full buffer available)
 */
static volatile uint8_t dma_half_cplt = 0;
static volatile uint8_t dma_full_cplt = 0;

/* ── State machine variables ── */
static uint16_t learn_count = 0;
static uint8_t similarity_score = 0;

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_DMA_Init(void);
static void MX_ADC1_Init(void);
static void MX_TIM2_Init(void);
/* USER CODE BEGIN PFP */
// static void CastBuffer_And_Normalize(void);   /* Disabled — data logger sends raw values */
// static uint8_t UART_GetChar(void);             /* Disabled — no state machine commands */
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* ═══════════════════════════════════════════════════════════════════════════
 *                         PRINTF RETARGETING
 *
 *  Routes printf() output to LPUART1 (ST-Link Virtual COM Port).
 *  This overrides the weak _write() syscall used by newlib-nano.
 * ═══════════════════════════════════════════════════════════════════════════ */
// extern UART_HandleTypeDef hlpuart1; // Not needed, using BSP handle!

int _write(int file, char *ptr, int len)
{
    (void)file;
    HAL_UART_Transmit(&hcom_uart[COM1], (uint8_t *)ptr, (uint16_t)len, HAL_MAX_DELAY);
    return len;
}

#if 0  /* ── Disabled for data logger mode ── */
/* ═══════════════════════════════════════════════════════════════════════════
 *                    BUFFER CAST & NORMALIZATION
 *
 *  Converts the full 256-element uint16_t DMA buffer into a float buffer
 *  suitable for NanoEdge AI. Subtracts the 3103 zero-point offset so the
 *  AI receives an AC waveform centered at 0, not a DC-biased signal.
 *
 *  Physics: ACS724 outputs 2.5V at zero current. On a 3.3V / 12-bit ADC:
 *           2.5 / 3.3 × 4095 ≈ 3103 counts
 * ═══════════════════════════════════════════════════════════════════════════ */
static void CastBuffer_And_Normalize(void)
{
    for (uint16_t i = 0; i < DMA_BUFFER_SIZE; i++)
    {
        ai_input_buffer[i] = (float)adc_dma_buffer[i] - (float)ADC_ZERO_POINT;
    }
}

/* ═══════════════════════════════════════════════════════════════════════════
 *                       UART SINGLE-CHAR POLLING
 *
 *  Non-blocking check for a single byte on LPUART1.
 *  Returns the character if available, or 0 if nothing received.
 * ═══════════════════════════════════════════════════════════════════════════ */
static uint8_t UART_GetChar(void)
{
    uint8_t ch = 0;
    if (HAL_UART_Receive(&hcom_uart[COM1], &ch, 1, 10) == HAL_OK)
    {
        return ch;
    }
    return 0;
}
#endif  /* Disabled for data logger mode */

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_DMA_Init();
  MX_ADC1_Init();
  MX_TIM2_Init();
  /* USER CODE BEGIN 2 */

  /* ── Initialize BSP Components ── */
  BSP_LED_Init(LED_GREEN);
  BSP_PB_Init(BUTTON_USER, BUTTON_MODE_EXTI);

  /* ── Initialize COM1 for BSP printf (optional, LPUART1 already handles it) ── */
  BspCOMInit.BaudRate   = 115200;
  BspCOMInit.WordLength = COM_WORDLENGTH_8B;
  BspCOMInit.StopBits   = COM_STOPBITS_1;
  BspCOMInit.Parity     = COM_PARITY_NONE;
  BspCOMInit.HwFlowCtl  = COM_HWCONTROL_NONE;
  if (BSP_COM_Init(COM1, &BspCOMInit) != BSP_ERROR_NONE)
  {
      Error_Handler();
  }

  /* ── ADC Calibration (recommended before first conversion on STM32G4) ── */
  if (HAL_ADCEx_Calibration_Start(&hadc1, ADC_SINGLE_ENDED) != HAL_OK)
  {
      Error_Handler();
  }

  /* ── NanoEdge AI Engine ── */
  enum neai_state neai_ret = neai_anomalydetection_init(false);
  if (neai_ret != NEAI_OK)
  {
      Error_Handler();
  }

  /* Banner REMOVED — NanoEdge AI Studio requires pure numeric output from byte zero */

  /* ──────────────────────────────────────────────────────────────────────
   *  Start the TIM2→ADC→DMA acquisition pipeline.
   *  DMA fills adc_dma_buffer[256] in circular mode.
   *  When full, HAL_ADC_ConvCpltCallback sets dma_full_cplt = 1.
   * ────────────────────────────────────────────────────────────────────── */

  /* Start ADC+DMA in circular mode (256 half-words) */
  HAL_ADC_Start_DMA(&hadc1, (uint32_t *)adc_dma_buffer, DMA_BUFFER_SIZE);

  /* Start TIM2 — TRGO update events begin triggering ADC at 5 kHz */
  HAL_TIM_Base_Start(&htim2);

  /* Status message REMOVED — NanoEdge AI Studio requires pure numeric output */

  /* USER CODE END 2 */

  /* Initialize led */
  BSP_LED_Init(LED_GREEN);

  /* Initialize USER push-button, will be used to trigger an interrupt each time it's pressed.*/
  BSP_PB_Init(BUTTON_USER, BUTTON_MODE_EXTI);

  /* Initialize COM1 port (115200, 8 bits (7-bit data + 1 stop bit), no parity */
  BspCOMInit.BaudRate   = 115200;
  BspCOMInit.WordLength = COM_WORDLENGTH_8B;
  BspCOMInit.StopBits   = COM_STOPBITS_1;
  BspCOMInit.Parity     = COM_PARITY_NONE;
  BspCOMInit.HwFlowCtl  = COM_HWCONTROL_NONE;
  if (BSP_COM_Init(COM1, &BspCOMInit) != BSP_ERROR_NONE)
  {
    Error_Handler();
  }

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */

        if (dma_full_cplt)
        {
            dma_full_cplt = 0;
            HAL_ADC_Stop_DMA(&hadc1); // Pause sensor

            // 1. Convert raw ADC data into floats for the AI
            for (int i = 0; i < 256; i++) {
                ai_input_buffer[i] = (float)adc_dma_buffer[i];
            }

            // 2. The AI State Machine
            if (learn_count < 12) {
                // Phase 1: Establish the Baseline
                neai_anomalydetection_learn(ai_input_buffer);
                learn_count++;
                printf("AI Learning Phase... %d/12\r\n", learn_count);
            }
            else {
                // Phase 2: Active Condition Monitoring
                neai_anomalydetection_detect(ai_input_buffer, &similarity_score);

                // Print the AI's confidence score!
                if (similarity_score > 80) {
                    printf("Motor Status: NORMAL (%d%% match)\r\n", similarity_score);
                } else {
                    printf("!! ANOMALY DETECTED !! (%d%% match)\r\n", similarity_score);
                }
            }

            HAL_ADC_Start_DMA(&hadc1, (uint32_t*)adc_dma_buffer, 256); // Resume sensor
        }

  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = RCC_PLLM_DIV4;
  RCC_OscInitStruct.PLL.PLLN = 85;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief ADC1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_ADC1_Init(void)
{

  /* USER CODE BEGIN ADC1_Init 0 */

  /* USER CODE END ADC1_Init 0 */

  ADC_MultiModeTypeDef multimode = {0};
  ADC_ChannelConfTypeDef sConfig = {0};

  /* USER CODE BEGIN ADC1_Init 1 */

  /* USER CODE END ADC1_Init 1 */

  /** Common config
  */
  hadc1.Instance = ADC1;
  hadc1.Init.ClockPrescaler = ADC_CLOCK_SYNC_PCLK_DIV4;
  hadc1.Init.Resolution = ADC_RESOLUTION_12B;
  hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc1.Init.GainCompensation = 0;
  hadc1.Init.ScanConvMode = ADC_SCAN_DISABLE;
  hadc1.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
  hadc1.Init.LowPowerAutoWait = DISABLE;
  hadc1.Init.ContinuousConvMode = DISABLE;
  hadc1.Init.NbrOfConversion = 1;
  hadc1.Init.DiscontinuousConvMode = DISABLE;
  hadc1.Init.ExternalTrigConv = ADC_EXTERNALTRIG_T2_TRGO;
  hadc1.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_RISING;
  hadc1.Init.DMAContinuousRequests = DISABLE;
  hadc1.Init.Overrun = ADC_OVR_DATA_PRESERVED;
  hadc1.Init.OversamplingMode = DISABLE;
  if (HAL_ADC_Init(&hadc1) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure the ADC multi-mode
  */
  multimode.Mode = ADC_MODE_INDEPENDENT;
  if (HAL_ADCEx_MultiModeConfigChannel(&hadc1, &multimode) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Regular Channel
  */
  sConfig.Channel = ADC_CHANNEL_15;
  sConfig.Rank = ADC_REGULAR_RANK_1;
  sConfig.SamplingTime = ADC_SAMPLETIME_2CYCLES_5;
  sConfig.SingleDiff = ADC_SINGLE_ENDED;
  sConfig.OffsetNumber = ADC_OFFSET_NONE;
  sConfig.Offset = 0;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN ADC1_Init 2 */

  /* USER CODE END ADC1_Init 2 */

}

/**
  * @brief TIM2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM2_Init(void)
{

  /* USER CODE BEGIN TIM2_Init 0 */

  /* USER CODE END TIM2_Init 0 */

  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  /* USER CODE BEGIN TIM2_Init 1 */

  /* USER CODE END TIM2_Init 1 */
  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 170-1;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 199;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim2) != HAL_OK)
  {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim2, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_UPDATE;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM2_Init 2 */

  /* USER CODE END TIM2_Init 2 */

}

/**
  * Enable DMA controller clock
  */
static void MX_DMA_Init(void)
{

  /* DMA controller clock enable */
  __HAL_RCC_DMAMUX1_CLK_ENABLE();
  __HAL_RCC_DMA1_CLK_ENABLE();

  /* DMA interrupt init */
  /* DMA1_Channel1_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(DMA1_Channel1_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(DMA1_Channel1_IRQn);

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOF_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

/* ═══════════════════════════════════════════════════════════════════════════
 *                      DMA INTERRUPT CALLBACKS
 *
 *  Called from DMA1_Channel1_IRQHandler → HAL_DMA_IRQHandler().
 *  RULE: Never call AI functions or printf inside ISRs — set a flag only.
 *        All heavy processing happens in the main while(1) loop.
 *
 *  DMA Circular Mode with 256-element buffer:
 *    • Half-Transfer (HT): elements [0..127] are stable, DMA fills [128..255]
 *    • Transfer-Complete (TC): elements [128..255] are stable, DMA refills [0..127]
 *
 *  For this pipeline we use the FULL buffer on TC, since NanoEdge AI expects
 *  256 contiguous samples. The HT callback is provided for future use
 *  (e.g., double-buffering or streaming partial results).
 * ═══════════════════════════════════════════════════════════════════════════ */

/**
 * @brief DMA Half-Transfer Complete callback.
 *        First 128 samples [0..127] are now stable.
 *        Sets flag for potential future use (partial processing).
 */
void HAL_ADC_ConvHalfCpltCallback(ADC_HandleTypeDef *hadc)
{
    if (hadc->Instance == ADC1)
    {
        dma_half_cplt = 1;
    }
}

/**
 * @brief DMA Transfer Complete callback.
 *        Full 256-sample buffer is now complete.
 *        Sets flag — main loop will copy, normalize, and run AI.
 *
 * @note  Timer is NOT stopped. DMA circular mode continuously overwrites
 *        the buffer. The main loop must process before the next TC fires,
 *        or data will be overwritten. At 5 kHz / 256 samples = ~51 ms
 *        per buffer, which is ample time for inference on Cortex-M4F.
 */
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
    if (hadc->Instance == ADC1)
    {
        dma_full_cplt = 1;
    }
}

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  __disable_irq();
  while (1)
  {
      /* Optionally toggle LED for visual error indication */
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  printf("Assert failed: %s line %lu\r\n", (char *)file, (unsigned long)line);
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
