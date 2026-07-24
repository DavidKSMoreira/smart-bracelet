#include <BMI160Gen.h>           // https://github.com/hanyazou/BMI160-Arduino
#include <Wire.h>
#include <math.h>
#include "dt_model.h"            // Arquivo gerado pelo micromlgen utilizando Random Forest

// Instância do modelo de Random Forest (conforme seu esqueleto)
Eloquent::ML::Port::DecisionTree clf;

// --- Configurações I2C para o ESP32 ---
const int i2c_addr = 0x68;  
const int sda_pin = 8;      
const int scl_pin = 9;      

// --- Pinos de Alerta ---
const int ALARM_PIN = 2; // Ajuste conforme o pino desejado na sua montagem

// ---------------------------------------------------------
// VARIÁVEIS DO FILTRO DE ORIENTAÇÃO (MADGWICK)
// ---------------------------------------------------------
const float deltat = 0.02f;                                      // 50Hz = 0.02 segundos
const float gyroMeasError = 3.14159265358979f * (5.0f / 180.0f); // 5 deg/s em rad/s
const float beta = 0.86602540378f * gyroMeasError;               

float SEq_1 = 1.0f, SEq_2 = 0.0f, SEq_3 = 0.0f, SEq_4 = 0.0f; 

// ---------------------------------------------------------
// VARIÁVEIS DO SISTEMA DE QUEDA E BUFFER
// ---------------------------------------------------------
double absolute_accel = 0;
bool queda_livre = false;
unsigned long lastUpdate = 0;

// Buffer circular de 2 segundos (100 amostras a 50Hz) focados nas características do filtro
#define WINDOW_SIZE 100 
float ta_buffer[WINDOW_SIZE];
float va_buffer[WINDOW_SIZE];
int buf_index = 0;

bool em_captura_pos_impacto = false;
int amostras_pos_impacto = 0;
const int ATRASO_AVALIACAO = 25; // Aguarda 0.5s após o impacto para rodar o ML

void setup() {
  Serial.begin(115200);
  while (!Serial);

  // --- Configuração do Alarme (do seu esqueleto) ---
  pinMode(ALARM_PIN, OUTPUT);
  digitalWrite(ALARM_PIN, LOW);

  Wire.begin(sda_pin, scl_pin); 
  
  if (!BMI160.begin(BMI160GenClass::I2C_MODE, i2c_addr)) { 
    Serial.println("Falha na inicializacao do BMI160!");
    while (1);
  }
  
  // Range de +-4g para aceleração e +-250dps para o giroscópio (requerido pelo filtro)
  BMI160.setAccelerometerRange(4);
  BMI160.setGyroRange(250);
  
  Serial.println("BMI160 inicializado! Iniciando filtro de orientacao e ML...");
  
  // Sinalização de inicialização pelo LED/Alarme
  digitalWrite(ALARM_PIN, HIGH); 
  delay(200); 
  digitalWrite(ALARM_PIN, LOW); 

  // Zera os buffers
  for(int i=0; i<WINDOW_SIZE; i++){
    ta_buffer[i] = 0.0f;
    va_buffer[i] = 0.0f;
  }
}

