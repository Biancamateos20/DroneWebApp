# DroneWebApp

Se trata de una aplicación web integrada en el Drone Engineering Ecosystem para interactuar con un dron enviando órdenes como despegar, ir a una ubicación o, incluso, centrar la imagen. Además, en ella se desarrolla una modalidad de juego a la que se le añade procesamiento de imagen y voz.

## Descripción

La aplicación se divide en dos flujos principales: uno orientado al funcionamiento en modo real y otro dedicado al funcionamiento en modo simulación. En ambos casos, los usuarios se registran en la aplicación y participan en una dinámica de juego basada en la selección de un participante, la visualización de un gesto y su posterior imitación para obtener puntos.

El dron actúa como intermediario entre los usuarios y el administrador de la partida, convirtiéndose en el elemento principal de interacción dentro del campo de vuelo. Como resultado, se obtiene una aplicación web que permite la participación simultánea de varios usuarios y facilita la interacción entre estos, el administrador y el dron.

## Vídeos demostrativos

Se adjuntan tres vídeos para facilitar la comprensión de la estructura del código y del funcionamiento de la aplicación:

- Paseo por el código: https://youtu.be/SYcKPRkb4go
- Funcionamiento en modo manual: https://youtu.be/98DStqMm3M4
- Funcionamiento en modo automático: https://youtu.be/ffKhEm094BQ

En el vídeo denominado "Paseo por el código" se explica la estructura del repositorio y los scripts más importantes. En los vídeos de funcionamiento se muestra el comportamiento de la aplicación en los modos manual y automático.

## Tecnologías utilizadas

Vue
Flask
Python
WebSocket
WebRTC
OpenCV
MediaPipe
YOLO
MAVLink / pymavlink
Mission Planner / SITL

## Ejecución con Docker

- Levantar contenedores: docker-compose -d up
- Apagar contenedores: docker-compose -d drown
- Ejecutar un servicio sin contenedor: python3 app.py
- Ejecutar frontend sin contenedor: npm run dev
