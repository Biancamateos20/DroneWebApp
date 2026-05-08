from flask import Flask, request, jsonify, Response
import requests
from flask_cors import CORS
import os
from Voz.voz import get_color_name_from_alias, resolve_spoken_color

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
dron_despegado = False

jugadores = []
game_start_id = 0
reset_id = 0
player_alias_by_id = {}
jugador_actual_alias = None
siguiente_jugador_alias = None
foto_tomada_alias = None
voz_objetivo_alias = None
voz_comando_id = 0


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
    raw_reset_id = data.get("resetId", data.get("reset_id"))
    player_id = None
    client_reset_id = None
    if raw_player_id is not None:
        player_id = str(raw_player_id).strip() or None
    if raw_reset_id is not None:
        try:
            client_reset_id = int(raw_reset_id)
        except Exception:
            client_reset_id = None

    if lat is None or lon is None or alias is None:
        return jsonify({"error": "Datos incompletos"}), 400

    alias = str(alias).strip()
    if not alias:
        return jsonify({"error": "Alias inválido"}), 400

    if client_reset_id is not None and client_reset_id != reset_id:
        return jsonify({"error": "Sesion antigua ignorada", "stale_reset": True}), 409

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
    raw_reset_id = data.get("resetId", data.get("reset_id"))
    client_reset_id = None
    if raw_reset_id is not None:
        try:
            client_reset_id = int(raw_reset_id)
        except Exception:
            client_reset_id = None

    if lat is None or lon is None or alias is None:
        return jsonify({"error": "Datos incompletos"}), 400

    if client_reset_id is not None and client_reset_id != reset_id:
        return jsonify({"error": "Sesion antigua ignorada", "stale_reset": True}), 409

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
            "dron_despegado": dron_despegado,
            "jugador_actual_alias": jugador_actual_alias,
            "siguiente_jugador_alias": siguiente_jugador_alias,
            "game_start_id": game_start_id,
            "forwarded_vm": False
        }), 200
    except Exception as e:
        print("❌ Error iniciar juego:", e)
        return jsonify({"error": "Error iniciando juego en VM", "warning": True}), 500


@app.route("/reset", methods=["POST"])
def reset():
    # Reinicia el estado local y solicita reset en la VM.
    global juego_en_curso, dron_despegado, colores_ocupados, jugadores, reset_id, player_alias_by_id
    global jugador_actual_alias, siguiente_jugador_alias, foto_tomada_alias, voz_objetivo_alias, voz_comando_id

    colores_ocupados.clear()
    jugadores.clear()
    player_alias_by_id.clear()
    juego_en_curso = False
    dron_despegado = False
    jugador_actual_alias = None
    siguiente_jugador_alias = None
    foto_tomada_alias = None
    voz_objetivo_alias = None
    voz_comando_id = 0
    reset_id += 1
    print("Juego reseteado (proxy)")

    if VM_HTTP_PROXY_ENABLED:
        try:
            requests.post(f"{VM_BASE_URL}/reset", timeout=3)
        except Exception as e:
            print("⚠️ No se pudo resetear VM (continuo igual):", e)

    return jsonify({
        "status": "reset ok",
        "reset_id": reset_id,
        "juego_en_curso": juego_en_curso,
        "dron_despegado": dron_despegado,
        "jugador_actual_alias": jugador_actual_alias,
        "siguiente_jugador_alias": siguiente_jugador_alias,
        "foto_tomada_alias": foto_tomada_alias,
        "voz_objetivo_alias": voz_objetivo_alias,
        "voz_comando_id": voz_comando_id
    }), 200


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


def _proxy_webrtc_request(path: str, timeout_s: int = 15):
    url = f"{IMAGE_BASE_URL}/{path.lstrip('/')}"
    method = request.method.upper()

    try:
        if method == "POST":
            upstream = requests.post(
                url,
                data=request.get_data(),
                headers={"Content-Type": request.headers.get("Content-Type", "application/json")},
                timeout=timeout_s
            )
        else:
            upstream = requests.get(url, params=request.args, timeout=timeout_s)
    except Exception as e:
        print(f"Error conectando con servicio WebRTC ({path}):", e)
        return jsonify({"error": "No se pudo conectar al servicio WebRTC"}), 502

    content_type = upstream.headers.get("Content-Type", "")
    response = Response(upstream.content, status=upstream.status_code)
    if content_type:
        response.headers["Content-Type"] = content_type
    response.headers["Cache-Control"] = "no-store"
    return response


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
def webrtc_offer_legacy():
    # Compatibilidad con clientes antiguos que publican directo sobre /offer.
    return _proxy_webrtc_request("/offer")


