from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, join_room, leave_room, send

app = Flask(__name__)
app.secret_key = "supersecretkey"

socketio = SocketIO(app)

# Guardar salas en memoria
rooms = {}


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        room = request.form.get("room")
        password = request.form.get("password")
        action = request.form.get("action")

        if action == "create":
            if room in rooms:
                return "Room already exists"
            rooms[room] = password

        elif action == "join":
            if room not in rooms:
                return "Room does not exist"
            if rooms[room] != password:
                return "Wrong password"

        session["room"] = room
        return redirect("/chat")

    return render_template("index.html")


@app.route("/chat")
def chat():
    room = session.get("room")
    if not room:
        return redirect("/")
    return render_template("chat.html", room=room)


@socketio.on("message")
def handle_message(msg):
    room = session.get("room")
    send(msg, to=room)


@socketio.on("join")
def handle_join():
    room = session.get("room")
    join_room(room)
    send("User joined the room.", to=room)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=10000)