import requests

def obtener_ubicacion(exacta=None):
    """
    exacta: dict con {"lat": valor, "lon": valor} si proviene de GPS o navegador.
    Si no se pasa, devuelve ubicación aproximada por IP.
    """

    # Si recibimos ubicación exacta, la usamos
    if exacta is not None:
        return {
            "metodo": "GPS/Navegador (ubicación exacta)",
            "latitud": exacta.get("lat"),
            "longitud": exacta.get("lon"),
            "precision": exacta.get("precision", "desconocida"),
        }

    # Ubicación aproximada por IP
    try:
        respuesta = requests.get("https://ipinfo.io/json")
        datos = respuesta.json()

        lat, lon = datos.get("loc", ",").split(",")

        return {
            "metodo": "Dirección IP (aproximada)",
            "ip": datos.get("ip"),
            "ciudad": datos.get("city"),
            "region": datos.get("region"),
            "pais": datos.get("country"),
            "latitud": lat,
            "longitud": lon
        }

    except Exception as e:
        print("Error obteniendo ubicación:", e)
        return None


# ---- EJEMPLO ----
info = obtener_ubicacion()
print(info)
