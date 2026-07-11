from twilio.rest import Client
import smtplib
from dotenv import load_dotenv
from email.mime.text import MIMEText
import os

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
        msg['To'] = dados_esp['email_notify']

        # Conecta ao servidor SMTP do Gmail
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp_server:
            smtp_server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp_server.sendmail(EMAIL_ADDRESS, dados_esp['email_notify'], msg.as_string())
        
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
