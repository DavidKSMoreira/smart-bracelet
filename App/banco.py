import sqlite3
from datetime import datetime
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import os
from dotenv import load_dotenv

load_dotenv()

# --- Configurações do SQLite (Clientes) ---
DB_SQLITE = "dados_esp32.db"

# --- Configurações do InfluxDB (Sensores) ---
INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "SEU_TOKEN_AQUI")
INFLUX_ORG = os.getenv("INFLUX_ORG", "sua-organizacao")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "monitoramento_esp32")

# Inicializa cliente Influx
client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)
query_api = client.query_api()

def inicializar_banco():
    """Inicializa apenas a tabela de clientes no SQLite."""
    conn = sqlite3.connect(DB_SQLITE)
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        esp_id TEXT NOT NULL UNIQUE,
        email_noitfy TEXT NOT NULL UNIQUE,
        number_notify TEXT NOT NULL UNIQUE
    )
    """)
    conn.commit()
    conn.close()
    print("Banco SQLite (Clientes) inicializado.")

def buscar_cliente(esp_id):
    """Busca dados de contato do cliente no SQLite."""
    conn = sqlite3.connect(DB_SQLITE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes WHERE esp_id = ?", (esp_id,))
    resultado = cursor.fetchone()
    conn.close()
    return resultado

def salvar_leitura_influx(dados):
    """Salva a leitura dos sensores no InfluxDB."""
    try:
        point = Point("sensores") \
            .tag("esp_id", dados['esp_id']) \
            .field("temperatura", float(dados['temperatura'])) \
            .field("batimento_cardiaco", int(dados['batimento_cardiaco'])) \
            .field("queda", int(dados['queda'])) \
            .time(datetime.utcnow(), WritePrecision.NS)

        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        print(f"Dados salvos no InfluxDB para {dados['esp_id']}")
        return True
    except Exception as e:
        print(f"Erro ao salvar no InfluxDB: {e}")
        return False

def buscar_historico_influx(esp_id):
    """Busca dados da última hora para o gráfico."""
    query = f'''
    from(bucket: "{INFLUX_BUCKET}")
      |> range(start: -1h)
      |> filter(fn: (r) => r["_measurement"] == "sensores")
      |> filter(fn: (r) => r["esp_id"] == "{esp_id}")
      |> filter(fn: (r) => r["_field"] == "temperatura" or r["_field"] == "batimento_cardiaco")
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> sort(columns: ["_time"])
    '''
    
    try:
        result = query_api.query(org=INFLUX_ORG, query=query)
        dados_retorno = {"labels": [], "temperatura": [], "batimentos": []}
        
        for table in result:
            for record in table.records:
                hora = record.get_time().strftime('%H:%M:%S')
                temp = record.get("temperatura")
                bpm = record.get("batimento_cardiaco")
                
                if hora:
                    dados_retorno["labels"].append(hora)
                    dados_retorno["temperatura"].append(temp if temp is not None else 0)
                    dados_retorno["batimentos"].append(bpm if bpm is not None else 0)
                    
        return dados_retorno
    except Exception as e:
        print(f"Erro na query Influx: {e}")
        return {"labels": [], "temperatura": [], "batimentos": []}