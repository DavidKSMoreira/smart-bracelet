# Pulseira Inteligente — Monitoramento de Quedas

Sistema embarcado e aplicação web para detecção de quedas em tempo real utilizando o sensor inercial **BMI160 (Acelerômetro e Giroscópio)**, **Filtro de Orientação Madgwick**, **Árvore de Decisão embarcada** no **ESP32-C3 Mini** e envio de alertas via **Telegram** e **E-mail**.

---

## Estrutura do Projeto

* **[`QUEDA_BMI160_2/QUEDA_BMI160_2.ino`](QUEDA_BMI160_2/QUEDA_BMI160_2.ino)**: Firmware do ESP32 (leitura a 50Hz, filtro Madgwick, gatilho de queda livre e impacto, classificação com [`dt_model.h`](QUEDA_BMI160_2/dt_model.h) e descoberta automática do servidor via UDP).
* **[`App/app.py`](App/app.py)**: Servidor Flask com autenticação de usuários, recepção de eventos do ESP32 (`POST /dados`) e API do painel em tempo real.
* **[`App/banco.py`](App/banco.py)**: Persistência em SQLite com criptografia de dados de contato (`CTR-SHA256 + HMAC-SHA256`) e hash de senhas.
* **[`App/notificacao.py`](App/notificacao.py)**: Envio de alertas de queda via Bot do Telegram e SMTP.
* **[`App/templates/login.html`](App/templates/login.html)** e **[`App/templates/grafico.html`](App/templates/grafico.html)**: Interfaces de acesso e painel de monitoramento em tempo real.

---

## Execução

### 1. Iniciar o Servidor
```powershell
python App/app.py
```
O terminal exibirá os endereços de acesso para o computador (`http://localhost:5000`) e para dispositivos na mesma rede Wi-Fi.

### 2. Simulador de Eventos (Teste sem Hardware)
```powershell
python App/injeta_teste.py --queda
```
