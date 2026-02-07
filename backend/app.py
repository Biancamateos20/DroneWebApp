from flask import Flask, request, jsonify, Response
import requests
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)

VM_IP = "192.168.64.2"
VM_PORT = 5002
VM_BASE_URL = f"http://{VM_IP}:{VM_PORT}"

IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "http://127.0.0.1:8080")

colores_ocupados = set()
juego_en_curso = False

jugadores = []
game_start_id = 0
reset_id = 0


@app.route("/Hello", methods=['GET'])
def hola():
    # comprobar el servicio.
    print("Hola")
    return "Hola"

@app.route("/jugador", methods=["POST"])
def registrar_jugador():
    # Registra un jugador, valida datos y reenvia a la VM.
    data = request.get_json() or {}

    lat = data.get("lat")
    lon = data.get("lon")
    alias = data.get("alias")

    if lat is None or lon is None or alias is None:
        return jsonify({"error": "Datos incompletos"}), 400

    if alias in colores_ocupados:
        return jsonify({"error": "Color ya ocupado"}), 400

    colores_ocupados.add(alias)
    jugadores.append({"lat": lat, "lon": lon, "alias": alias})
    print(f"Jugador registrado (proxy) → {alias} ({lat}, {lon})")

    try:
        requests.post(
            f"{VM_BASE_URL}/jugador",
            json={"lat": lat, "lon": lon, "alias": alias},
            timeout=3
        )
    except Exception as e:
        print("Error comunicando con la VM:", e)

        colores_ocupados.discard(alias)
        jugadores[:] = [j for j in jugadores if j.get("alias") != alias]

        return jsonify({"error": "Error comunicando con la VM"}), 500

    return jsonify({
        "status": "ok",
        "colores_ocupados": list(colores_ocupados)
    }), 200


@app.route("/ubicacion-live", methods=["POST"])
def ubicacion_live():
    # Recibe ubicacion en tiempo real y actualiza el estado local.
    data = request.get_json() or {}

    lat = data.get("lat")
    lon = data.get("lon")
    alias = data.get("alias")
    precision = data.get("precision")
    ts = data.get("ts")

    if lat is None or lon is None or alias is None:
        return jsonify({"error": "Datos incompletos"}), 400

    if alias not in colores_ocupados:
        colores_ocupados.add(alias)
        jugadores.append({"lat": lat, "lon": lon, "alias": alias})
        print(f"Jugador auto-registrado → {alias} ({lat}, {lon})")
    else:
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
            jugadores.append({"lat": lat, "lon": lon, "alias": alias, "precision": precision, "ts": ts})

    try:
        requests.post(
            f"{VM_BASE_URL}/ubicacion-live",
            json={"lat": lat, "lon": lon, "alias": alias, "precision": precision, "ts": ts},
            timeout=2
        )
    except Exception as e:
        print("Error enviando ubicación live a la VM:", e)

    return jsonify({"status": "ok"}), 200


@app.route("/colores", methods=["GET"])
def colores():
    # Devuelve la lista de colores ya ocupados por jugadores.
    return jsonify(list(colores_ocupados)), 200


@app.route("/jugadores", methods=["GET"])
def get_jugadores():
    # Devuelve la lista de jugadores para el mapa del admin.
    return jsonify(jugadores), 200


@app.route("/iniciar-juego", methods=["POST"])
def iniciar_juego():
    # Marca el inicio del juego y notifica a la VM.
    global juego_en_curso, game_start_id
    print("Admin → iniciar juego")

    try:
        juego_en_curso = True
        game_start_id += 1

        resp = requests.post(
            f"{VM_BASE_URL}/iniciar-juego",
            json={"jugadores": jugadores},
            timeout=3
        )
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        print("❌ Error iniciar juego:", e)
        return jsonify({"error": "Error iniciando juego en VM", "warning": True}), 500


@app.route("/reset", methods=["POST"])
def reset():
    # Reinicia el estado local y solicita reset en la VM.
    global juego_en_curso, colores_ocupados, jugadores, reset_id

    colores_ocupados.clear()
    jugadores.clear()
    juego_en_curso = False
    reset_id += 1
    print("Juego reseteado (proxy)")

    try:
        requests.post(f"{VM_BASE_URL}/reset", timeout=3)
    except Exception as e:
        print("⚠️ No se pudo resetear VM (continuo igual):", e)

    return jsonify({"status": "reset ok", "reset_id": reset_id}), 200


def _fetch_image_from_rtc(timeout_s: int = 12):
    # Solicita una imagen al servicio RTC y la devuelve.
    url = f"{IMAGE_BASE_URL}/snapshot"
    try:
        resp = requests.get(url, timeout=timeout_s)
    except Exception as e:
        print("Error conectando a RTC:", e)
        return jsonify({"error": "No se pudo conectar al servicio RTC"}), 502

    if not resp.ok:
        return jsonify({"error": "Error en servicio RTC"}), resp.status_code

    ct = (resp.headers.get("Content-Type") or "").lower()
    if ct.startswith("image/"):
        return Response(
            resp.content,
            status=resp.status_code,
            headers={
                "Content-Type": ct,
                "Cache-Control": "no-store"
            }
        )

    return jsonify({"error": "Formato de imagen no soportado"}), 500


@app.route("/foto", methods=["POST"])
def foto():
    # Devuelve una foto actual desde el servicio RTC.
    return _fetch_image_from_rtc()

@app.route("/land", methods=["POST"])
def land():
    # Envia la orden de aterrizaje a la VM.
    try:
        resp = requests.post(f"{VM_BASE_URL}/land", timeout=3)
        return jsonify({"status": "ok", "vm_status": resp.status_code}), 200
    except Exception as e:
        print("⚠️ Error enviando LAND a la VM:", e)
        return jsonify({"error": "Error enviando LAND a la VM"}), 502


@app.route("/foto-y-land", methods=["POST"])
def foto_y_land():
    # Captura una foto y envia la orden de aterrizaje a la VM.
    img_resp = _fetch_image_from_rtc()

    try:
        requests.post(f"{VM_BASE_URL}/land", timeout=3)
    except Exception as e:
        print("⚠️ Error enviando LAND a la VM:", e)

    return img_resp


@app.route("/offer", methods=["POST"])
def webrtc():
    # Informa que la senalizacion WebRTC esta en otro servicio.
    return jsonify({
        "error": "WebRTC está en el servicio dedicado (puerto 8090)"
    }), 400


@app.route("/estado-juego", methods=["GET"])
def estado_juego():
    # Devuelve el estado actual del juego y contadores.
    return jsonify({
        "juego_en_curso": juego_en_curso,
        "reset_id": reset_id,
        "game_start_id": game_start_id
    }), 200

@app.route("/connection", methods=["POST"])
def connection():
    # Proxy al endpoint real de la VM para conectar el dron.
    try:
        resp = requests.post(f"{VM_BASE_URL}/connection", timeout=3)
        if not resp.ok:
            return jsonify({"ok": False, "error": "Error en VM", "vm_status": resp.status_code}), 502
        data = {}
        try:
            data = resp.json()
        except Exception:
            data = {}
        connected = bool(data.get("connected", True))
        return jsonify({"ok": True, "connected": connected}), 200
    except Exception as e:
        print("⚠️ Error conectando dron a la VM:", e)
        return jsonify({"ok": False, "error": "Error comunicando con la VM"}), 502

if __name__ == "__main__":
    print("Servidor Flask proxy en http://127.0.0.1:5001")
    app.run(host="0.0.0.0", port=5001, debug=True)
