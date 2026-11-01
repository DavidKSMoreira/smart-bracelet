from datetime import datetime
from email.mime.text import MIMEText
import os
import smtplib
from dotenv import load_dotenv
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_ENV = os.path.join(os.path.dirname(BASE_DIR), ".env")
DEFAULT_TELEGRAM_TOKEN = "9126148239:AAE7Ox2Nf00NvkxU1LBtK3CPv5AgWfNk6qA"


def _carregar_env():
    """Carrega variáveis do arquivo .env."""
    load_dotenv(ROOT_ENV, override=True)
    load_dotenv(override=True)


def _obter_token_telegram() -> str:
    _carregar_env()
    return (os.getenv("TELEGRAM_BOT_TOKEN") or DEFAULT_TELEGRAM_TOKEN).strip()


def obter_username_bot_telegram() -> str:
    """Retorna o nome de usuário do bot no Telegram a partir do token configurado."""
    tg_token = _obter_token_telegram()
    if not tg_token:
        return ""
    try:
        resp = requests.get(f"https://api.telegram.org/bot{tg_token}/getMe", timeout=5)
        if resp.status_code == 200:
            dados = resp.json()
            if dados.get("ok") and dados.get("result"):
                return dados["result"].get("username", "")
    except Exception:
        pass
    return ""


def _descobrir_chat_ids_telegram(tg_token: str) -> list[str]:
    """Obtém a lista de Chat IDs ativos do bot no Telegram."""
    chat_ids = set()
    env_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if env_chat_id:
        chat_ids.add(env_chat_id)

    try:
        resp = requests.get(f"https://api.telegram.org/bot{tg_token}/getUpdates", timeout=8)
        if resp.status_code == 200:
            dados = resp.json()
            for item in dados.get("result", []):
                msg = item.get("message") or item.get("my_chat_member") or {}
                chat = msg.get("chat") or {}
                cid = chat.get("id")
                if cid:
                    chat_ids.add(str(cid))
    except Exception as e:
        print(f"[Telegram] Aviso ao consultar getUpdates: {e}")

    return list(chat_ids)


def _montar_texto_alerta(nome: str, esp_id: str, telefone_mascarado: str, horario: str, eh_teste: bool) -> str:
    if eh_teste:
        return (
            f"✅ *Teste de Alerta — Pulseira Inteligente*\n\n"
            f"Olá, *{nome}*!\n"
            f"Seu telefone (`{telefone_mascarado}`) foi vinculado com sucesso ao dispositivo *{esp_id}*.\n"
            f"🕒 Horário do teste: *{horario}*"
        )
    return (
        f"🚨 *ALERTA CRÍTICO: QUEDA DETECTADA!*\n\n"
        f"Olá, *{nome}*!\n"
        f"A pulseira inteligente (*{esp_id}*) acabou de detectar uma *QUEDA* através do sensor inercial BMI160.\n"
        f"📱 Contato vinculado: `{telefone_mascarado}`\n"
        f"🕒 Horário do evento: *{horario}*\n\n"
        f"⚠️ *Por favor, verifique imediatamente a situação do idoso!*"
    )