// ---------------------------------------------------------
// FUNÇÃO DE ATUALIZAÇÃO DO FILTRO MADGWICK
// ---------------------------------------------------------
void filterUpdate(float w_x, float w_y, float w_z, float a_x, float a_y, float a_z) {
    float norm;                                                 
    float SEqDot_omega_1, SEqDot_omega_2, SEqDot_omega_3, SEqDot_omega_4; 
    float f_1, f_2, f_3;                                          
    float J_11or24, J_12or23, J_13or22, J_14or21, J_32, J_33;     
    float SEqHatDot_1, SEqHatDot_2, SEqHatDot_3, SEqHatDot_4;     

    float halfSEq_1 = 0.5f * SEq_1;
    float halfSEq_2 = 0.5f * SEq_2;
    float halfSEq_3 = 0.5f * SEq_3;
    float halfSEq_4 = 0.5f * SEq_4;
    float twoSEq_1 = 2.0f * SEq_1;
    float twoSEq_2 = 2.0f * SEq_2;
    float twoSEq_3 = 2.0f * SEq_3;

    norm = sqrt(a_x * a_x + a_y * a_y + a_z * a_z);
    if (norm == 0.0f) return;
    a_x /= norm;
    a_y /= norm;
    a_z /= norm;

    f_1 = twoSEq_2 * SEq_4 - twoSEq_1 * SEq_3 - a_x;
    f_2 = twoSEq_1 * SEq_2 + twoSEq_3 * SEq_4 - a_y;
    f_3 = 1.0f - twoSEq_2 * SEq_2 - twoSEq_3 * SEq_3 - a_z;
    J_11or24 = twoSEq_3;                                                
    J_12or23 = 2.0f * SEq_4;
    J_13or22 = twoSEq_1;                                                
    J_14or21 = twoSEq_2;
    J_32 = 2.0f * J_14or21;                                             
    J_33 = 2.0f * J_11or24;                                             

    SEqHatDot_1 = J_14or21 * f_2 - J_11or24 * f_1;
    SEqHatDot_2 = J_12or23 * f_1 + J_13or22 * f_2 - J_32 * f_3;
    SEqHatDot_3 = J_12or23 * f_2 - J_33 * f_3 - J_13or22 * f_1;
    SEqHatDot_4 = J_14or21 * f_1 + J_11or24 * f_2;

    norm = sqrt(SEqHatDot_1 * SEqHatDot_1 + SEqHatDot_2 * SEqHatDot_2 + SEqHatDot_3 * SEqHatDot_3 + SEqHatDot_4 * SEqHatDot_4);
    SEqHatDot_1 /= norm;
    SEqHatDot_2 /= norm;
    SEqHatDot_3 /= norm;
    SEqHatDot_4 /= norm;

    SEqDot_omega_1 = -halfSEq_2 * w_x - halfSEq_3 * w_y - halfSEq_4 * w_z;
    SEqDot_omega_2 = halfSEq_1 * w_x + halfSEq_3 * w_z - halfSEq_4 * w_y;
    SEqDot_omega_3 = halfSEq_1 * w_y - halfSEq_2 * w_z + halfSEq_4 * w_x;
    SEqDot_omega_4 = halfSEq_1 * w_z + halfSEq_2 * w_y - halfSEq_3 * w_x;

    SEq_1 += (SEqDot_omega_1 - (beta * SEqHatDot_1)) * deltat;
    SEq_2 += (SEqDot_omega_2 - (beta * SEqHatDot_2)) * deltat;
    SEq_3 += (SEqDot_omega_3 - (beta * SEqHatDot_3)) * deltat;
    SEq_4 += (SEqDot_omega_4 - (beta * SEqHatDot_4)) * deltat;

    norm = sqrt(SEq_1 * SEq_1 + SEq_2 * SEq_2 + SEq_3 * SEq_3 + SEq_4 * SEq_4);
    SEq_1 /= norm;
    SEq_2 /= norm;
    SEq_3 /= norm;
    SEq_4 /= norm;
}

// ---------------------------------------------------------
// EXTRAÇÃO DE CARACTERÍSTICAS E CLASSIFICAÇÃO ML
// ---------------------------------------------------------
void classificarJanela() {
    float TA_sum=0, TA_max=0;
    float TV=0, TV_sum=0, TV_max=0;
    float VV=0, VV_sum=0, VV_max=0;
    float VD=0, VD_sum=0, VD_max=0;

    // Percorre o buffer temporal
    for(int i = 0; i < WINDOW_SIZE; i++) {
        int idx = (buf_index + i) % WINDOW_SIZE;
        float ta = ta_buffer[idx];
        float va = va_buffer[idx];

        // 1. Média e Máximo de TA
        TA_sum += ta;
        if(ta > TA_max) TA_max = ta;

        // 2. Integração no tempo (Velocidade - TV e VV)
        TV += ta * deltat;
        VV += va * deltat;

        TV_sum += TV;
        if(TV > TV_max) TV_max = TV;

        VV_sum += VV;
        if(VV > VV_max) VV_max = VV;

        // 3. Integração no tempo (Deslocamento - VD)
        VD += VV * deltat;
        
        VD_sum += VD;
        if(VD > VD_max) VD_max = VD;
    }

    float TA_mean = TA_sum / WINDOW_SIZE;
    float TV_mean = TV_sum / WINDOW_SIZE;
    float VV_mean = VV_sum / WINDOW_SIZE;
    float VD_mean = VD_sum / WINDOW_SIZE;

    // As 8 características alimentadas ao seu modelo (baseadas no script Python do filtro)
    float features[8] = {TA_mean, TA_max, TV_mean, TV_max, VV_mean, VV_max, VD_mean, VD_max};

    // === PREDIÇÃO COM RANDOM FOREST ===
    int prediction = clf.predict(features); 

    // Avalia o resultado 
    if(prediction == 1) { 
      Serial.println(">>> ALERTA: QUEDA DETECTADA (ML) <<<"); 
      digitalWrite(ALARM_PIN, HIGH); 
      delay(2000); // Mantém o alarme por 2 segundos 
      digitalWrite(ALARM_PIN, LOW); 
    } else { 
      Serial.println("ADL (Atividade Normal) - Falso positivo descartado"); 
    }
}

