import sqlite3
from flask import Flask, request, jsonify, render_template, redirect
from notificacao import enviar_email_notificacao, enviar_sms_notificacao
from banco import DB_NAME, inicializar_banco, salva_dados
import json


# --- Criação do Servidor Flask ---

app = Flask(__name__)

@app.route("/login", methods=['POST', 'GET'])
def login():
    pass

@app.route("/logout")
def logout():
    pass

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
    if not all(key in dados for key in ["queda", "esp_id", "temperatura", "batimento_cardiaco", "spo2"]):
        return jsonify({"status": "error", "message": "Dados incompletos"}), 400

    # A LÓGICA PRINCIPAL: Checa se houve uma queda
    if dados.get("queda") == True:
        print(f"QUEDA DETECTADA para o dispositivo {dados.get('esp_id')}! Acionando notificações...")
        
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM clientes where esp_id = ?",(dados['esp_id'],))
        resultado = cursor.fetchone()
        conn.close()
        
        dados['email_notify'] = resultado['email_notify']
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
        # Se não houve queda, apenas verifica os sinais vitais
        print(f"Dados recebidos de {dados.get('esp_id')} sem alerta de queda. Verificando sinais vitais...")

        #coleta os valores numéricos para verificação
        batimento = float(dados.get("batimento_cardiaco", 0))
        spo2 = float(dados.get("spo2", 100)) #assume 100% caso ainda não esteja enviando o spo2

        #limiares de Segurança
        if batimento > 120 or spo2 < 90:
            print(f"ALERTA: Sinais vitais anormais {dados.get('esp_id')}! Preparando e-mail...")
            
            #busca dados de contato do cliente no banco
            conn = sqlite3.connect(DB_NAME)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM clientes where esp_id = ?", (dados['esp_id'],))
            resultado = cursor.fetchone()

            if resultado:
                dados['email_notify'] = resultado['email_notify']
                dados['nome'] = resultado['nome']

                #envia o email mesmo sem queda
                enviar_email_notificacao(dados)

            conn.close()

        #salva os dados independemente de alerta ou nao    
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
        

@app.route('/api/dados_grafico')
def api_dados_grafico():
    esp_id_query = request.args.get('esp_id')
    horas_atras = request.args.get('horas')

    if not esp_id_query:
        return jsonify({'error': 'esp_id não fornecido'}), 400

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # 1. Consulta original: Traz apenas as quedas para a tabela e o contador
        if horas_atras:
            cursor.execute("""
                SELECT horario 
                FROM leituras 
                WHERE esp_id = ? AND queda = 1 AND horario >= datetime('now', 'localtime', ?)
                ORDER BY id DESC
            """, (esp_id_query, f'-{horas_atras} hours'))
        else:
            cursor.execute("""
                SELECT horario 
                FROM leituras 
                WHERE esp_id = ? AND queda = 1
                ORDER BY id DESC LIMIT 50
            """, (esp_id_query,))
            
        resultados = cursor.fetchall()

        # 2. NOVA CONSULTA: Pega o horário da última leitura enviada (qualquer uma)
        cursor.execute("""
            SELECT horario 
            FROM leituras 
            WHERE esp_id = ? 
            ORDER BY id DESC LIMIT 1
        """, (esp_id_query,))
        
        ultimo_sinal = cursor.fetchone()
        conn.close()

        # Se houver um último sinal, extraímos o texto. Se o banco for novo, devolve None.
        ultima_comunicacao = ultimo_sinal[0] if ultimo_sinal else None

        # Empacota e envia
        dados_json = {
            'total_quedas': len(resultados),
            'horarios_quedas': [row[0] for row in resultados],
            'ultima_comunicacao': ultima_comunicacao
        }

        return jsonify(dados_json)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    inicializar_banco()
    # O 'host="0.0.0.0"' torna o servidor acessível na sua rede local
    app.run(host='0.0.0.0', port=5000, debug=True)
