from datetime import datetime
import sqlite3
from flask import jsonify

# Banco
DB_NAME = "dados_esp32.db"


# --- Configuração do Banco de Dados ---
def inicializar_banco():
    """Cria o banco de dados e a tabela se eles ainda não existirem."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Cria a tabela 'leituras'
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leituras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        esp_id TEXT NOT NULL,
        horario TEXT NOT NULL,
        temperatura REAL,
        spo2 REAL NOT NULL,
        batimento_cardiaco INTEGER,
        queda INTEGER NOT NULL
    )
    """)
    
    #Cria a tabela 'usuarios'
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        password TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE
    )
    """)
    
    # Cria a tabela 'clientes'
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        esp_id TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL,
        email_noitfy TEXT NOT NULL UNIQUE,
        number_notify TEXT NOT NULL UNIQUE
    )
    """)
    
    conn.commit()
    conn.close()
    print(f"Banco de dados '{DB_NAME}' inicializado com sucesso.")

def salva_dados(dados):
    # Salva no banco de dados
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        horario_atual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # O '?' previne SQL Injection
        # Converte o booleano 'queda' para 1 (True) ou 0 (False) para o SQLite
        cursor.execute(
            "INSERT INTO leituras (esp_id, horario, temperatura, batimento_cardiaco, queda, spo2) VALUES (?, ?, ?, ?, ?, ?)",
            (dados['esp_id'], horario_atual, dados['temperatura'], dados['batimento_cardiaco'], int(dados['queda']), dados['spo2'])
        )
        
        conn.commit()
        conn.close()
        
        print(f"Dados do {dados['esp_id']} salvos com sucesso no banco.")
        return jsonify({"status": "sucesso", "mensagem": "Dados recebidos e salvos"}), 201

    except sqlite3.Error as e:
        print(f"Erro no banco de dados: {e}")
        return jsonify({"status": "erro", "mensagem": "Erro interno do servidor ao salvar dados"}), 500