@app.route("/webrtc/offer", methods=["POST"])
def webrtc_offer():
    return _proxy_webrtc_request("/offer")


@app.route("/webrtc/tracking", methods=["GET"])
def webrtc_tracking():
    return _proxy_webrtc_request("/tracking")


@app.route("/webrtc/snapshot", methods=["GET"])
def webrtc_snapshot():
    return _proxy_webrtc_request("/snapshot")


@app.route("/estado-juego", methods=["GET", "POST"])
def estado_juego():
    global juego_en_curso, dron_despegado, jugador_actual_alias, siguiente_jugador_alias
    global foto_tomada_alias, voz_objetivo_alias, voz_comando_id

    if request.method == "POST":
        data = request.get_json() or {}

        if "juego_en_curso" in data:
            juego_en_curso = bool(data.get("juego_en_curso"))

        if "dron_despegado" in data:
            dron_despegado = bool(data.get("dron_despegado"))

        if "jugador_actual_alias" in data:
            value = data.get("jugador_actual_alias")
            if value is None:
                jugador_actual_alias = None
            else:
                alias = str(value).strip().upper()
                jugador_actual_alias = alias or None

        if "siguiente_jugador_alias" in data:
            value = data.get("siguiente_jugador_alias")
            if value is None:
                siguiente_jugador_alias = None
            else:
                alias = str(value).strip().upper()
                siguiente_jugador_alias = alias or None

        if "foto_tomada_alias" in data:
            value = data.get("foto_tomada_alias")
            if value is None:
                foto_tomada_alias = None
            else:
                alias = str(value).strip().upper()
                foto_tomada_alias = alias or None

        if "voz_objetivo_alias" in data:
            value = data.get("voz_objetivo_alias")
            if value is None:
                voz_objetivo_alias = None
            else:
                alias = str(value).strip().upper()
                voz_objetivo_alias = alias or None

        if "voz_comando_id" in data:
            voz_comando_id = int(data.get("voz_comando_id") or 0)

    # Devuelve el estado actual del juego y contadores.
    return jsonify({
        "juego_en_curso": juego_en_curso,
        "dron_despegado": dron_despegado,
        "jugador_actual_alias": jugador_actual_alias,
        "siguiente_jugador_alias": siguiente_jugador_alias,
        "foto_tomada_alias": foto_tomada_alias,
        "voz_objetivo_alias": voz_objetivo_alias,
        "voz_comando_id": voz_comando_id,
        "reset_id": reset_id,
        "game_start_id": game_start_id
    }), 200


@app.route("/voz-color", methods=["POST"])
def voz_color():
    global siguiente_jugador_alias, foto_tomada_alias, voz_objetivo_alias, voz_comando_id

    data = request.get_json() or {}
    texto = str(data.get("texto") or "").strip()
    current_alias = str(data.get("current_alias") or "").strip().upper()

    if not texto:
        return jsonify({"ok": False, "error": "Falta texto reconocido"}), 400

    if not current_alias:
        return jsonify({"ok": False, "error": "Falta alias actual"}), 400

    if jugador_actual_alias != current_alias:
        return jsonify({"ok": False, "error": "Ahora mismo no te toca enviar el dron"}), 409

    if foto_tomada_alias != current_alias:
        return jsonify({"ok": False, "error": "Primero hay que hacer la foto del jugador actual"}), 409

    aliases_disponibles = []
    for jugador in jugadores:
        alias = str(jugador.get("alias") or "").strip().upper()
        if alias and alias != current_alias:
            aliases_disponibles.append(alias)

    aliases_disponibles = list(dict.fromkeys(aliases_disponibles))
    alias_resuelto = resolve_spoken_color(texto, aliases_disponibles)

    if alias_resuelto is None:
        return jsonify({"ok": False, "error": "No se ha reconocido un color registrado"}), 404

    siguiente_jugador_alias = alias_resuelto
    voz_objetivo_alias = alias_resuelto
    voz_comando_id += 1

    return jsonify({
        "ok": True,
        "texto": texto,
        "alias": alias_resuelto,
        "color_name": get_color_name_from_alias(alias_resuelto),
        "voz_comando_id": voz_comando_id
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
