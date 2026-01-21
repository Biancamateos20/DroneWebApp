from flask import Flask, request, jsonify
import requests
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ===============================
# CONFIG VM
# ===============================
VM_IP = "192.168.64.2"
VM_PORT = 5002
VM_BASE_URL = f"http://{VM_IP}:{VM_PORT}"

# ===============================
# ESTADO LOCAL (PROXY)
# ===============================
colores_ocupados = set()
juego_en_curso = False

# Guardamos jugadores para que el panel admin pueda pintarlos en el mapa
# Cada item: {"lat": float, "lon": float, "alias": str (hex color)}
jugadores = []


# ===============================
# JUGADOR → REGISTRO
# ===============================
@app.route("/jugador", methods=["POST"])
def registrar_jugador():
    data = request.get_json() or {}

    lat = data.get("lat")
    lon = data.get("lon")
    alias = data.get("alias")

    # ✅ Validación robusta: 0.0 es válido, por eso usamos "is None"
    if lat is None or lon is None or alias is None:
        return jsonify({"error": "Datos incompletos"}), 400

    # 🔒 bloquear color
    if alias in colores_ocupados:
        return jsonify({"error": "Color ya ocupado"}), 400

    # Guardar estado local
    colores_ocupados.add(alias)
    jugadores.append({"lat": lat, "lon": lon, "alias": alias})
    print(f"Jugador registrado (proxy) → {alias} ({lat}, {lon})")

    # reenviar a la VM
    try:
        requests.post(
            f"{VM_BASE_URL}/jugador",
            json={"lat": lat, "lon": lon, "alias": alias},
            timeout=3
        )
    except Exception as e:
        print("❌ Error comunicando con la VM:", e)

        # rollback local
        colores_ocupados.discard(alias)
        jugadores[:] = [j for j in jugadores if j.get("alias") != alias]

        return jsonify({"error": "Error comunicando con la VM"}), 500

    return jsonify({
        "status": "ok",
        "colores_ocupados": list(colores_ocupados)
    }), 200


# ===============================
# UBICACIÓN EN DIRECTO (LIVE)
# ===============================
@app.route("/ubicacion-live", methods=["POST"])
def ubicacion_live():
    data = request.get_json() or {}

    lat = data.get("lat")
    lon = data.get("lon")
    alias = data.get("alias")
    precision = data.get("precision")
    ts = data.get("ts")

    if lat is None or lon is None or alias is None:
        return jsonify({"error": "Datos incompletos"}), 400

    # Si no está registrado, devolvemos error para que el frontend haga fallback a /jugador
    if alias not in colores_ocupados:
        return jsonify({"error": "Jugador no registrado"}), 400

    # Actualiza posición del jugador en la lista
    found = False
    for j in jugadores:
        if j.get("alias") == alias:
            j["lat"] = lat
            j["lon"] = lon
            j["precision"] = precision
            j["ts"] = ts
            found = True
            break

    if not found:
        # Inconsistencia set/list
        jugadores.append({"lat": lat, "lon": lon, "alias": alias, "precision": precision, "ts": ts})

    # Reenviar a la VM si tiene endpoint equivalente (opcional)
    try:
        requests.post(
            f"{VM_BASE_URL}/ubicacion-live",
            json={"lat": lat, "lon": lon, "alias": alias, "precision": precision, "ts": ts},
            timeout=2
        )
    except Exception as e:
        print("⚠️ Error enviando ubicación live a la VM:", e)

    return jsonify({"status": "ok"}), 200


# ===============================
# COLORES OCUPADOS
# ===============================
@app.route("/colores", methods=["GET"])
def colores():
    return jsonify(list(colores_ocupados)), 200


# ===============================
# JUGADORES (para el mapa del admin)
# ===============================
@app.route("/jugadores", methods=["GET"])
def get_jugadores():
    return jsonify(jugadores), 200


# ===============================
# ADMIN → INICIAR JUEGO
# ===============================
@app.route("/iniciar-juego", methods=["POST"])
def iniciar_juego():
    global juego_en_curso
    print("Admin → iniciar juego")

    juego_en_curso = True  # 🔑 estado local

    try:
        resp = requests.post(f"{VM_BASE_URL}/iniciar-juego", timeout=3)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        print("❌ Error iniciar juego:", e)
        juego_en_curso = False
        return jsonify({"error": "Error iniciando juego"}), 500


# ===============================
# ADMIN → RESET
# ===============================
@app.route("/reset", methods=["POST"])
def reset():
    global juego_en_curso, colores_ocupados, jugadores

    colores_ocupados.clear()
    jugadores.clear()
    juego_en_curso = False
    print("Juego reseteado (proxy)")

    try:
        requests.post(f"{VM_BASE_URL}/reset", timeout=3)
    except Exception as e:
        print("⚠️ No se pudo resetear VM (continuo igual):", e)

    return jsonify({"status": "reset ok"}), 200


# ===============================
# INFO WEBRTC
# ===============================
@app.route("/offer", methods=["POST"])
def webrtc():
    return jsonify({
        "error": "WebRTC está en el servicio dedicado (puerto 8090)"
    }), 400


@app.route("/estado-juego", methods=["GET"])
def estado_juego():
    return jsonify({"juego_en_curso": juego_en_curso}), 200


# ===============================
# MAIN
# ===============================
if __name__ == "__main__":
    print("Servidor Flask proxy en http://127.0.0.1:5001")
    app.run(host="0.0.0.0", port=5001, debug=True)