def enviar_alerta_telefone(destinatario: dict, horario_evento: str = None, eh_teste: bool = False) -> tuple[bool, str]:
    """Envia o alerta de queda para o usuário via Telegram e/ou e-mail."""
    _carregar_env()

    telefone = (destinatario.get("telefone") or "").strip()
    if not telefone:
        return False, "Cadastre e salve seu número de telefone antes de testar o alerta."

    apenas_digitos = "".join(c for c in telefone if c.isdigit())
    tel_mascarado = f"+** (**) *****-{apenas_digitos[-4:]}" if len(apenas_digitos) >= 4 else "****"

    nome = destinatario.get("nome") or "Usuário"
    esp_id = destinatario.get("esp_id") or "ESP_SALA_01"
    horario = horario_evento or datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
    mensagem = _montar_texto_alerta(nome, esp_id, tel_mascarado, horario, eh_teste)

    canais_sucesso = []
    erros = []

    # Envio via Telegram
    tg_token = _obter_token_telegram()
    if tg_token:
        chat_ids = []
        if destinatario.get("callmebot_key") and destinatario["callmebot_key"].lstrip("-").isdigit():
            chat_ids.append(destinatario["callmebot_key"].strip())
        for cid in _descobrir_chat_ids_telegram(tg_token):
            if cid not in chat_ids:
                chat_ids.append(cid)

        if not chat_ids:
            bot_user = obter_username_bot_telegram()
            dica_bot = f"@{bot_user}" if bot_user else "seu Bot no Telegram"
            erros.append(
                f"Abra {dica_bot} no seu Telegram e clique em 'Começar / Start' "
                "para ativar o recebimento no seu celular!"
            )
        else:
            url_tg = f"https://api.telegram.org/bot{tg_token}/sendMessage"
            enviou_algum = False
            for cid in chat_ids:
                try:
                    r_tg = requests.post(
                        url_tg,
                        json={"chat_id": cid, "text": mensagem, "parse_mode": "Markdown"},
                        timeout=10,
                    )
                    if r_tg.status_code == 200:
                        enviou_algum = True
                        print(f"[Telegram] Alerta enviado com sucesso para {nome} (Chat ID {cid})!")
                    else:
                        erros.append(f"Telegram ({r_tg.status_code}): {r_tg.text[:100]}")
                except requests.RequestException as e:
                    erros.append(f"Erro de conexão com o Telegram: {e}")

            if enviou_algum:
                canais_sucesso.append("Telegram")

    # Envio via e-mail (SMTP)
    if destinatario.get("email") and enviar_email_notificacao(destinatario, horario_evento=horario):
        canais_sucesso.append("E-mail")

    if canais_sucesso:
        return True, f"Alerta enviado com sucesso para o seu celular via {', '.join(canais_sucesso)}!"

    if erros:
        return False, " | ".join(erros)

    return (
        False,
        "Token do bot do Telegram não configurado no arquivo .env.",
    )


def enviar_email_notificacao(destinatario: dict, horario_evento: str = None) -> bool:
    """Envia notificação de queda por e-mail via SMTP."""
    _carregar_env()
    email_address = os.getenv("EMAIL_ADDRESS", "").strip()
    email_password = os.getenv("EMAIL_PASSWORD", "").strip()
    email_destino = (destinatario.get("email") or "").strip()

    if not email_destino or not email_address or not email_password:
        return False

    nome = destinatario.get("nome") or "Usuário"
    esp_id = destinatario.get("esp_id") or "ESP_SALA_01"
    horario = horario_evento or datetime.now().strftime("%d/%m/%Y às %H:%M:%S")

    try:
        msg_subject = f"🚨 ALERTA DE QUEDA DETECTADA - Dispositivo {esp_id}"
        msg_body = (
            f"Olá, {nome},\n\n"
            f"Um evento crítico de QUEDA foi detectado pela pulseira inteligente ({esp_id}).\n\n"
            f"Detalhes da ocorrência:\n"
            f"- Sensor: BMI160 (Detecção por Machine Learning)\n"
            f"- Dispositivo: {esp_id}\n"
            f"- Data/Hora: {horario}\n\n"
            f"Por favor, verifique imediatamente a situação da pessoa monitorada.\n\n"
            f"--\n"
            f"Sistema de Monitoramento de Quedas"
        )

        msg = MIMEText(msg_body, "plain", "utf-8")
        msg["Subject"] = msg_subject
        msg["From"] = email_address
        msg["To"] = email_destino

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as smtp_server:
            smtp_server.login(email_address, email_password)
            smtp_server.sendmail(email_address, email_destino, msg.as_string())

        print(f"[E-mail] Notificacao de queda enviada com sucesso para {nome}!")
        return True
    except Exception as e:
        print(f"[E-mail] Erro ao enviar e-mail: {e}")
        return False


def disparar_alertas_queda(esp_id: str, destinatarios: list[dict]) -> dict:
    """Envia os alertas de queda para a lista de destinatários do dispositivo."""
    horario_str = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
    enviados_tel = 0
    enviados_email = 0

    for dest in destinatarios:
        if dest.get("telefone"):
            ok_tel, _ = enviar_alerta_telefone(dest, horario_evento=horario_str)
            if ok_tel:
                enviados_tel += 1

        if dest.get("email"):
            ok_mail = enviar_email_notificacao(dest, horario_evento=horario_str)
            if ok_mail:
                enviados_email += 1

    return {
        "total_destinatarios": len(destinatarios),
        "alertas_celular_enviados": enviados_tel,
        "emails_enviados": enviados_email,
    }
