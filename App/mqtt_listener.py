import json
import paho.mqtt.client as mqtt
from banco import salvar_leitura_influx, buscar_cliente
from notificacao import enviar_email_notificacao, enviar_sms_notificacao

# Configurações MQTT
MQTT_BROKER = "localhost" # ou IP do seu broker
MQTT_PORT = 1883
MQTT_TOPIC = "esp32/dados"

def on_connect(client, userdata, flags, rc):
    print(f"Conectado ao MQTT Broker com código: {rc}")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        print(f"Recebido: {payload}")
        dados = json.loads(payload)
        
        # 1. Salvar no InfluxDB
        salvar_leitura_influx(dados)
        
        # 2. Verificar Queda
        if dados.get("queda") == True:
            print(f"QUEDA DETECTADA: {dados['esp_id']}")
            cliente = buscar_cliente(dados['esp_id'])
            
            if cliente:
                dados_notificacao = dict(dados) # Copia dados
                dados_notificacao['email_noitfy'] = cliente['email_noitfy']
                dados_notificacao['number_notify'] = cliente['number_notify']
                dados_notificacao['nome'] = cliente['nome']
                
                enviar_email_notificacao(dados_notificacao)
                enviar_sms_notificacao(dados_notificacao)
            else:
                print("Cliente não cadastrado para notificações.")

    except json.JSONDecodeError:
        print("Erro ao decodificar JSON")
    except Exception as e:
        print(f"Erro no processamento MQTT: {e}")

if __name__ == "__main__":
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    print("Iniciando Listener MQTT...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_forever()