import sqlite3
from flask import Flask, request, jsonify, render_template
from .notificacao import enviar_email_notificacao, enviar_sms_notificacao
from banco import DB_NAME, inicializar_banco, salva_dados
import json


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

    try:
        # --- CONEXÃO COM O BANCO DE DADOS ---
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Busca temperatura e horário, ordenados por ID (ordem de chegada)
        cursor.execute("""
            SELECT temperatura, batimento_cardiaco, horario 
            FROM leituras 
            WHERE esp_id = ? 
            ORDER BY id ASC
        """, (esp_id_query,))
        
        resultados = cursor.fetchall()
        conn.close()
        
        # Se não houver dados, envia listas vazias
        if not resultados:
            dados_valores = []
            rotulos = []
        else:
            # Separa os resultados em duas listas para o gráfico
            # row[0] é temperatura, row[1] é batimento_cardiaco, row[1] é horario
            dados_valores = {'temperatura': [row[0] for row in resultados], 'batimento_cardiaco' : [row[1] for row in resultados]}
            rotulos = [row[2] for row in resultados]

        # Renderiza o template HTML
        return render_template('grafico.html', 
                               esp_id=esp_id_query, 
                               dados=json.dumps(dados_valores), 
                               rotulos=json.dumps(rotulos))

    except sqlite3.Error as e:
        return f"<h1>Erro no Banco de Dados</h1><p>{e}</p>", 500
        
if __name__ == '__main__':
    inicializar_banco()
    # O 'host="0.0.0.0"' torna o servidor acessível na sua rede local
    app.run(host='0.0.0.0', port=5000, debug=True)
