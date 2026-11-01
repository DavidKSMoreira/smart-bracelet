from functools import wraps
import hmac
import importlib
import os
import socket
import sqlite3
import threading
from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from banco import (
    DB_NAME,
    alternar_alertas_usuario,
    atualizar_contatos_usuario,
    autenticar_usuario,
    buscar_destinatarios_alerta,
    criar_usuario,
    descriptografar_dado,
    excluir_usuario_lgpd,
    inicializar_banco,
    obter_usuario_por_id,
    salva_dados,
)
import notificacao

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "chave-secreta-simposio-lgpd-2026-bmi160")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Chave de autenticação do dispositivo para a rota POST /dados
ESP_API_KEY = os.getenv("ESP_API_KEY", "simposio-bmi160-key")
UDP_DISCOVERY_PORT = 5005


def login_required(f):
    """Exige sessão autenticada para acesso à rota."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Não autorizado. Faça login."}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


@app.after_request
def adicionar_headers_seguranca(response):
    """Adiciona cabeçalhos de segurança HTTP nas respostas."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# Rotas de autenticação e gerenciamento de conta

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("mostrar_grafico"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("mostrar_grafico"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        usuario = autenticar_usuario(username, password)
        if usuario:
            session.clear()
            session["user_id"] = usuario["id"]
            session["esp_id"] = usuario["esp_id"]
            return redirect(url_for("mostrar_grafico", esp_id=usuario["esp_id"]))
        else:
            flash("Usuário ou senha inválidos.", "erro")

    return render_template("login.html")


@app.route("/registro", methods=["POST"])
def registro():
    nome = request.form.get("nome", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    esp_id = request.form.get("esp_id", "ESP_SALA_01").strip() or "ESP_SALA_01"
    consentimento = request.form.get("consentimento_lgpd")

    if consentimento != "on":
        flash(
            "Para criar a conta, é necessário concordar com os termos de privacidade.",
            "erro",
        )
        return redirect(url_for("login"))

    sucesso, mensagem = criar_usuario(nome, username, password, esp_id)
    if not sucesso:
        flash(mensagem, "erro")
        return redirect(url_for("login"))

    usuario = autenticar_usuario(username, password)
    if usuario:
        session.clear()
        session["user_id"] = usuario["id"]
        session["esp_id"] = usuario["esp_id"]
        flash("Conta criada com sucesso! Configure abaixo seu telefone para receber alertas.", "sucesso")
        return redirect(url_for("mostrar_grafico", esp_id=usuario["esp_id"]))

    flash(mensagem, "sucesso")
    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/salvar_contato", methods=["POST"])
@login_required
def api_salvar_contato():
    dados = request.get_json() or {}
    telefone = dados.get("telefone", "")
    callmebot_key = dados.get("callmebot_key", "")
    email = dados.get("email", "")
    esp_id = dados.get("esp_id", "ESP_SALA_01").strip() or "ESP_SALA_01"

    sucesso, msg = atualizar_contatos_usuario(
        session["user_id"],
        telefone=telefone,
        callmebot_key=callmebot_key,
        email=email,
        esp_id=esp_id,
    )
    if sucesso:
        session["esp_id"] = esp_id
        perfil = obter_usuario_por_id(session["user_id"])
        return jsonify({"status": "success", "message": msg, "perfil": perfil}), 200
    return jsonify({"status": "error", "message": msg}), 400


@app.route("/api/testar_alerta", methods=["POST"])
@login_required
def api_testar_alerta():
    """Envia uma notificação de teste para o usuário autenticado."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (session["user_id"],))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({"status": "error", "message": "Usuário não encontrado."}), 404

    telefone = descriptografar_dado(row["telefone_encrypted"])
    apikey = descriptografar_dado(row["callmebot_key_encrypted"])

    if not telefone:
        return jsonify({
            "status": "error",
            "message": "Cadastre e salve seu número de telefone antes de testar o alerta.",
        }), 400

    importlib.reload(notificacao)
    ok, detalhe = notificacao.enviar_alerta_telefone(
        {
            "nome": row["nome"],
            "esp_id": row["esp_id"],
            "telefone": telefone,
            "email": descriptografar_dado(row["email_encrypted"]),
            "callmebot_key": apikey,
        },
        eh_teste=True,
    )
    if ok:
        return jsonify({"status": "success", "message": detalhe}), 200
    return jsonify({"status": "error", "message": detalhe}), 502


@app.route("/api/alternar_alertas", methods=["POST"])
@login_required
def api_alternar_alertas():
    dados = request.get_json() or {}
    ativo = bool(dados.get("ativo", True))
    alternar_alertas_usuario(session["user_id"], ativo)
    perfil = obter_usuario_por_id(session["user_id"])
    return jsonify({
        "status": "success",
        "message": "Recebimento de alertas atualizado.",
        "perfil": perfil,
    }), 200


@app.route("/api/excluir_conta", methods=["POST"])
@login_required
def api_excluir_conta():
    """Remove a conta do usuário autenticado e encerra a sessão."""
    user_id = session["user_id"]
    excluir_usuario_lgpd(user_id)
    session.clear()
    return jsonify({
        "status": "success",
        "message": "Conta e dados de contato excluídos com sucesso.",
    }), 200


# Recepção de leituras do dispositivo

@app.route("/dados", methods=["POST"])
def receber_dados():
    if not request.is_json:
        return jsonify({"status": "error", "message": "Formato inválido, esperado JSON"}), 400

    # Validação da chave de API do dispositivo
    api_key_recebida = request.headers.get("X-API-Key", "")
    if ESP_API_KEY and api_key_recebida and not hmac.compare_digest(api_key_recebida, ESP_API_KEY):
        return jsonify({"status": "error", "message": "Chave de API da pulseira inválida"}), 403

    dados = request.get_json()
    print(f"Dados recebidos da pulseira: {dados}")

    # Validação dos campos obrigatórios
    if not all(key in dados for key in ["queda", "esp_id"]):
        return jsonify({
            "status": "error",
            "message": "Dados incompletos. Esperado: 'esp_id' e 'queda'.",
        }), 400

    # Persistência da leitura no banco de dados
    resposta_banco = salva_dados(dados)

    if bool(dados.get("queda")) is True:
        esp_id = dados.get("esp_id")
        print(f"[ALERTA] QUEDA DETECTADA no dispositivo {esp_id}! Disparando notificacoes...")

        importlib.reload(notificacao)
        destinatarios = buscar_destinatarios_alerta(esp_id)
        resumo_envio = notificacao.disparar_alertas_queda(esp_id, destinatarios)

        return jsonify({
            "status": "success",
            "message": "Queda registrada e alertas processados.",
            "alertas": resumo_envio,
        }), 200

    return resposta_banco


# Rotas do painel de monitoramento

@app.route("/grafico")
@login_required
def mostrar_grafico():
    perfil = obter_usuario_por_id(session["user_id"])
    if not perfil:
        session.clear()
        return redirect(url_for("login"))

    esp_id_query = request.args.get("esp_id") or perfil.get("esp_id") or "ESP_SALA_01"
    importlib.reload(notificacao)
    bot_username = notificacao.obter_username_bot_telegram()
    return render_template(
        "grafico.html",
        esp_id=esp_id_query,
        perfil=perfil,
        bot_username=bot_username,
    )


@app.route("/api/dados_grafico")
@login_required
def api_dados_grafico():
    esp_id_query = request.args.get("esp_id") or session.get("esp_id") or "ESP_SALA_01"
    horas_atras = request.args.get("horas")

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Consulta de ocorrências de queda
        if horas_atras:
            cursor.execute(
                """
                SELECT id, horario
                FROM leituras
                WHERE esp_id = ? AND queda = 1 AND horario >= datetime('now', 'localtime', ?)
                ORDER BY id DESC
                """,
                (esp_id_query, f"-{int(horas_atras)} hours"),
            )
        else:
            cursor.execute(
                """
                SELECT id, horario
                FROM leituras
                WHERE esp_id = ? AND queda = 1
                ORDER BY id DESC LIMIT 50
                """,
                (esp_id_query,),
            )

        resultados_quedas = cursor.fetchall()

        # Consulta do último registro recebido do dispositivo
        cursor.execute(
            """
            SELECT horario, queda
            FROM leituras
            WHERE esp_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (esp_id_query,),
        )
        ultimo_sinal = cursor.fetchone()
        conn.close()

        ultima_comunicacao = ultimo_sinal[0] if ultimo_sinal else None
        ultimo_foi_queda = bool(ultimo_sinal[1]) if ultimo_sinal else False

        eventos = [
            {
                "id": row[0],
                "horario": row[1],
                "queda": 1,
            }
            for row in resultados_quedas
        ]

        return jsonify({
            "esp_id": esp_id_query,
            "total_quedas": len(eventos),
            "eventos": eventos,
            "ultima_comunicacao": ultima_comunicacao,
            "ultimo_foi_queda": ultimo_foi_queda,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def iniciar_servidor_descoberta_udp():
    """Responde via UDP na porta 5005 para descoberta automática do IP do servidor pelo ESP32."""
    def _loop_udp():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", UDP_DISCOVERY_PORT))
            print(f"[Descoberta Automática] Escutando pulseira via UDP na porta {UDP_DISCOVERY_PORT}...")
            while True:
                data, addr = sock.recvfrom(1024)
                mensagem = data.decode("utf-8", errors="ignore").strip()
                if mensagem == "DISCOVER_PULSEIRA_SERVER":
                    sock.sendto(b"PULSEIRA_SERVER_OK:5000", addr)
        except Exception as e:
            print(f"[Descoberta Automática] Aviso UDP: {e}")

    t = threading.Thread(target=_loop_udp, daemon=True)
    t.start()


def obter_ip_local() -> str:
    """Retorna o endereço IP local da máquina na rede ativa."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    inicializar_banco()
    iniciar_servidor_descoberta_udp()
    ip_rede = obter_ip_local()
    print("\n==============================================================")
    print(" SERVIDOR PULSEIRA INTELIGENTE ATIVO!")
    print(" -> No Computador:            http://localhost:5000")
    print(f" -> No Celular (mesmo Wi-Fi): http://{ip_rede}:5000")
    print("==============================================================\n")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
