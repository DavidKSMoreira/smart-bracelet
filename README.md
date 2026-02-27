# Projeto Pulseira Inteligente

## Descrição
App para envio de notificações de Alerta e Armazenamento de dados corporais

## Tecnologias Utilizadas:
- **Python**
    - **Flask**
    - **python-dotenv**
    - **Twilio**
    - **SMTP GMAIL**
    - **SQLITE3**
- **DB Browser**
- **Postman**

### Como executar
1. Instale o python:
    ```bash
    python
    ```
2. Crie um ambiente virtual .venv:
    ```bash
    python -m venv .venv
    ```
3. Ative o ambiente virtual:
    ```bash
    .\.venv\Scripts\activate
    ```
4. Faça as importações:
    ```bash
    pip install -r .\requirements.txt
    ```
5. Execute o arquivo app.py:
    ```bash
    python .\App\app.py
    ```

- Para desativar o ambiente virtual:
    ```bash
    deactivate
    ```

### Configurando banco de dados:
1. Execute o app.py
2. Vá até a tabela cliente e insira os seus dados. Exemplo:

| id | nome  | esp_id      | email_noitfy        | number_notify  |
|----|-------|-------------|---------------------|----------------|
| 1  | Pedro | ESP_SALA_01 | seu_email@gmail.com | +5588940028922 |

3. Em seguida veja os links [SMTP GMAIL PYTHON](#smtp) e [TWilio SMS PYTHON](#twilio) para configurar o .env para o recebimento de dados

### Links para ver com mais detalhes o funcionamento:
- [SMTP GMAIL PYTHON](https://www.youtube.com/watch?v=N97q96BygUg) 
- [TWilio SMS PYTHON](https://www.youtube.com/watch?v=Hd7n2J5mZ7o)
- [Flask](https://flask.palletsprojects.com/en/stable/)
- [SQLITE3 Python](https://www.youtube.com/watch?v=byHcYRpMgI4)
- [python-dotenv](https://pypi.org/project/python-dotenv/)