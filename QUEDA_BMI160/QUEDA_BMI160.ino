// Código Corrigido (sketch_jul27a.ino)

#include <Wire.h>
#include "DFRobot_BMI160.h"

// Instância do sensor BMI160
DFRobot_BMI160 bmi160;

// -- Configurações de Pinos e Detecção --
const int INTERRUPT_PIN = 0;
volatile bool fallDetectedFlag = false;
const float FALL_THRESHOLD_G = 0.4;
const float IMPACT_THRESHOLD_G = 2.2;
const uint8_t FALL_DURATION_MS = 20;

void ICACHE_RAM_ATTR fallInterruptRoutine() {
  fallDetectedFlag = true;
}

/**
 * @brief Configura a interrupção de Baixa Gravidade (Low-G) no BMI160
 * VERSÃO CORRIGIDA: Adiciona o 4º argumento 'bmi160.Obmi160' nas chamadas setRegs.
 */
void setupLowGInterrupt() {
  Serial.println("Configurando interrupcao de Baixa-G (Low-G)...");

  // Limiar (Threshold)
  uint8_t low_th = (uint8_t)(FALL_THRESHOLD_G * 1000 / 7.81);
  bmi160.setRegs(BMI160_INT_LOWHIGH_4_ADDR, &low_th, 1, bmi160.Obmi160);

  // Duração (Duration)
  uint8_t low_dur = (uint8_t)((FALL_DURATION_MS / 2.5) - 1);
  bmi160.setRegs(BMI160_INT_LOWHIGH_3_ADDR, &low_dur, 1, bmi160.Obmi160);

  // Modo (Histerese + soma de eixos)
  uint8_t low_mode = 0b00001001;
  bmi160.setRegs(BMI160_INT_LOWHIGH_2_ADDR, &low_mode, 1, bmi160.Obmi160);

  // Habilitar a interrupção de Low-G
  uint8_t int_en_1 = 0b00001000;
  bmi160.setRegs(BMI160_INT_ENABLE_1_ADDR, &int_en_1, 1, bmi160.Obmi160);

  // Mapear a interrupção para o pino INT1
  uint8_t int_map_0 = 0b00000001;
  bmi160.setRegs(BMI160_INT_MAP_0_ADDR, &int_map_0, 1, bmi160.Obmi160);

  // Configurar o comportamento do pino INT1 (output, active high, edge)
  uint8_t int_out_ctrl = 0b00001010;
  bmi160.setRegs(BMI160_INT_OUT_CTRL_ADDR, &int_out_ctrl, 1, bmi160.Obmi160);

  // Configurar interrupção como não-travada (non-latched)
  uint8_t int_latch = 0b00000000;
  bmi160.setRegs(BMI160_INT_LATCH_ADDR, &int_latch, 1, bmi160.Obmi160);
  
  Serial.println("Interrupcao Low-G configurada!");
}


void setup() {
  Serial.begin(115200);
  while (!Serial);

  Wire.begin(8, 9);
  
  if (bmi160.I2cInit() != BMI160_OK) {
    Serial.println("Falha ao inicializar o BMI160!");
    while (1);
  }
  Serial.println("BMI160 inicializado com sucesso!");

  setupLowGInterrupt();

  pinMode(INTERRUPT_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(INTERRUPT_PIN), fallInterruptRoutine, RISING);
  
  Serial.println("\nSistema pronto. Aguardando deteccao de queda...");
}


void loop() {
  if (fallDetectedFlag) {
    Serial.println("-------------------------------------------");
    Serial.println("EVENTO DE QUEDA LIVRE DETECTADO (LOW-G)!");
    Serial.println("Verificando impacto nos proximos 500ms...");

    bool impactConfirmed = false;
    unsigned long impactCheckStartTime = millis();

    while (millis() - impactCheckStartTime < 500) {
      int16_t accelData[3];
      bmi160.getAccelData(accelData);

      float ax = accelData[0] / 16384.0;
      float ay = accelData[1] / 16384.0;
      float az = accelData[2] / 16384.0;

      float resultant_g = sqrt(pow(ax, 2) + pow(ay, 2) + pow(az, 2));
      
      Serial.print("Magnitude: ");
      Serial.print(resultant_g, 2);
      Serial.println(" g");
      
      if (resultant_g > IMPACT_THRESHOLD_G) {
        Serial.println("\n>> IMPACTO CONFIRMADO! <<");
        impactConfirmed = true;
        break;
      }
      delay(10);
    }

    if (impactConfirmed) {
      Serial.println("!! ALERTA: QUEDA DETECTADA E CONFIRMADA !!");
    } else {
      Serial.println(">> Impacto nao detectado. Alarme falso.");
    }

    Serial.println("-------------------------------------------\n");
    
    fallDetectedFlag = false;
  }
  
  delay(50); 
}