void loop() {
  unsigned long now = millis();
  // Garante taxa de amostragem exata de 50Hz (20ms) substituindo o delay(20)
  if (now - lastUpdate >= 20) { 
    lastUpdate = now;

    int gx, gy, gz; 
    int ax, ay, az; 
    
    BMI160.readGyro(gx, gy, gz);
    BMI160.readAccelerometer(ax, ay, az);
    
    // Converte os dados brutos para alimentar o filtro
    float rad_s_multiplier = (M_PI / 180.0f) / 131.2f;
    float w_x = gx * rad_s_multiplier;
    float w_y = gy * rad_s_multiplier;
    float w_z = gz * rad_s_multiplier;

    float ax_g = (float)ax / 8192.0f;
    float ay_g = (float)ay / 8192.0f;
    float az_g = (float)az / 8192.0f;

    // Atualiza a orientação no espaço 3D
    filterUpdate(w_x, w_y, w_z, ax_g, ay_g, az_g);

    // -------------------------------------------------------------
    // ENGENHARIA DE CARACTERÍSTICAS EM TEMPO REAL
    // -------------------------------------------------------------
    
    // Total Acceleration (TA) - Remoção da gravidade
    float accel_mag_ms2 = sqrt(ax_g*ax_g + ay_g*ay_g + az_g*az_g) * 9.81f;
    float current_TA = abs(accel_mag_ms2 - 9.81f);

    // Vertical Acceleration (VA) - Decomposição projetando no eixo do quaternion
    float grav_x = 2.0f * (SEq_2 * SEq_4 - SEq_1 * SEq_3);
    float grav_y = 2.0f * (SEq_1 * SEq_2 + SEq_3 * SEq_4);
    float grav_z = SEq_1 * SEq_1 - SEq_2 * SEq_2 - SEq_3 * SEq_3 + SEq_4 * SEq_4;

    float v_accel_g = (ax_g * grav_x + ay_g * grav_y + az_g * grav_z);
    float current_VA = abs(v_accel_g - 1.0f) * 9.81f; 

    // Guarda na matriz temporal (janelamento de 2s)
    ta_buffer[buf_index] = current_TA;
    va_buffer[buf_index] = current_VA;

    // -------------------------------------------------------------
    // GATILHO (Acorda o modelo ML apenas em eventos suspeitos)
    // -------------------------------------------------------------
    absolute_accel = sqrt(sq((double)ax) + sq((double)ay) + sq((double)az));
    
    if (absolute_accel < 4125) queda_livre = true; // Aproximadamente < 0.5g
    
    if (queda_livre && absolute_accel > 12375 && !em_captura_pos_impacto) { // Aproximadamente > 1.5g
        em_captura_pos_impacto = true;
        amostras_pos_impacto = 0;
        Serial.println("Impacto detectado! Aguardando estabilizacao (0.5s) para Random Forest...");
    }

    if (em_captura_pos_impacto) {
        amostras_pos_impacto++;
        
        // Aguarda estabilizar a pessoa no chão para classificar a janela temporal
        if (amostras_pos_impacto >= ATRASO_AVALIACAO) {
            classificarJanela();
            
            em_captura_pos_impacto = false;
            queda_livre = false;
        }
    }

    buf_index = (buf_index + 1) % WINDOW_SIZE;
  }
}