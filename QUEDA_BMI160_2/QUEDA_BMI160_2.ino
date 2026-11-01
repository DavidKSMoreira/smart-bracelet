#include <BMI160Gen.h>
#include <Wire.h>
#include <math.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiUdp.h>
#include "dt_model.h"

// Instância do classificador de árvore de decisão (definido em dt_model.h)
Eloquent::ML::Port::DecisionTree clf;

// Credenciais da rede Wi-Fi e identificação do dispositivo
const char* WIFI_SSID     = "SSID";
const char* WIFI_PASSWORD = "SENHA";
const char* ESP_ID        = "ESP_SALA_01";
const char* ESP_API_KEY   = "simposio-bmi160-key";

// Endereço do servidor HTTP e porta de descoberta automática via UDP
String serverIp = "192.168.0.36";
const int serverPort = 5000;
const int udpDiscoveryPort = 5005;
WiFiUDP udp;

// Controle de envio periódico de presença (heartbeat a cada 10s)
unsigned long lastHeartbeat = 0;
const unsigned long HEARTBEAT_INTERVAL = 10000;

// Pinos e endereço I2C para comunicação com o sensor BMI160
const int i2c_addr = 0x68;  
const int sda_pin = 8;      
const int scl_pin = 9;      

// Pino de acionamento do buzzer passivo
const int ALARM_PIN = 1;

// Gera sinal sonoro de 2.5kHz no buzzer passivo pelo tempo especificado (em ms)
void acionarAlarme(int duracaoMs) {
  unsigned long inicio = millis();
  while (millis() - inicio < (unsigned long)duracaoMs) {
    digitalWrite(ALARM_PIN, HIGH);
    delayMicroseconds(200);
    digitalWrite(ALARM_PIN, LOW);
    delayMicroseconds(200);
  }
  digitalWrite(ALARM_PIN, LOW);
}

// Constantes e quatérnion de estado do filtro de orientação Madgwick (50Hz -> dt = 0.02s)
const float deltat = 0.02f;
const float gyroMeasError = 3.14159265358979f * (5.0f / 180.0f);
const float beta = 0.86602540378f * gyroMeasError;               

float SEq_1 = 1.0f, SEq_2 = 0.0f, SEq_3 = 0.0f, SEq_4 = 0.0f; 

// Variáveis de controle da amostragem e dos estágios de queda
double absolute_accel = 0;
bool queda_livre = false;
unsigned long lastUpdate = 0;

// Buffer circular para armazenar os últimos 2 segundos (100 amostras a 50Hz)
#define WINDOW_SIZE 100 
float ta_buffer[WINDOW_SIZE];
float va_buffer[WINDOW_SIZE];
int buf_index = 0;

// Controle da janela de estabilização pós-impacto (25 amostras = 0.5s)
bool em_captura_pos_impacto = false;
int amostras_pos_impacto = 0;
const int ATRASO_AVALIACAO = 25;

// Localiza automaticamente o IP do servidor na rede local via pacote UDP broadcast
void descobrirServidorNaRede() {
  if (WiFi.status() != WL_CONNECTED) return;

  udp.begin(udpDiscoveryPort);
  IPAddress broadcastIp(255, 255, 255, 255);
  const char* msg = "DISCOVER_PULSEIRA_SERVER";

  // Envia pacote de busca para todos os dispositivos da sub-rede
  udp.beginPacket(broadcastIp, udpDiscoveryPort);
  udp.write((const uint8_t*)msg, strlen(msg));
  udp.endPacket();

  // Aguarda até 600ms pela resposta do servidor Flask
  unsigned long inicio = millis();
  while (millis() - inicio < 600) {
    int packetSize = udp.parsePacket();
    if (packetSize) {
      char buf[64];
      int len = udp.read(buf, sizeof(buf) - 1);
      if (len > 0) buf[len] = '\0';
      String resposta = String(buf);
      if (resposta.startsWith("PULSEIRA_SERVER_OK")) {
        serverIp = udp.remoteIP().toString();
        Serial.print("Servidor descoberto automaticamente em: ");
        Serial.println(serverIp);
        break;
      }
    }
    delay(10);
  }
  udp.stop();
}

