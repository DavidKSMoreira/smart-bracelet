#include <BMI160Gen.h>           // https://github.com/hanyazou/BMI160-Arduino
#include <Wire.h>
#include <math.h>
#include "rf_model.h"            // Arquivo gerado pelo micromlgen utilizando Árvore de Decisão

// --- Configurações I2C para o ESP32-C3 ---
const int i2c_addr = 0x68;  
const int sda_pin = 8;      
const int scl_pin = 9;      

// --- Configurações da Janela de Dados ---
// Adaptado para 450 amostras (9 segundos a 50Hz) para refletir a estrutura de treinamento
const int WINDOW_SIZE = 450; 
int sample_count = 0;

float x_buf[WINDOW_SIZE];
float y_buf[WINDOW_SIZE];
float z_buf[WINDOW_SIZE];

// --- Pinos de Alerta ---
const int ALARM_PIN = 2; // Ajuste conforme o pino desejado na sua montagem

void setup() {
  Serial.begin(115200);
  pinMode(ALARM_PIN, OUTPUT);
  digitalWrite(ALARM_PIN, LOW);

  Wire.begin(sda_pin, scl_pin); 
  
  if (!BMI160.begin(BMI160GenClass::I2C_MODE, i2c_addr)) { 
    Serial.println("Falha na inicializacao do BMI160!");
    while (1);
  }
  
  // Range de +-4g configurado para a conversão de unidades
  BMI160.setAccelerometerRange(4);
  Serial.println("BMI160 inicializado! Iniciando coleta para inferencia (Janelas de 9s)...");
  digitalWrite(ALARM_PIN, HIGH); //[cite: 2]
  delay(200); // Mantém o alarme por 2 segundos[cite: 2]
  digitalWrite(ALARM_PIN, LOW); //[cite: 2]
}

// Função para calcular Variância (Amostral)
float calculateVariance(float* array, int size, float mean) {
  float temp = 0;
  for(int i = 0; i < size; i++) {
    temp += (array[i] - mean) * (array[i] - mean);
  }
  return temp / (size - 1); // N-1 para variância amostral garantindo compatibilidade com ddof=1 do Pandas
}

// Função para extrair as 4 características de um eixo
void extractFeaturesForAxis(float* array, int size, float &max_val, float &min_val, float &mean_val, float &var_val) {
  max_val = array[0];
  min_val = array[0];
  float sum = 0;

  for(int i = 0; i < size; i++) {
    if(array[i] > max_val) max_val = array[i];
    if(array[i] < min_val) min_val = array[i];
    sum += array[i];
  }
  
  mean_val = sum / size;
  var_val = calculateVariance(array, size, mean_val);
}

void loop() {
  int ax, ay, az;
  
  // Lê os dados brutos do acelerômetro
  BMI160.readAccelerometer(ax, ay, az);

  // Converte para escala em m/s^2 (range de +-4g, 1g = 8192)
  float x = (ax / 8192.0) * 9.80665;
  float y = (ay / 8192.0) * 9.80665;
  float z = (az / 8192.0) * 9.80665;
  
  // Armazena a leitura atual no buffer correspondente à amostra
  x_buf[sample_count] = x;
  y_buf[sample_count] = y;
  z_buf[sample_count] = z;

  sample_count++;

  // Quando o buffer encher (passou 9 segundos / 450 amostras)[cite: 2]
  if(sample_count >= WINDOW_SIZE) { //[cite: 2]
    float features[12]; // Array para armazenar as 12 características FS-1[cite: 2]
    
    // Extrai características Eixo X[cite: 2]
    extractFeaturesForAxis(x_buf, WINDOW_SIZE, features[0], features[1], features[2], features[3]); //[cite: 2]
    // Extrai características Eixo Y[cite: 2]
    extractFeaturesForAxis(y_buf, WINDOW_SIZE, features[4], features[5], features[6], features[7]); //[cite: 2]
    // Extrai características Eixo Z[cite: 2]
    extractFeaturesForAxis(z_buf, WINDOW_SIZE, features[8], features[9], features[10], features[11]); //[cite: 2]

    // === ALTERAÇÃO AQUI ===
    // De: Eloquent::ML::Port::DecisionTree clf;[cite: 2]
    Eloquent::ML::Port::RandomForest clf;
    
    int prediction = clf.predict(features); //[cite: 2]

    // Avalia o resultado (1 para Queda, 0 para ADL)[cite: 2]
    if(prediction == 1) { //[cite: 2]
      Serial.println(">>> ALERTA: QUEDA DETECTADA (ML) <<<"); //[cite: 2]
      digitalWrite(ALARM_PIN, HIGH); //[cite: 2]
      delay(2000); // Mantém o alarme por 2 segundos[cite: 2]
      digitalWrite(ALARM_PIN, LOW); //[cite: 2]
    } else { //[cite: 2]
      Serial.println("ADL (Atividade Normal)"); //[cite: 2]
    }

    // Zera o contador para a próxima janela de 9 segundos[cite: 2]
    sample_count = 0; //[cite: 2]
  }

  // Delay de 20ms para manter a taxa de amostragem em ~50Hz (1000ms / 50 = 20ms)
  delay(20); 
}