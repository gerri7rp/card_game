from flask import Flask, render_template, request, redirect
from flask_socketio import SocketIO, join_room, emit
import random
import requests

app = Flask(__name__)
app.secret_key = "supersecretkey"
socketio = SocketIO(app)

rooms = {}

# Game Utilities
def get_card_value(card):
    """Returns the numerical value of a card (A=14, K=13, Q=12, J=11, etc)"""
    value_map = {
        'ACE': 14, 'A': 14,
        'KING': 13, 'K': 13,
        'QUEEN': 12, 'Q': 12,
        'JACK': 11, 'J': 11,
        '10': 10, '0': 10
    }
    value = card['value']
    if value in value_map:
        return value_map[value]
    return int(value)

def get_card_suit(card):
    """Returns the suit of a card"""
    suit_map = {
        'SPADES': '♠', '♠': '♠',
        'HEARTS': '♥', '♥': '♥',
        'DIAMONDS': '♦', '♦': '♦',
        'CLUBS': '♣', '♣': '♣'
    }
    suit = card['suit']
    return suit_map.get(suit, suit)

def can_play_card(card, first_card_suit, hand, first_card_played):
    """Validates if a card can be played legally"""
    card_suit = get_card_suit(card)
    
    # If it's the first card of the round, it can always be played
    if not first_card_played:
        return True
    
    # If you have the suit that was played, you must play it
    hand_suits = [get_card_suit(c) for c in hand]
    if first_card_suit in hand_suits:
        return card_suit == first_card_suit or card_suit == '♠'  # O una pica
    
    # If you don't have the suit, you can play any card
    return True

def determine_round_winner(played_cards, first_card_suit):
    """Determines who wins the round based on cards played"""
    # played_cards = [{"player": username, "card": card}, ...]
    
    spades = [p for p in played_cards if get_card_suit(p["card"]) == '♠']
    if spades:
        # Highest spade wins
        winner = max(spades, key=lambda p: get_card_value(p["card"]))
        return winner["player"]
    
    # Highest card of the suit played wins
    same_suit = [p for p in played_cards if get_card_suit(p["card"]) == first_card_suit]
    if same_suit:
        winner = max(same_suit, key=lambda p: get_card_value(p["card"]))
        return winner["player"]
    
    # If no one played the suit or spades, the first player wins
    return played_cards[0]["player"]

def calculate_points(room_data):
    """Calculates and updates points based on predictions and rounds won"""
    for player in room_data["players"]:
        prediction = room_data["predictions"].get(player, 0)
        rounds_won = room_data["rounds_won"].get(player, 0)
        
        if rounds_won == prediction:
            # Correct: gains 10 + rounds predicted
            points_earned = 10 + prediction
        else:
            # Wrong
            if prediction > 0:
                # If predicted > 0: loses those points
                points_earned = -prediction
            else:
                # If predicted 0: loses 10 points
                points_earned = -10
        
        # Store round change for summary
        if "round_points_change" not in room_data:
            room_data["round_points_change"] = {}
        room_data["round_points_change"][player] = points_earned
        
        # Add points (minimum 0)
        room_data["points"][player] = max(0, room_data["points"][player] + points_earned)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        username = request.form.get("username").strip()
        room = request.form.get("room").strip()
        action = request.form.get("action")

        if not username or not room:
            return "Username and room required"

        if action == "create":
            if room in rooms:
                return "Room already exists"
            rooms[room] = {
                "players": [username],
                "creator": username,
                "game_started": False,
                "hands": {},
                "sids": {},  # {username: sid}
                "turn": None,
                "played_cards": [],
                "ready": {},
                "deck_id": None,
                "deck_remaining": 0,
                "game_phase": "waiting",  # waiting, cards_dealt, predicting, playing, finished
                "predictions": {},  # {username: num_rounds}
                "rounds_won": {},  # {username: count}
                "points": {},  # {username: total_points}
                "current_round": 0,
                "first_card_suit": None,
                "current_round_cards": [],
                "first_player": None,
                "cards_per_round": 4  # Número de cartas por ronda, decrece cada nivel
            }
        elif action == "join":
            if room not in rooms:
                return "Room does not exist"
            if len(rooms[room]["players"]) >= 2:
                return "Room full"
            rooms[room]["players"].append(username)

        return redirect(f"/game?username={username}&room={room}")

    return render_template("index.html", rooms=rooms.keys())