// Conecta ao Wi-Fi e sinaliza a conexão com 3 bips no buzzer
void conectarWiFiBateria() {
  WiFi.mode(WIFI_STA);
  WiFi.setTxPower(WIFI_POWER_11dBm);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Conectando ao Wi-Fi ");
  Serial.print(WIFI_SSID);

  unsigned long inicio = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - inicio) < 8000) {
    delay(250);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWi-Fi conectado! IP da Pulseira: " + WiFi.localIP().toString());
    descobrirServidorNaRede();

    // Sinalização sonora de conexão Wi-Fi estabelecida (3 bips rápidos)
    for (int i = 0; i < 3; i++) {
      acionarAlarme(120);
      delay(100);
    }
  } else {
    Serial.println("\nProsseguindo em modo offline (tentara reconectar em background).");
  }
}

// Envia o estado atual (queda confirmada ou sinal de presença) via HTTP POST para a rota /dados
void enviarEventoServidor(bool quedaDetectada) {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    return;
  }

  HTTPClient http;
  String url = "http://" + serverIp + ":" + String(serverPort) + "/dados";
  http.begin(url);
  http.setTimeout(2500);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", ESP_API_KEY);

  String payload = "{\"esp_id\":\"" + String(ESP_ID) + "\",\"queda\":" + (quedaDetectada ? "true" : "false") + "}";
  int httpCode = http.POST(payload);

  // Caso o servidor não responda no IP atual, refaz a busca automática via UDP
  if (httpCode <= 0) {
    descobrirServidorNaRede();
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(500);

  // Configura o pino do buzzer inicialmente desligado
  pinMode(ALARM_PIN, OUTPUT);
  digitalWrite(ALARM_PIN, LOW);

  // Inicializa o barramento I2C e o sensor inercial BMI160
  Wire.begin(sda_pin, scl_pin); 
  
  while (!BMI160.begin(BMI160GenClass::I2C_MODE, i2c_addr)) { 
    Serial.println("Falha na inicializacao do BMI160! Tentando novamente...");
    delay(300);
  }
  
  // Define as escalas de leitura: +-4g para acelerômetro e +-250 graus/s para giroscópio
  BMI160.setAccelerometerRange(4);
  BMI160.setGyroRange(250);
  
  Serial.println("BMI160 inicializado! Iniciando filtro de orientacao e ML...");
  
  // Emite 1 bip curto indicando que o sensor foi inicializado
  acionarAlarme(250);
  delay(200);

  // Limpa os buffers circulares antes de iniciar a coleta
  for(int i=0; i<WINDOW_SIZE; i++){
    ta_buffer[i] = 0.0f;
    va_buffer[i] = 0.0f;
  }

  // Conecta na rede Wi-Fi e registra presença inicial no servidor
  conectarWiFiBateria();
  enviarEventoServidor(false);
}

