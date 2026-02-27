#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// --- Configurações de Rede ---
const char* ssid = "NOME_REDE";
const char* password = "SENHA_REDE";
// O endereço do seu servidor. Se o servidor estiver no mesmo computador,
// use o IP local do computador, não "localhost".
// Para descobrir seu IP no Windows, use `ipconfig` no cmd. No Linux/macOS, `ifconfig` ou `ip a`.
const char* serverName = "http://IP.ADDRESS.SERVER:5000/dados"; // <-- TROQUE PELO IP DO SEU PC!

void setup() {
  Serial.begin(115200);
  delay(1000);

  // Conectar ao Wi-Fi
  WiFi.begin(ssid, password);
  Serial.println("Conectando ao WiFi..");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConectado!");
  Serial.print("Endereço IP do ESP32: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  // Simula a leitura dos sensores
  float temperatura = 36.5;
  int batimento_cardiaco = 80;
  String esp_id = "ESP_SALA_01";

  // *** Simula a detecção de queda ***
  // Na prática, esta variável viria do seu sensor (ex: acelerômetro)
  // Alterne entre 'true' e 'false' para testar
  bool queda = true; 

  // Envia os dados
  enviarDados(temperatura, batimento_cardiaco, queda, esp_id);

  // Aguarda 10 segundos antes de enviar novamente
  delay(10000);

  // Envia um dado sem queda para teste
  queda = false;
  enviarDados(temperatura, batimento_cardiaco, queda, esp_id);
  
  delay(10000);
}

void enviarDados(float temp, int bpm, bool queda, String id) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(serverName);
    http.addHeader("Content-Type", "application/json");

    // Cria o documento JSON
    JsonDocument doc; // Para ArduinoJson v6+
    doc["temperatura"] = temp;
    doc["batimento_cardiaco"] = bpm;
    doc["queda"] = queda;
    doc["esp_id"] = id;

    String jsonPayload;
    serializeJson(doc, jsonPayload); // Converte o JSON para uma String

    Serial.println("Enviando payload: ");
    Serial.println(jsonPayload);

    // Envia a requisição POST
    int httpResponseCode = http.POST(jsonPayload);

    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.print("Código de resposta HTTP: ");
      Serial.println(httpResponseCode);
      Serial.print("Resposta do servidor: ");
      Serial.println(response);
    } else {
      Serial.print("Erro no envio. Código: ");
      Serial.println(httpResponseCode);
    }

    http.end();
  } else {
    Serial.println("WiFi Desconectado. Tentando reconectar...");
    WiFi.begin(ssid, password);
  }
}