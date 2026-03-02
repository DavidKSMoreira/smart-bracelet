from flask import Flask, jsonify, render_template, request
from banco import inicializar_banco, buscar_historico_influx

app = Flask(__name__)

@app.route("/")
def index():
    return "<h1>Sistema IoT MQTT + InfluxDB</h1><p>Acesse /grafico?esp_id=SEU_ID</p>"

# Rota para renderizar a página HTML
@app.route('/grafico')
def pagina_grafico():
    esp_id = request.args.get('esp_id')
    if not esp_id:
        return "Informe o esp_id na URL", 400
    return render_template('grafico.html', esp_id=esp_id)

# API JSON para o JavaScript buscar dados em tempo real
@app.route('/api/historico')
def api_historico():
    esp_id = request.args.get('esp_id')
    if not esp_id:
        return jsonify({"error": "Faltou esp_id"}), 400
        
    dados = buscar_historico_influx(esp_id)
    return jsonify(dados)

if __name__ == '__main__':
    inicializar_banco()
    app.run(host='0.0.0.0', port=5000, debug=True)