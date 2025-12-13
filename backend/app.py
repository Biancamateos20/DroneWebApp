from flask import Flask, request, jsonify
import requests  # Para mandar datos a la VM
import Gestos.imagen

from flask_cors import CORS
app = Flask(__name__)
CORS(app)


VM_IP = "192.168.64.2"  # IP de la VM
VM_PORT = 5002           

@app.route("/ubicacion", methods=["POST"])
def recibir_ubicacion():
    data = request.get_json()
    lat = data.get("lat")
    lon = data.get("lon")
    precision = data.get("precision")

    print(f"Recibido del frontend: lat={lat}, lon={lon}, precision={precision}")
 
    try:
        resp = requests.post(
            f"http://{VM_IP}:{VM_PORT}/coordenadas",
            json={"lat": lat, "lon": lon}
        )
        resp.raise_for_status()
    except Exception as e:
        print("Error enviando a la VM:", e)
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "ok"})

@app.route("/offer", methods=["POST"])
def webRTC():
    return jsonify({"error": "El WebRTC está en el servicio 'webrtc' (puerto 8090)"}), 400

 


if __name__ == "__main__":
    print("Servidor Flask arrancando en http://127.0.0.1:5001 ...")
    app.run(host="0.0.0.0", port=5001, debug=True)
