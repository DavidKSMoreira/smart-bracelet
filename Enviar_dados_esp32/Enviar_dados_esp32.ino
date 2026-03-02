#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// --- Configurações de Rede ---
const char* ssid = "NOME_REDE";
const char* password = "SENHA_REDE";

// --- Configurações MQTT ---
const char* mqtt_server = "IP.DO.BROKER.MQTT"; // Ex: 192.168.1.100
const int mqtt_port = 1883;
const char* mqtt_topic = "esp32/dados";

WiFiClient espClient;
PubSubClient client(espClient);

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Conectando a ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("Conectado!");
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Tentando conexão MQTT...");
    // Cria um ID randômico para não conflitar
    String clientId = "ESP32Client-";
    clientId += String(random(0xffff), HEX);
    
    if (client.connect(clientId.c_str())) {
      Serial.println("conectado");
    } else {
      Serial.print("falhou, rc=");
      Serial.print(client.state());
      Serial.println(" tentando novamente em 5s");
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // --- Simulação de Dados ---
  float temperatura = 36.5 + (random(-10, 10) / 10.0); // Variação leve
  int batimento_cardiaco = 80 + random(-5, 10);
  String esp_id = "ESP_SALA_01";
  bool queda = false; 
  
  // Simula queda aleatória (1% de chance a cada loop)
  if(random(0, 100) > 98) queda = true;

  // Criação do JSON
  JsonDocument doc;
  doc["temperatura"] = temperatura;
  doc["batimento_cardiaco"] = batimento_cardiaco;
  doc["queda"] = queda;
  doc["esp_id"] = esp_id;

  String jsonPayload;
  serializeJson(doc, jsonPayload);

  Serial.print("Publicando: ");
  Serial.println(jsonPayload);

  // Publica no tópico MQTT
  client.publish(mqtt_topic, jsonPayload.c_str());

  delay(2000); // Envia a cada 2 segundos
}