from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, join_room, send
import json
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"
socketio = SocketIO(app)

ROOMS_FILE = "rooms.json"

def load_rooms():
    if os.path.exists(ROOMS_FILE):
        with open(ROOMS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_rooms(rooms):
    with open(ROOMS_FILE, "w") as f:
        json.dump(rooms, f)

@app.route("/", methods=["GET", "POST"])
def index():
    rooms = load_rooms()

    if request.method == "POST":
        action = request.form.get("action")
        username = request.form.get("username").strip()
        room = request.form.get("room").strip()
        password = request.form.get("password")

        if not username:
            return "Username required"

        if action == "create":
            if room in rooms:
                return "Room already exists"
            rooms[room] = password
            save_rooms(rooms)

        elif action == "join":
            if room not in rooms:
                return "Room does not exist"
            if rooms[room] != password:
                return "Wrong password"

        session["username"] = username
        session["room"] = room
        return redirect("/chat")

    # Para GET, mostrar la lista de salas en el joinForm
    return render_template("index.html", rooms=rooms.keys())

@app.route("/chat")
def chat():
    room = session.get("room")
    username = session.get("username")
    if not room or not username:
        return redirect("/")
    return render_template("chat.html", room=room, username=username)

@socketio.on("join")
def handle_join():
    room = session.get("room")
    username = session.get("username")
    join_room(room)
    send(f"{username} joined the room.", to=room)

@socketio.on("message")
def handle_message(msg):
    room = session.get("room")
    username = session.get("username")
    send(f"{username}: {msg}", to=room)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=10000)