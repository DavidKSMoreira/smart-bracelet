import base64
from datetime import datetime
import hashlib
import hmac
import os
import secrets
import sqlite3
from dotenv import load_dotenv
from flask import jsonify
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "dados_esp32.db")
KEY_FILE = os.path.join(BASE_DIR, ".lgpd_master_key")


def _obter_chave_mestra() -> bytes:
    """Obtém ou gera a chave mestra de 256 bits para criptografia dos dados de contato."""
    env_key = os.getenv("DATA_ENCRYPTION_KEY")
    if env_key:
        return hashlib.sha256(env_key.encode("utf-8")).digest()

    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            raw = f.read().strip()
            if len(raw) == 32:
                return raw

    nova_chave = secrets.token_bytes(32)
    try:
        with open(KEY_FILE, "wb") as f:
            f.write(nova_chave)
    except OSError:
        pass
    return nova_chave


def _keystream_sha256(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    """Gera o fluxo de chaves (CTR-SHA256) para o nonce informado."""
    blocos = []
    contador = 0
    gerados = 0
    while gerados < length:
        bloco = hmac.new(
            enc_key,
            nonce + contador.to_bytes(4, "big"),
            hashlib.sha256,
        ).digest()
        blocos.append(bloco)
        gerados += len(bloco)
        contador += 1
    return b"".join(blocos)[:length]


def criptografar_dado(texto_claro: str) -> str:
    """Criptografa uma string utilizando CTR-SHA256 e autenticação HMAC-SHA256."""
    if not texto_claro:
        return ""
    texto_claro = texto_claro.strip()
    if not texto_claro:
        return ""

    chave_mestra = _obter_chave_mestra()
    enc_key = hmac.new(chave_mestra, b"lgpd-enc-v1", hashlib.sha256).digest()
    mac_key = hmac.new(chave_mestra, b"lgpd-mac-v1", hashlib.sha256).digest()

    nonce = secrets.token_bytes(16)
    dados_bytes = texto_claro.encode("utf-8")
    stream = _keystream_sha256(enc_key, nonce, len(dados_bytes))
    ciphertext = bytes(a ^ b for a, b in zip(dados_bytes, stream))
    tag = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()

    payload = base64.urlsafe_b64encode(nonce + tag + ciphertext).decode("ascii")
    return f"enc:v1:{payload}"


def descriptografar_dado(texto_cifrado: str) -> str:
    """Verifica a integridade via HMAC-SHA256 e descriptografa o texto cifrado."""
    if not texto_cifrado or not texto_cifrado.startswith("enc:v1:"):
        return ""

    try:
        chave_mestra = _obter_chave_mestra()
        enc_key = hmac.new(chave_mestra, b"lgpd-enc-v1", hashlib.sha256).digest()
        mac_key = hmac.new(chave_mestra, b"lgpd-mac-v1", hashlib.sha256).digest()

        raw = base64.urlsafe_b64decode(texto_cifrado[7:].encode("ascii"))
        if len(raw) < 48:
            return ""

        nonce = raw[:16]
        tag = raw[16:48]
        ciphertext = raw[48:]

        tag_esperada = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, tag_esperada):
            return ""

        stream = _keystream_sha256(enc_key, nonce, len(ciphertext))
        dados_bytes = bytes(a ^ b for a, b in zip(ciphertext, stream))
        return dados_bytes.decode("utf-8")
    except Exception:
        return ""


def mascarar_telefone(telefone: str) -> str:
    """Formata o número de telefone exibindo apenas os quatro últimos dígitos."""
    if not telefone:
        return "Não cadastrado"
    apenas_digitos = "".join(c for c in telefone if c.isdigit())
    if len(apenas_digitos) >= 4:
        ultimos = apenas_digitos[-4:]
        return f"+** (**) *****-{ultimos}"
    return "****"


def mascarar_email(email: str) -> str:
    """Formata o endereço de e-mail ocultando parte do identificador."""
    if not email or "@" not in email:
        return "Não cadastrado"
    usuario, dominio = email.split("@", 1)
    prefixo = usuario[:2] if len(usuario) >= 2 else usuario[:1]
    return f"{prefixo}***@{dominio}"