@app.route("/game")
def game():
    username = request.args.get("username")
    room = request.args.get("room")
    if not username or not room or room not in rooms:
        return redirect("/")
    room_data = rooms[room]
    return render_template("game.html", username=username, room=room, room_data=room_data)

@socketio.on("join")
def handle_join(data):
    room = data["room"]
    username = data["username"]
    if room not in rooms:
        emit("error", {"message": "Room does not exist"}, to=request.sid)
        return
    join_room(room)
    if username in rooms[room]["players"]:
        rooms[room]["sids"][username] = request.sid
    # Emitir notificación cuando alguien se une
    emit("player_joined", {"username": username, "players": rooms[room]["players"]}, to=room)
    emit("update", rooms[room], to=room)

@socketio.on("start_game")
def start_game(data):
    room = data["room"]
    username = data.get("username")
    room_data = rooms[room]
    if room_data["game_started"] or username not in room_data["players"]:
        return

    # Toggle ready state
    if username in room_data["ready"] and room_data["ready"][username]:
        room_data["ready"][username] = False
    else:
        room_data["ready"][username] = True
    
    ready_count = sum(1 for ready in room_data["ready"].values() if ready)
    total_players = len(room_data["players"])

    if ready_count == total_players and total_players >= 1:
        # Inicializar puntos solo la primera vez
        if not room_data.get("points"):
            room_data["points"] = {p: 0 for p in room_data["players"]}

        # Reset game round state for a new start
        room_data["predictions"] = {}
        room_data["rounds_won"] = {p: 0 for p in room_data["players"]}
        room_data["current_round"] = 0
        room_data["current_round_cards"] = []
        room_data["first_card_suit"] = None
        room_data["played_cards"] = []

        # Crear nuevo mazo y obtener cartas según el nivel actual
        cards_count = room_data["cards_per_round"] * 2
        response = requests.get(f"https://deckofcardsapi.com/api/deck/new/draw/?count={cards_count}")
        data_response = response.json()
        cards = data_response["cards"]
        room_data["deck_id"] = data_response["deck_id"]
        room_data["deck_remaining"] = data_response["remaining"]
        room_data["hands"][room_data["players"][0]] = cards[:room_data["cards_per_round"]]
        room_data["hands"][room_data["players"][1]] = cards[room_data["cards_per_round"]:]
        room_data["game_started"] = True
        room_data["game_phase"] = "cards_dealt"
        room_data["turn"] = room_data["creator"]
        room_data["first_player"] = room_data["creator"]

    emit("update", room_data, to=room)

@socketio.on("go_to_prediction")
def go_to_prediction(data):
    room = data["room"]
    room_data = rooms[room]
    room_data["game_phase"] = "predicting"
    room_data["rounds_won"] = {p: 0 for p in room_data["players"]}
    emit("update", room_data, to=room)

@socketio.on("make_prediction")
def make_prediction(data):
    room = data["room"]
    username = data["username"]
    rounds = data["rounds"]
    
    room_data = rooms[room]
    
    if rounds is None:
        # Cancelar predicción
        if username in room_data["predictions"]:
            del room_data["predictions"][username]
    else:
        rounds = int(rounds)
        if rounds < 0 or rounds > room_data["cards_per_round"]:
            return
        room_data["predictions"][username] = rounds
    
    # Si todos los jugadores han hecho su predicción, empieza el juego automáticamente
    if len(room_data["predictions"]) == len(room_data["players"]):
        room_data["game_phase"] = "playing"
        room_data["current_round"] = 1
        room_data["turn"] = room_data["first_player"]  # El primer jugador comienza
        room_data["rounds_won"] = {p: 0 for p in room_data["players"]}  # Inicializar rounds_won
    
    emit("update", room_data, to=room)

