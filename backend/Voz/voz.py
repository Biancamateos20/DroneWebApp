import speech_recognition as sr

def escuchar_y_mostrar():
    recognizer = sr.Recognizer()

    with sr.Microphone() as source:
        print("Di una palabra...")
        recognizer.adjust_for_ambient_noise(source)
        audio = recognizer.listen(source)

    try:
        texto = recognizer.recognize_google(audio, language="es-ES")
        print("Has dicho:", texto)
        return texto
    except sr.UnknownValueError:
        print("No se ha entendido lo que has dicho.")
    except sr.RequestError:
        print("Error con el servicio de reconocimiento.")

escuchar_y_mostrar()