def inicializar_banco():
    """Cria as tabelas do banco de dados SQLite caso não existam."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Tabela de leituras do sensor
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leituras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        esp_id TEXT NOT NULL,
        horario TEXT NOT NULL,
        queda INTEGER NOT NULL
    )
    """)

    # Tabela de usuários
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        esp_id TEXT NOT NULL DEFAULT 'ESP_SALA_01',
        telefone_encrypted TEXT DEFAULT '',
        callmebot_key_encrypted TEXT DEFAULT '',
        email_encrypted TEXT DEFAULT '',
        alertas_ativos INTEGER NOT NULL DEFAULT 1,
        consentimento_lgpd INTEGER NOT NULL DEFAULT 1,
        consentimento_data TEXT NOT NULL
    )
    """)

    # Tabela de registro de eventos de conta
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS auditoria_lgpd (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        acao TEXT NOT NULL,
        detalhe TEXT NOT NULL,
        horario TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()
    print(f"Banco de dados '{DB_NAME}' inicializado com sucesso.")


def registrar_auditoria_lgpd(acao: str, detalhe: str):
    """Registra eventos de alteração cadastral no banco de dados."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        horario_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO auditoria_lgpd (acao, detalhe, horario) VALUES (?, ?, ?)",
            (acao, detalhe, horario_atual),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"Erro ao registrar log: {e}")


def salva_dados(dados: dict):
    """Salva uma leitura do dispositivo no banco de dados."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        horario_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            "INSERT INTO leituras (esp_id, horario, queda) VALUES (?, ?, ?)",
            (dados["esp_id"], horario_atual, int(bool(dados["queda"]))),
        )

        conn.commit()
        conn.close()

        print(f"Leitura do dispositivo {dados['esp_id']} (queda={dados['queda']}) salva com sucesso.")
        return jsonify({"status": "sucesso", "mensagem": "Dados recebidos e salvos"}), 201

    except sqlite3.Error as e:
        print(f"Erro no banco de dados: {e}")
        return jsonify({"status": "erro", "mensagem": "Erro interno do servidor ao salvar dados"}), 500


def criar_usuario(nome: str, username: str, senha: str, esp_id: str = "ESP_SALA_01") -> tuple[bool, str]:
    """Cria um novo usuário no banco de dados com senha em hash."""
    username_limpo = username.strip().lower()
    nome_limpo = nome.strip()
    esp_id_limpo = (esp_id or "ESP_SALA_01").strip()

    if len(username_limpo) < 3 or len(senha) < 6:
        return False, "O usuário deve ter pelo menos 3 caracteres e a senha pelo menos 6 caracteres."

    senha_hash = generate_password_hash(senha)
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usuarios (
                nome, username, password_hash, esp_id,
                alertas_ativos, consentimento_lgpd, consentimento_data
            ) VALUES (?, ?, ?, ?, 1, 1, ?)
            """,
            (nome_limpo, username_limpo, senha_hash, esp_id_limpo, agora),
        )
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()

        registrar_auditoria_lgpd(
            "CADASTRO_USUARIO",
            f"Usuário ID #{user_id} concluiu o cadastro.",
        )
        return True, "Conta criada com sucesso!"
    except sqlite3.IntegrityError:
        return False, "Este nome de usuário já está em uso."
    except sqlite3.Error as e:
        return False, f"Erro ao criar usuário: {e}"


def autenticar_usuario(username: str, senha: str):
    """Valida as credenciais do usuário comparando o hash da senha."""
    username_limpo = username.strip().lower()
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE username = ?", (username_limpo,))
    row = cursor.fetchone()
    conn.close()

    if row and check_password_hash(row["password_hash"], senha):
        return dict(row)
    return None