@socketio.on("play_card")
def play_card(data):
    room = data["room"]
    username = data["username"]
    card_code = data["card_code"]
    room_data = rooms[room]
    
    if room_data["game_phase"] != "playing" or room_data["turn"] != username:
        return
    
    # Obtener la carta
    card = next((c for c in room_data["hands"][username] if c["code"] == card_code), None)
    if not card:
        return
    
    # Validar que la carta se puede jugar
    first_card_played = len(room_data["current_round_cards"]) > 0
    if first_card_played:
        first_card_suit = room_data["first_card_suit"]
        if not can_play_card(card, first_card_suit, room_data["hands"][username], first_card_played):
            emit("error", {"message": "Debes seguir el palo si tienes cartas de ese palo."}, to=room_data["sids"].get(username))
            return  # Carta no válida
    else:
        # Primera carta de la ronda
        room_data["first_card_suit"] = get_card_suit(card)
    
    # Quitar carta de la mano
    room_data["hands"][username].remove(card)
    room_data["current_round_cards"].append({"player": username, "card": card})
    room_data["played_cards"].append({"player": username, "card": card})
    
    # Cambiar turno al otro jugador
    other_player = [p for p in room_data["players"] if p != username][0]
    
    # Si ambos jugadores han jugado, determinar ganador de la ronda
    if len(room_data["current_round_cards"]) == 2:
        winner = determine_round_winner(room_data["current_round_cards"], room_data["first_card_suit"])
        if winner not in room_data["rounds_won"]:
            room_data["rounds_won"][winner] = 0  # Inicializar si no existe
        room_data["rounds_won"][winner] += 1
        room_data["turn"] = winner  # El ganador empieza la siguiente ronda
        
        # Check if level is finished (all rounds played)
        if room_data["current_round"] == room_data["cards_per_round"]:
            # Calculate points for this level
            calculate_points(room_data)
            # Show round summary instead of immediately going to next level
            room_data["game_phase"] = "round_summary"
        else:
            room_data["current_round"] += 1
            room_data["current_round_cards"] = []
            room_data["first_card_suit"] = None
    else:
        room_data["turn"] = other_player
    
    emit("update", room_data, to=room)

@socketio.on("continue_game")
def continue_game(data):
    room = data["room"]
    room_data = rooms[room]
    
    if room_data["game_phase"] != "round_summary":
        return
    
    if room_data["cards_per_round"] > 1:
        # Move to next level with fewer cards
        room_data["cards_per_round"] -= 1
        room_data["current_round"] = 1
        room_data["rounds_won"] = {p: 0 for p in room_data["players"]}
        room_data["predictions"] = {}
        room_data["current_round_cards"] = []
        room_data["first_card_suit"] = None
        room_data["played_cards"] = []
        
        # Alternate who starts the next level
        current_first_player = room_data["first_player"]
        other_player = [p for p in room_data["players"] if p != current_first_player][0]
        room_data["first_player"] = other_player
        room_data["turn"] = room_data["first_player"]
        
        room_data["game_phase"] = "cards_dealt"
        # Deal new cards for the next level
        cards_count = room_data["cards_per_round"] * 2
        response = requests.get(f"https://deckofcardsapi.com/api/deck/new/draw/?count={cards_count}")
        data_response = response.json()
        cards = data_response["cards"]
        room_data["deck_id"] = data_response["deck_id"]
        room_data["deck_remaining"] = data_response["remaining"]
        room_data["hands"][room_data["players"][0]] = cards[:room_data["cards_per_round"]]
        room_data["hands"][room_data["players"][1]] = cards[room_data["cards_per_round"]:]
    else:
        room_data["game_phase"] = "finished"
    
    emit("update", room_data, to=room)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)