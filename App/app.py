import os
import smtplib
import sqlite3
from datetime import datetime
from email.mime.text import MIMEText
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from twilio.rest import Client

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# --- Configurações carregadas do .env ---
# Email
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# Twilio (SMS)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# Banco
DB_NAME = "dados_esp32.db"

# --- Funções de Notificação ---

def enviar_email_notificacao(dados_esp):
    """Envia um email de notificação de queda."""
    try:
        msg_subject = f"Alerta de Queda Detectada de {dados_esp['nome']}"
        msg_body = f"""
        Olá,
        
        Um evento de queda foi detectado pelo dispositivo {dados_esp['esp_id']}.
        
        Detalhes do momento do evento:
        - Temperatura: {dados_esp['temperatura']} °C
        - Batimento Cardíaco: {dados_esp['batimento_cardiaco']} bpm
        
        Por favor, verifique a situação do {dados_esp['nome']}.
        """

        msg = MIMEText(msg_body)
        msg['Subject'] = msg_subject
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = dados_esp['email_noitfy']

        # Conecta ao servidor SMTP do Gmail
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp_server:
            smtp_server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp_server.sendmail(EMAIL_ADDRESS, dados_esp['email_noitfy'], msg.as_string())
        
        print("Notificação por e-mail enviada com sucesso!")
        return True
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")
        return False

def enviar_sms_notificacao(dados_esp):
    """Envia um SMS de notificação de queda usando a Twilio."""
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message_body = (
            f"ALERTA DE QUEDA: {dados_esp['nome']} sofreu uma queda. "
            f"Temp: {dados_esp['temperatura']}C, BPM: {dados_esp['batimento_cardiaco']}. "
            f"Verificar imediatamente a situação do {dados_esp['nome']}."
        )
        
        message = client.messages.create(
            body=message_body,
            from_=TWILIO_PHONE_NUMBER,
            to=dados_esp['number_notify']
        )
        
        print(f"SMS enviado com sucesso! SID: {message.sid}")
        return True
    except Exception as e:
        print(f"Erro ao enviar SMS: {e}")
        return False

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
        batimento_cardiaco INTEGER,
        queda INTEGER NOT NULL
    )
    """)
    
    # Cria a tabela 'clientes'
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
            "INSERT INTO leituras (esp_id, horario, temperatura, batimento_cardiaco, queda) VALUES (?, ?, ?, ?, ?)",
            (dados['esp_id'], horario_atual, dados['temperatura'], dados['batimento_cardiaco'], int(dados['queda']))
        )
        
        conn.commit()
        conn.close()
        
        print(f"Dados do {dados['esp_id']} salvos com sucesso no banco.")
        return jsonify({"status": "sucesso", "mensagem": "Dados recebidos e salvos"}), 201

    except sqlite3.Error as e:
        print(f"Erro no banco de dados: {e}")
        return jsonify({"status": "erro", "mensagem": "Erro interno do servidor ao salvar dados"}), 500


# --- Criação do Servidor Flask ---

app = Flask(__name__)

@app.route("/")
def index():
    return "<h1>Servidor de Notificações Ativo</h1><p>Aguardando dados na rota /dados.</p>"

@app.route('/dados', methods=['POST'])
def receber_dados():
    # Verifica se o conteúdo recebido é JSON
    if not request.is_json:
        return jsonify({"status": "error", "message": "Formato inválido, esperado JSON"}), 400

    dados = request.get_json()
    print(f"Dados recebidos: {dados}")

    # Verifica se os dados essenciais estão presentes
    if not all(key in dados for key in ["queda", "esp_id", "temperatura", "batimento_cardiaco"]):
        return jsonify({"status": "error", "message": "Dados incompletos"}), 400

    # A LÓGICA PRINCIPAL: Checa se houve uma queda
    if dados.get("queda") == True:
        print(f"QUEDA DETECTADA para o dispositivo {dados.get('esp_id')}! Acionando notificações...")
        
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM clientes where esp_id = ?",(dados['esp_id'],))
        resultado = cursor.fetchone()
        
        dados['email_noitfy'] = resultado['email_noitfy']
        dados['number_notify'] = resultado['number_notify']
        dados['nome'] = resultado['nome']
        
        # Envia as notificações
        email_sent = enviar_email_notificacao(dados)
        sms_sent = enviar_sms_notificacao(dados)
        
        mensagem_banco = salva_dados(dados)
        
        if email_sent or sms_sent:
            return jsonify({"status": "success", "message": "Notificações de queda enviadas"}), 200
        else:
            return jsonify({"status": "error", "message": "Falha ao enviar notificações"}), 500

    else:
        # Se não houve queda, apenas confirma o recebimento
        print(f"Dados recebidos de {dados.get('esp_id')} sem alerta de queda.")
        return salva_dados(dados)
        
# Rota para exibir o gráfico
@app.route('/grafico')
def mostrar_grafico():
    # Pega o esp_id da URL (ex: /grafico?esp_id=esp32_sala)
    esp_id_query = request.args.get('esp_id')

    # Se nenhum esp_id for fornecido na URL
    if not esp_id_query:
        return "<h1>Erro</h1><p>Por favor, especifique um ID de ESP na URL. Ex: /grafico?esp_id=esp32_sala</p>", 400

    # Pega os dados do ESP solicitado. Se não existir, retorna uma lista vazia.
    
    
    
    dados_para_grafico = list(dados_dos_esps.get(esp_id_query, []))

    # Cria rótulos para o eixo X (ex: "Amostra 1", "Amostra 2", ...)
    rotulos = [f"Amostra {i+1}" for i in range(len(dados_para_grafico))]

    # Renderiza o template HTML, passando os dados e rótulos
    return render_template('grafico.html', 
                           esp_id=esp_id_query, 
                           dados=json.dumps(dados_para_grafico), 
                           rotulos=json.dumps(rotulos))
        
if __name__ == '__main__':
    inicializar_banco()
    # O 'host="0.0.0.0"' torna o servidor acessível na sua rede local
    app.run(host='0.0.0.0', port=5000, debug=True)