def obter_usuario_por_id(user_id: int):
    """Retorna os dados do usuário com telefone e e-mail mascarados."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    telefone_real = descriptografar_dado(row["telefone_encrypted"])
    callmebot_key_real = descriptografar_dado(row["callmebot_key_encrypted"])
    email_real = descriptografar_dado(row["email_encrypted"])

    return {
        "id": row["id"],
        "nome": row["nome"],
        "username": row["username"],
        "esp_id": row["esp_id"],
        "telefone_mascarado": mascarar_telefone(telefone_real),
        "email_mascarado": mascarar_email(email_real),
        "tem_whatsapp": bool(telefone_real),
        "tem_email": bool(email_real),
        "alertas_ativos": bool(row["alertas_ativos"]),
        "consentimento_data": row["consentimento_data"],
    }


def atualizar_contatos_usuario(
    user_id: int,
    telefone: str,
    callmebot_key: str,
    email: str = "",
    esp_id: str = "ESP_SALA_01",
) -> tuple[bool, str]:
    """Criptografa e atualiza os dados de contato e o dispositivo vinculado ao usuário."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,))
    atual = cursor.fetchone()

    if not atual:
        conn.close()
        return False, "Usuário não encontrado."

    tel_limpo = "".join(c for c in (telefone or "") if c.isdigit() or c == "+")
    key_limpa = (callmebot_key or "").strip()
    email_limpo = (email or "").strip()
    esp_limpo = (esp_id or atual["esp_id"] or "ESP_SALA_01").strip()

    novo_tel_enc = criptografar_dado(tel_limpo) if tel_limpo else atual["telefone_encrypted"]
    nova_key_enc = criptografar_dado(key_limpa) if key_limpa else atual["callmebot_key_encrypted"]
    novo_email_enc = criptografar_dado(email_limpo) if email_limpo else atual["email_encrypted"]

    cursor.execute(
        """
        UPDATE usuarios
        SET telefone_encrypted = ?,
            callmebot_key_encrypted = ?,
            email_encrypted = ?,
            esp_id = ?,
            alertas_ativos = 1
        WHERE id = ?
        """,
        (novo_tel_enc, nova_key_enc, novo_email_enc, esp_limpo, user_id),
    )
    conn.commit()
    conn.close()

    registrar_auditoria_lgpd(
        "ATUALIZACAO_CONTATO",
        f"Usuário ID #{user_id} atualizou os dados de contato (ESP: {esp_limpo}).",
    )
    return True, "Dados de notificação salvos com sucesso!"


def alternar_alertas_usuario(user_id: int, ativo: bool) -> bool:
    """Atualiza o status de ativação de alertas do usuário."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE usuarios SET alertas_ativos = ? WHERE id = ?",
        (1 if ativo else 0, user_id),
    )
    conn.commit()
    conn.close()

    estado = "ATIVADOS" if ativo else "PAUSADOS"
    registrar_auditoria_lgpd(
        f"ALERTAS_{estado}",
        f"Usuário ID #{user_id} alterou o status de alertas para {estado}.",
    )
    return True


def excluir_usuario_lgpd(user_id: int) -> bool:
    """Remove o registro do usuário do banco de dados."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
    deletados = cursor.rowcount
    conn.commit()
    conn.close()

    if deletados > 0:
        registrar_auditoria_lgpd(
            "EXCLUSAO_CONTA",
            f"Usuário ID #{user_id} removeu a conta.",
        )
        return True
    return False


def buscar_destinatarios_alerta(esp_id: str) -> list[dict]:
    """Retorna a lista de destinatários com alertas ativos para o dispositivo informado."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, nome, esp_id, telefone_encrypted, callmebot_key_encrypted, email_encrypted
        FROM usuarios
        WHERE (esp_id = ? OR esp_id = 'TODOS')
          AND alertas_ativos = 1
          AND consentimento_lgpd = 1
        """,
        (esp_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    destinatarios = []
    for row in rows:
        telefone = descriptografar_dado(row["telefone_encrypted"])
        callmebot_key = descriptografar_dado(row["callmebot_key_encrypted"])
        email = descriptografar_dado(row["email_encrypted"])
        if telefone or email:
            destinatarios.append(
                {
                    "nome": row["nome"],
                    "esp_id": esp_id,
                    "telefone": telefone,
                    "callmebot_key": callmebot_key,
                    "email": email,
                }
            )

    # Contato adicional configurado via variáveis de ambiente
    env_phone = os.getenv("WHATSAPP_PHONE", "").strip()
    env_key = os.getenv("CALLMEBOT_API_KEY", "").strip()
    env_email = os.getenv("EMAIL_NOTIFY_DEFAULT", "").strip()
    if env_phone or env_email:
        ja_existe = any(d["telefone"] == env_phone and env_phone for d in destinatarios)
        if not ja_existe:
            destinatarios.append(
                {
                    "nome": os.getenv("PATIENT_NAME", "Monitoramento Simposio"),
                    "esp_id": esp_id,
                    "telefone": env_phone,
                    "callmebot_key": env_key,
                    "email": env_email,
                }
            )

    return destinatarios
