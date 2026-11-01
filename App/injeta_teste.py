from datetime import datetime
import os
import sys
import time
from dotenv import load_dotenv
import requests

load_dotenv()

SERVER_URL = os.getenv("TEST_SERVER_URL", "http://127.0.0.1:5000/dados")
ESP_ID = os.getenv("ESP_ID", "ESP_SALA_01")
ESP_API_KEY = os.getenv("ESP_API_KEY", "simposio-bmi160-key")


def enviar_evento(queda: bool):
    payload = {
        "esp_id": ESP_ID,
        "queda": queda,
    }
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": ESP_API_KEY,
    }
    horario = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        resp = requests.post(SERVER_URL, json=payload, headers=headers, timeout=10)
        tipo = "[ALERTA] QUEDA DETECTADA" if queda else "[OK] HEARTBEAT (Online)"
        print(f"[{horario}] {tipo} -> Status {resp.status_code}: {resp.text.strip()}")
    except requests.RequestException as e:
        print(f"[{horario}] [ERRO] Falha ao conectar em {SERVER_URL}: {e}")
        print("Certifique-se de que o servidor esta rodando (python App/app.py).")


if __name__ == "__main__":
    print("==========================================================")
    print("Simulador da Pulseira Inteligente (Sensor BMI160)")
    print(f"Alvo: {SERVER_URL} | Dispositivo: {ESP_ID}")
    print("==========================================================\n")

    # Se passar "--queda" na linha de comando, dispara 1 queda imediata e encerra
    if "--queda" in sys.argv:
        enviar_evento(queda=True)
        sys.exit(0)

    print("Modo continuo iniciado: envia 1 Queda seguida de Heartbeats.")
    print("Pressione Ctrl+C para encerrar.\n")

    ciclo = 0
    try:
        while True:
            # Dispara queda no primeiro ciclo e a cada 3 ciclos (~15s); nos demais envia heartbeat
            eh_queda = (ciclo % 3 == 0)
            enviar_evento(queda=eh_queda)
            ciclo += 1
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nSimulacao encerrada pelo usuario.")
