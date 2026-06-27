import os
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

socketio = SocketIO(app, cors_allowed_origins="*")

receptores = {}
vinculos = {}


@app.route("/")
def index():
    return """
    <h1>📡 Transfer Uni</h1>
    <a href="/receptor">Abrir receptor</a><br>
    <a href="/emisor">Abrir emisor</a>
    """


@app.route("/receptor")
def receptor():
    return render_template("receptor.html")


@app.route("/emisor")
def emisor():
    return render_template("emisor.html")


@app.route("/api/receptores")
def api_receptores():
    return jsonify(list(receptores.values()))


@app.route("/upload", methods=["POST"])
def upload():
    receptor_id = request.form.get("receptor_id")
    dispositivo = request.form.get("dispositivo", "Dispositivo desconocido")
    archivo = request.files.get("archivo")

    if not receptor_id or receptor_id not in receptores:
        return jsonify({"ok": False, "error": "Receptor no disponible"})

    if not archivo:
        return jsonify({"ok": False, "error": "No se envió archivo"})

    ext = os.path.splitext(archivo.filename)[1]
    nombre_guardado = f"{uuid.uuid4().hex}{ext}"
    ruta = os.path.join(app.config["UPLOAD_FOLDER"], nombre_guardado)
    archivo.save(ruta)

    data = {
        "nombre_original": archivo.filename,
        "url": f"/uploads/{nombre_guardado}",
        "dispositivo": dispositivo,
        "fecha": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    }

    socketio.emit("archivo_recibido", data, room=receptor_id)

    return jsonify({"ok": True, "archivo": data})


@app.route("/uploads/<filename>")
def uploads(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@socketio.on("registrar_receptor")
def registrar_receptor(data):
    nombre = data.get("nombre", "Pantalla sin nombre")
    receptor_id = request.sid

    join_room(receptor_id)

    receptores[receptor_id] = {
        "id": receptor_id,
        "nombre": nombre,
        "estado": "Disponible"
    }

    emit("registrado", {
        "id": receptor_id,
        "nombre": nombre,
        "estado": "Disponible"
    })


@socketio.on("vincular_dispositivo")
def vincular_dispositivo(data):
    receptor_id = data.get("receptor_id")
    dispositivo = data.get("dispositivo", "Dispositivo desconocido")
    emisor_id = request.sid

    if receptor_id not in receptores:
        emit("error_vinculo", {"error": "La pantalla ya no está disponible"})
        return

    vinculos[receptor_id] = {
        "emisor_id": emisor_id,
        "dispositivo": dispositivo
    }

    receptores[receptor_id]["estado"] = "Vinculado"

    socketio.emit("dispositivo_vinculado", {
        "dispositivo": dispositivo,
        "emisor_id": emisor_id
    }, room=receptor_id)

    emit("vinculo_confirmado", {
        "receptor_id": receptor_id,
        "pantalla": receptores[receptor_id]["nombre"]
    })


@socketio.on("desvincular_dispositivo")
def desvincular_dispositivo(data):
    receptor_id = data.get("receptor_id")

    if receptor_id in vinculos:
        del vinculos[receptor_id]

    if receptor_id in receptores:
        receptores[receptor_id]["estado"] = "Disponible"
        socketio.emit("dispositivo_desvinculado", {}, room=receptor_id)

    emit("desvinculado_ok", {})


@socketio.on("desvincular_receptor")
def desvincular_receptor():
    receptor_id = request.sid

    if receptor_id in vinculos:
        emisor_id = vinculos[receptor_id].get("emisor_id")
        del vinculos[receptor_id]

        if emisor_id:
            socketio.emit("desvinculado_ok", {}, room=emisor_id)

    if receptor_id in receptores:
        receptores[receptor_id]["estado"] = "Disponible"

    emit("dispositivo_desvinculado", {})


@socketio.on("disconnect")
def desconectar():
    sid = request.sid

    if sid in receptores:
        if sid in vinculos:
            del vinculos[sid]

        del receptores[sid]
        return

    for receptor_id, info in list(vinculos.items()):
        if info.get("emisor_id") == sid:
            del vinculos[receptor_id]

            if receptor_id in receptores:
                receptores[receptor_id]["estado"] = "Disponible"
                socketio.emit("dispositivo_desvinculado", {}, room=receptor_id)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)