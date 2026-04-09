from flask import Flask, render_template, request, redirect
from flask_socketio import SocketIO, join_room, emit
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

        # Pasamos username y room a la URL
        return redirect(f"/chat?username={username}&room={room}")

    return render_template("index.html", rooms=rooms.keys())

@app.route("/chat")
def chat():
    username = request.args.get("username")
    room = request.args.get("room")
    if not username or not room:
        return redirect("/")
    return render_template("chat.html", username=username, room=room)

# Evento cuando alguien se une
@socketio.on("join")
def handle_join(data):
    room = data["room"]
    username = data["username"]
    join_room(room)
    emit("message", f"{username} joined the room.", to=room, broadcast=True)

# Evento cuando alguien envía un mensaje
@socketio.on("message")
def handle_message(data):
    room = data["room"]
    username = data["username"]
    msg = data["msg"]
    emit("message", f"{username}: {msg}", to=room, broadcast=True)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=10000)