// Atualiza o quatérnion de orientação 3D pelo algoritmo de fusão sensorial de Madgwick
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

    // Normaliza o vetor de aceleração
    norm = sqrt(a_x * a_x + a_y * a_y + a_z * a_z);
    if (norm == 0.0f) return;
    a_x /= norm;
    a_y /= norm;
    a_z /= norm;

    // Calcula a função objetivo e a matriz Jacobiana
    f_1 = twoSEq_2 * SEq_4 - twoSEq_1 * SEq_3 - a_x;
    f_2 = twoSEq_1 * SEq_2 + twoSEq_3 * SEq_4 - a_y;
    f_3 = 1.0f - twoSEq_2 * SEq_2 - twoSEq_3 * SEq_3 - a_z;
    J_11or24 = twoSEq_3;                                                
    J_12or23 = 2.0f * SEq_4;
    J_13or22 = twoSEq_1;                                                
    J_14or21 = twoSEq_2;
    J_32 = 2.0f * J_14or21;                                             
    J_33 = 2.0f * J_11or24;                                             

    // Calcula o gradiente descendente de correção do acelerômetro
    SEqHatDot_1 = J_14or21 * f_2 - J_11or24 * f_1;
    SEqHatDot_2 = J_12or23 * f_1 + J_13or22 * f_2 - J_32 * f_3;
    SEqHatDot_3 = J_12or23 * f_2 - J_33 * f_3 - J_13or22 * f_1;
    SEqHatDot_4 = J_14or21 * f_1 + J_11or24 * f_2;

    norm = sqrt(SEqHatDot_1 * SEqHatDot_1 + SEqHatDot_2 * SEqHatDot_2 + SEqHatDot_3 * SEqHatDot_3 + SEqHatDot_4 * SEqHatDot_4);
    SEqHatDot_1 /= norm;
    SEqHatDot_2 /= norm;
    SEqHatDot_3 /= norm;
    SEqHatDot_4 /= norm;

    // Calcula a taxa de variação do quatérnion medida pelo giroscópio
    SEqDot_omega_1 = -halfSEq_2 * w_x - halfSEq_3 * w_y - halfSEq_4 * w_z;
    SEqDot_omega_2 = halfSEq_1 * w_x + halfSEq_3 * w_z - halfSEq_4 * w_y;
    SEqDot_omega_3 = halfSEq_1 * w_y - halfSEq_2 * w_z + halfSEq_4 * w_x;
    SEqDot_omega_4 = halfSEq_1 * w_z + halfSEq_2 * w_y - halfSEq_3 * w_x;

    // Integra e normaliza o quatérnion estimado
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

// Calcula as 8 características da janela de 2s e executa a árvore de decisão
void classificarJanela() {
    float TA_sum=0, TA_max=0;
    float TV=0, TV_sum=0, TV_max=0;
    float VV=0, VV_sum=0, VV_max=0;
    float VD=0, VD_sum=0, VD_max=0;

    // Percorre as 100 amostras do buffer em ordem cronológica
    for(int i = 0; i < WINDOW_SIZE; i++) {
        int idx = (buf_index + i) % WINDOW_SIZE;
        float ta = ta_buffer[idx];
        float va = va_buffer[idx];

        // Acumula e identifica o pico da aceleração total (TA)
        TA_sum += ta;
        if(ta > TA_max) TA_max = ta;

        // Integra a aceleração no tempo para obter velocidades total (TV) e vertical (VV)
        TV += ta * deltat;
        VV += va * deltat;

        TV_sum += TV;
        if(TV > TV_max) TV_max = TV;

        VV_sum += VV;
        if(VV > VV_max) VV_max = VV;

        // Integra a velocidade vertical no tempo para obter o deslocamento vertical (VD)
        VD += VV * deltat;
        
        VD_sum += VD;
        if(VD > VD_max) VD_max = VD;
    }

    // Calcula as médias da janela temporal
    float TA_mean = TA_sum / WINDOW_SIZE;
    float TV_mean = TV_sum / WINDOW_SIZE;
    float VV_mean = VV_sum / WINDOW_SIZE;
    float VD_mean = VD_sum / WINDOW_SIZE;

    // Monta o vetor de entrada e executa a predição no modelo embarcado
    float features[8] = {TA_mean, TA_max, TV_mean, TV_max, VV_mean, VV_max, VD_mean, VD_max};

    Serial.printf("Features [TA_m=%.2f, TA_max=%.2f, TV_m=%.2f, TV_max=%.2f, VV_m=%.2f, VV_max=%.2f, VD_m=%.2f, VD_max=%.2f]\n",
                  TA_mean, TA_max, TV_mean, TV_max, VV_mean, VV_max, VD_mean, VD_max);

    int prediction = clf.predict(features); 

    // Em caso de queda confirmada (classe 1), aciona o buzzer e notifica o servidor
    if(prediction == 1) { 
      Serial.println(">>> ALERTA: QUEDA DETECTADA (ML) <<<"); 
      enviarEventoServidor(true);
      acionarAlarme(2000);
      lastHeartbeat = millis();
    } else { 
      Serial.println("ADL (Atividade Normal) - Falso positivo descartado"); 
    }
}

