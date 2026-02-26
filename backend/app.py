from flask import Flask, request, jsonify, Response
import requests
from flask_cors import CORS
import os

#https://github.com/dronsEETAC/WebAppFlask/blob/main/WebAppHTTP/app/dron_controls.py

app = Flask(__name__)
CORS(app)

VM_IP = "192.168.64.2"
VM_PORT = 5002
VM_BASE_URL = f"http://{VM_IP}:{VM_PORT}"
VM_HTTP_PROXY_ENABLED = os.getenv("VM_HTTP_PROXY_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}

IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "http://127.0.0.1:8080")

colores_ocupados = set()
juego_en_curso = False

jugadores = []
game_start_id = 0
reset_id = 0
player_alias_by_id = {}


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
    raw_player_id = data.get("playerId", data.get("player_id"))
    player_id = None
    if raw_player_id is not None:
        player_id = str(raw_player_id).strip() or None

    if lat is None or lon is None or alias is None:
        return jsonify({"error": "Datos incompletos"}), 400

    alias = str(alias).strip()
    if not alias:
        return jsonify({"error": "Alias inválido"}), 400

    if player_id:
        prev_alias = player_alias_by_id.get(player_id)
        if prev_alias and prev_alias != alias:
            colores_ocupados.discard(prev_alias)
            jugadores[:] = [j for j in jugadores if j.get("alias") != prev_alias]
            print(f"Liberado alias previo ({prev_alias}) para playerId={player_id}")

    existing = None
    for j in jugadores:
        if j.get("alias") == alias:
            existing = j
            break

    if existing is not None:
        existing_player_id = existing.get("playerId")
        existing_player_id = str(existing_player_id).strip() if existing_player_id is not None else None
        if existing_player_id and existing_player_id != player_id:
            return jsonify({"error": "Color ya ocupado"}), 400
        if existing_player_id is None and player_id is None and alias in colores_ocupados:
            return jsonify({"error": "Color ya ocupado"}), 400

        existing["lat"] = lat
        existing["lon"] = lon
        if player_id:
            existing["playerId"] = player_id
            player_alias_by_id[player_id] = alias
        colores_ocupados.add(alias)
        created_new = False
    else:
        if alias in colores_ocupados:
            return jsonify({"error": "Color ya ocupado"}), 400
        payload = {"lat": lat, "lon": lon, "alias": alias}
        if player_id:
            payload["playerId"] = player_id
            player_alias_by_id[player_id] = alias
        colores_ocupados.add(alias)
        jugadores.append(payload)
        created_new = True

    print(f"Jugador registrado (proxy) → {alias} ({lat}, {lon})")

    if VM_HTTP_PROXY_ENABLED:
        try:
            requests.post(
                f"{VM_BASE_URL}/jugador",
                json={"lat": lat, "lon": lon, "alias": alias, "playerId": player_id},
                timeout=3
            )
        except Exception as e:
            print("Error comunicando con la VM:", e)

            if created_new:
                colores_ocupados.discard(alias)
                jugadores[:] = [j for j in jugadores if j.get("alias") != alias]
                if player_id and player_alias_by_id.get(player_id) == alias:
                    player_alias_by_id.pop(player_id, None)
            return jsonify({"error": "Error comunicando con la VM"}), 500

    return jsonify({
        "status": "ok",
        "colores_ocupados": list(colores_ocupados),
        "forwarded_vm": VM_HTTP_PROXY_ENABLED
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

    if VM_HTTP_PROXY_ENABLED:
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

        if VM_HTTP_PROXY_ENABLED:
            resp = requests.post(
                f"{VM_BASE_URL}/iniciar-juego",
                json={"jugadores": jugadores},
                timeout=3
            )
            return jsonify(resp.json()), resp.status_code

        return jsonify({
            "status": "ok",
            "juego_en_curso": juego_en_curso,
            "game_start_id": game_start_id,
            "forwarded_vm": False
        }), 200
    except Exception as e:
        print("❌ Error iniciar juego:", e)
        return jsonify({"error": "Error iniciando juego en VM", "warning": True}), 500


@app.route("/reset", methods=["POST"])
def reset():
    # Reinicia el estado local y solicita reset en la VM.
    global juego_en_curso, colores_ocupados, jugadores, reset_id, player_alias_by_id

    colores_ocupados.clear()
    jugadores.clear()
    player_alias_by_id.clear()
    juego_en_curso = False
    reset_id += 1
    print("Juego reseteado (proxy)")

    if VM_HTTP_PROXY_ENABLED:
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
        resp = requests.post(f"{VM_BASE_URL}/land", timeout=10)
        if not resp.ok:
            try:
                data = resp.json()
            except Exception:
                data = {"ok": False, "error": "Error en VM"}
            return jsonify(data), resp.status_code
        try:
            data = resp.json()
        except Exception:
            data = {"ok": True, "land": True}
        return jsonify(data), 200
    except requests.exceptions.Timeout:
        # Si tarda en responder pero el dron ya aterrizó, evitamos romper el flujo UI.
        return jsonify({"ok": True, "land": True, "warning": "Timeout VM"}), 202
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
    data = request.get_json() or {}
    tipo = data.get("tipo")
    try:
        resp = requests.post(f"{VM_BASE_URL}/connection", json={"tipo": tipo}, timeout=3)
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

@app.route("/disconnection", methods=['POST'])
def disconnection():
    try:
        resp = requests.post(f"{VM_BASE_URL}/disconnection", timeout = 3)
        if not resp.ok:
            return jsonify({"ok": False, "error": "Error en VM", "vm_status": resp.status_code}), 502
        data = {}
        try:
            data = resp.json()
        except Exception:
            data = {}
        disconnected = bool(data.get("disconnected", True))
        return jsonify({"ok": True, "disconnected": disconnected}), 200
    except Exception as e:
        print("⚠️ Error conectando dron a la VM:", e)
        return jsonify({"ok": False, "error": "Error comunicando con la VM"}), 502
    
@app.route("/despegue", methods=["POST"])
def despegue():
    # Proxy al endpoint real de la VM para despegar.
    data = request.get_json() or {}
    height = data.get("height")
    h = data.get("h", height)

    try:
        resp = requests.post(f"{VM_BASE_URL}/despegue", json={"h": h}, timeout=20)
        if not resp.ok:
            return jsonify({"ok": False, "error": "Error en VM", "vm_status": resp.status_code}), 502
        vm_data = {}
        try:
            vm_data = resp.json()
        except Exception:
            vm_data = {}
        despegue_ok = bool(vm_data.get("despegue", True))
        return jsonify({"ok": True, "despegue": despegue_ok}), 200
    except requests.exceptions.Timeout:
        # La VM puede tardar en responder aunque el dron ya haya despegado.
        return jsonify({"ok": False, "error": "Timeout comunicando con la VM"}), 504
    except Exception as e:
        print("⚠️ Error enviando despegue a la VM:", e)
        return jsonify({"ok": False, "error": "Error comunicando con la VM"}), 502

@app.route("/goto-admin", methods=["POST"])
def goto_admin():
    # Proxy para enviar GOTO a la VM con lat/lon del administrador.
    data = request.get_json() or {}
    lat = data.get("lat")
    lon = data.get("lon")
    h = data.get("h")
    if lat is None or lon is None:
        return jsonify({"ok": False, "error": "Faltan lat/lon"}), 400
    try:
        resp = requests.post(
            f"{VM_BASE_URL}/GoTo",
            json={"lat": lat, "lon": lon, "h": h},
            timeout=20
        )
        if not resp.ok:
            try:
                vm_data = resp.json()
            except Exception:
                vm_data = {"ok": False, "error": "Error en VM"}
            return jsonify(vm_data), resp.status_code
        try:
            vm_data = resp.json()
        except Exception:
            vm_data = {"ok": True}
        return jsonify(vm_data), 200
    except requests.exceptions.Timeout:
        # La VM puede tardar en responder aunque ya esté ejecutando el goto.
        return jsonify({"ok": True, "goto": True, "warning": "Timeout VM"}), 202
    except Exception as e:
        print("⚠️ Error enviando GOTO a la VM:", e)
        return jsonify({"ok": False, "error": "Error comunicando con la VM"}), 502
    
# @app.route("/land", methods = ['POST'])
# def land():
#     try:
#         resp = requests.post(f"{VM_BASE_URL}/land")
#         if not resp.ok:
#             return jsonify({"ok": False, "Error": "Error en land", "vm_status": resp.status_code}), 502
#         else:
#             return jsonify({"ok": True})
        
#     except Exception as e:
#         return False

if __name__ == "__main__":
    print("Servidor Flask proxy en http://127.0.0.1:5001")
    app.run(host="0.0.0.0", port=5001, debug=True)