void loop() {
  unsigned long now = millis();
  // Executa a leitura e o processamento na frequência fixa de 50Hz (a cada 20ms)
  if (now - lastUpdate >= 20) { 
    lastUpdate = now;

    int gx, gy, gz; 
    int ax, ay, az; 
    
    // Lê os valores brutos de giroscópio e acelerômetro do BMI160
    BMI160.readGyro(gx, gy, gz);
    BMI160.readAccelerometer(ax, ay, az);
    
    // Converte giroscópio para rad/s e acelerômetro para múltiplos de g (1g = 8192 em +-4g)
    float rad_s_multiplier = (M_PI / 180.0f) / 131.2f;
    float w_x = gx * rad_s_multiplier;
    float w_y = gy * rad_s_multiplier;
    float w_z = gz * rad_s_multiplier;

    float ax_g = (float)ax / 8192.0f;
    float ay_g = (float)ay / 8192.0f;
    float az_g = (float)az / 8192.0f;

    // Atualiza a estimativa de orientação 3D
    filterUpdate(w_x, w_y, w_z, ax_g, ay_g, az_g);

    // Calcula a aceleração total (TA) descontando a gravidade (9.81 m/s^2)
    float accel_mag_ms2 = sqrt(ax_g*ax_g + ay_g*ay_g + az_g*az_g) * 9.81f;
    float current_TA = abs(accel_mag_ms2 - 9.81f);

    // Projeta a aceleração no eixo vertical estimado pelo quatérnion para obter VA
    float grav_x = 2.0f * (SEq_2 * SEq_4 - SEq_1 * SEq_3);
    float grav_y = 2.0f * (SEq_1 * SEq_2 + SEq_3 * SEq_4);
    float grav_z = SEq_1 * SEq_1 - SEq_2 * SEq_2 - SEq_3 * SEq_3 + SEq_4 * SEq_4;

    float v_accel_g = (ax_g * grav_x + ay_g * grav_y + az_g * grav_z);
    float current_VA = abs(v_accel_g - 1.0f) * 9.81f; 

    // Armazena as amostras atuais no buffer circular
    ta_buffer[buf_index] = current_TA;
    va_buffer[buf_index] = current_VA;

    // Avalia os limiares de pré-gatilho: queda livre (< 0.5g) seguida de impacto (> 1.5g)
    absolute_accel = sqrt(sq((double)ax) + sq((double)ay) + sq((double)az));
    
    if (absolute_accel < 4125) queda_livre = true;
    
    if (queda_livre && absolute_accel > 12375 && !em_captura_pos_impacto) {
        em_captura_pos_impacto = true;
        amostras_pos_impacto = 0;
        Serial.println("Impacto detectado! Aguardando estabilizacao (0.5s) para Random Forest...");
    }

    // Após o impacto, aguarda 25 amostras (0.5s) antes de classificar a janela com o modelo ML
    if (em_captura_pos_impacto) {
        amostras_pos_impacto++;
        
        if (amostras_pos_impacto >= ATRASO_AVALIACAO) {
            classificarJanela();
            
            em_captura_pos_impacto = false;
            queda_livre = false;
        }
    }

    buf_index = (buf_index + 1) % WINDOW_SIZE;

    // Envia sinal periódico de presença (heartbeat) a cada 10s quando em estado normal
    if (!em_captura_pos_impacto && !queda_livre && (now - lastHeartbeat >= HEARTBEAT_INTERVAL)) {
        lastHeartbeat = now;
        enviarEventoServidor(false);
    }
  }
}
