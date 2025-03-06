import asyncio
import json
import websockets
import uuid
import random

# Game state
players = {}
obstacles = []
fish = []
game_started = False

# Level configurations
levels = [
    {"name": "Ocean", "background": "#0077be", "transitionPoint": 5000},
    {"name": "Coast", "background": "#4682B4", "transitionPoint": 10000},
    {"name": "River Mouth", "background": "#5F9EA0", "transitionPoint": 15000},
    {"name": "Amazon River", "background": "#008080", "transitionPoint": float('inf')}
]

# Game settings
CANVAS_WIDTH = 1200  # Default canvas width
CANVAS_HEIGHT = 800  # Default canvas height
TICK_RATE = 50  # Server updates per second

async def register_player(websocket):
    """Register a new player and create their whale"""
    player_id = str(uuid.uuid4())
    color = "#{:06x}".format(random.randint(0, 0xFFFFFF))
    
    # Create a new whale for this player
    players[player_id] = {
        "id": player_id,
        "websocket": websocket,
        "whale": {
            "x": 100,
            "y": 300 + random.randint(-100, 100),  # Randomize starting position a bit
            "width": 80,
            "height": 40,
            "speed": 15,  # Increased from 5 to 7.5 (1.5x faster)
            "health": 100,
            "color": color
        },
        "score": 0,
        "level": "Ocean",
        "levelIndex": 0,
        "distance": 0,
        "isGameOver": False,
        "isGameWon": False
    }
    
    return player_id

def generate_obstacles():
    """Generate obstacles for the game"""
    global obstacles
    obstacles = []
    
    for i in range(20):
        obstacles.append({
            "id": str(uuid.uuid4()),
            "x": random.random() * CANVAS_WIDTH + CANVAS_WIDTH,
            "y": random.random() * CANVAS_HEIGHT,
            "width": 30 + random.random() * 50,
            "height": 30 + random.random() * 50,
            "speed": 2 + random.random() * 3,
            "color": "#964B00"  # Brown color for obstacles
        })

def generate_fish():
    """Generate fish for the game"""
    global fish
    fish = []
    
    for i in range(15):
        # Regular fish
        fish.append({
            "id": str(uuid.uuid4()),
            "x": random.random() * CANVAS_WIDTH + CANVAS_WIDTH,
            "y": random.random() * CANVAS_HEIGHT,
            "width": 20,
            "height": 10,
            "speed": 3 + random.random() * 2,
            "color": "#FFA500",  # Orange color for fish
            "type": "regular"
        })
    
    # Add special speed boost fish (blue fish)
    for i in range(3):
        fish.append({
            "id": str(uuid.uuid4()),
            "x": random.random() * CANVAS_WIDTH + CANVAS_WIDTH,
            "y": random.random() * CANVAS_HEIGHT,
            "width": 25,  # Slightly bigger
            "height": 15,
            "speed": 5 + random.random() * 3,  # Faster fish
            "color": "#00BFFF",  # Deep Sky Blue color for speed boost fish
            "type": "speed_boost",
            "duration": 5  # Speed boost duration in seconds
        })

def check_collision(obj1, obj2):
    """Check if two objects are colliding"""
    return (obj1["x"] < obj2["x"] + obj2["width"] and
            obj1["x"] + obj1["width"] > obj2["x"] and
            obj1["y"] < obj2["y"] + obj2["height"] and
            obj1["y"] + obj1["height"] > obj2["y"])

# In the game_loop function, update the obstacle collision handling
async def game_loop():
    """Main game loop that updates game state"""
    global game_started, obstacles, fish
    
    if not game_started:
        return
    
    # Update obstacles
    for obstacle in obstacles:
        obstacle["x"] -= obstacle["speed"]
        
        # Check collisions with all whales
        for player_id, player in players.items():
            if not player["isGameOver"] and check_collision(player["whale"], obstacle):
                player["whale"]["health"] -= 10
                
                # Apply slowdown effect
                if "original_speed" not in player["whale"]:  # Don't stack slowdown effects
                    player["whale"]["original_speed"] = player["whale"]["speed"]
                    player["whale"]["speed"] /= 1.5  # 1.5x slower
                    player["whale"]["slowdown_end_time"] = asyncio.get_event_loop().time() + 2  # 2 seconds duration
                
                obstacle["x"] = CANVAS_WIDTH + random.random() * 500
                obstacle["y"] = random.random() * CANVAS_HEIGHT
                
                # Check if player is now dead
                if player["whale"]["health"] <= 0:
                    player["isGameOver"] = True
                    await notify_game_over(player_id)
        
        # Reset obstacle if it goes off screen
        if obstacle["x"] + obstacle["width"] < 0:
            obstacle["x"] = CANVAS_WIDTH + random.random() * 200
            obstacle["y"] = random.random() * CANVAS_HEIGHT
    
    # Update fish
    for fish_obj in fish:
        fish_obj["x"] -= fish_obj["speed"]
        
        # Check collisions with all whales
        for player_id, player in players.items():
            if not player["isGameOver"] and check_collision(player["whale"], fish_obj):
                # Handle different fish types
                if fish_obj["type"] == "regular":
                    player["score"] += 100
                    player["whale"]["health"] = min(player["whale"]["health"] + 5, 100)
                elif fish_obj["type"] == "speed_boost":
                    player["score"] += 200
                    # Apply speed boost - store original speed and set boost end time
                    if "original_speed" not in player["whale"]:
                        player["whale"]["original_speed"] = player["whale"]["speed"]
                        player["whale"]["speed"] *= 3  # 3x speed boost
                        player["whale"]["boost_end_time"] = asyncio.get_event_loop().time() + fish_obj["duration"]
                
                # Reset fish position
                fish_obj["x"] = CANVAS_WIDTH + random.random() * 500
                fish_obj["y"] = random.random() * CANVAS_HEIGHT
                
                # Check for level transition
                if player["score"] >= levels[player["levelIndex"]]["transitionPoint"] and player["levelIndex"] < len(levels) - 1:
                    player["levelIndex"] += 1
                    player["level"] = levels[player["levelIndex"]]["name"]
                
                # Check if player won
                if player["levelIndex"] == len(levels) - 1 and player["score"] >= 20000:
                    player["isGameWon"] = True
                    await notify_game_won(player_id)
        
        # Reset fish if it goes off screen
        if fish_obj["x"] + fish_obj["width"] < 0:
            fish_obj["x"] = CANVAS_WIDTH + random.random() * 200
            fish_obj["y"] = random.random() * CANVAS_HEIGHT
    
    # Check for speed boost and slowdown expiration
    current_time = asyncio.get_event_loop().time()
    for player_id, player in players.items():
        if not player["isGameOver"]:
            # Check for speed boost expiration
            if "boost_end_time" in player["whale"] and current_time >= player["whale"]["boost_end_time"]:
                # Reset speed to original
                player["whale"]["speed"] = player["whale"]["original_speed"]
                del player["whale"]["original_speed"]
                del player["whale"]["boost_end_time"]
            
            # Check for slowdown expiration
            elif "slowdown_end_time" in player["whale"] and current_time >= player["whale"]["slowdown_end_time"]:
                # Reset speed to original
                player["whale"]["speed"] = player["whale"]["original_speed"]
                del player["whale"]["original_speed"]
                del player["whale"]["slowdown_end_time"]
    
    # Increment score and distance for all active players
    for player_id, player in players.items():
        if not player["isGameOver"] and not player["isGameWon"]:
            player["score"] += 1
            
            # Update distance based on level and current speed
            # Higher levels mean the player has traveled further
            distance_multiplier = player["levelIndex"] + 1
            
            # Calculate speed factor - slower when slowed down, faster with speed boost
            speed_factor = 1.0
            if "slowdown_end_time" in player["whale"]:
                speed_factor = 0.67  # 1/1.5 for slowdown effect
            elif "boost_end_time" in player["whale"]:
                speed_factor = 3.0   # 3x for speed boost
                
            player["distance"] += 0.01 * distance_multiplier * speed_factor
            
            # Check for level transition based on distance
            if player["levelIndex"] < len(levels) - 1 and player["distance"] >= levels[player["levelIndex"]]["transitionPoint"] / 50:
                player["levelIndex"] += 1
                player["level"] = levels[player["levelIndex"]]["name"]
    
    # Send updated game state to all players
    await broadcast_game_state()

async def notify_game_over(player_id):
    """Notify a player that they lost"""
    player = players[player_id]
    await player["websocket"].send(json.dumps({
        "type": "gameOver",
        "score": player["score"]
    }))

async def notify_game_won(player_id):
    """Notify a player that they won"""
    player = players[player_id]
    await player["websocket"].send(json.dumps({
        "type": "gameWon",
        "score": player["score"]
    }))

async def broadcast_game_state():
    """Send current game state to all connected players"""
    # Create a simplified game state to send to clients
    game_state = {
        "players": {},
        "obstacles": obstacles,
        "fish": fish
    }
    
    # Add player data without the websocket object
    for player_id, player in players.items():
        game_state["players"][player_id] = {
            "id": player_id,
            "whale": player["whale"],
            "score": player["score"],
            "level": player["level"],
            "levelIndex": player["levelIndex"],
            "distance": player["distance"],
            "health": player["whale"]["health"],
            "isGameOver": player["isGameOver"],
            "isGameWon": player["isGameWon"]
        }
    
    # Send to all connected players
    for player_id, player in players.items():
        try:
            await player["websocket"].send(json.dumps({
                "type": "gameState",
                "state": game_state,
                "yourId": player_id
            }))
        except websockets.exceptions.ConnectionClosed:
            pass  # Player disconnected

async def handle_message(websocket, message):
    """Handle incoming messages from clients"""
    data = json.loads(message)
    player_id = data.get("playerId")
    
    if data["type"] == "join":
        # New player joining
        player_id = await register_player(websocket)
        await websocket.send(json.dumps({
            "type": "joined",
            "playerId": player_id
        }))
        
        # If this is the first player, start the game
        global game_started
        if len(players) == 1 and not game_started:
            game_started = True
            generate_obstacles()
            generate_fish()
    
    elif data["type"] == "move" and player_id in players:
        # Player movement
        direction = data.get("direction")
        player = players[player_id]
        
        if direction == "up" and player["whale"]["y"] > 0:
            player["whale"]["y"] -= player["whale"]["speed"]
        elif direction == "down" and player["whale"]["y"] < CANVAS_HEIGHT - player["whale"]["height"]:
            player["whale"]["y"] += player["whale"]["speed"]
        elif direction == "left" and player["whale"]["x"] > 0:
            player["whale"]["x"] -= player["whale"]["speed"]
        elif direction == "right" and player["whale"]["x"] < CANVAS_WIDTH - player["whale"]["width"]:
            player["whale"]["x"] += player["whale"]["speed"]

async def handle_connection(websocket):
    """Handle a new WebSocket connection"""
    try:
        async for message in websocket:
            await handle_message(websocket, message)
    except websockets.exceptions.ConnectionClosed:
        # Remove player when they disconnect
        for player_id, player in list(players.items()):
            if player["websocket"] == websocket:
                del players[player_id]
                break

async def main():
    """Start the WebSocket server and game loop"""
    import os
    
    # Get port from environment variable (for Render.com) or use default
    port = int(os.environ.get("PORT", 8765))
    
    try:
        # Listen on all interfaces (0.0.0.0) instead of just localhost
        server = await websockets.serve(handle_connection, "0.0.0.0", port)
        print(f"Game server started successfully on port {port}")
        
        # Run the game loop at a fixed tick rate
        while True:
            await game_loop()
            await asyncio.sleep(1 / TICK_RATE)
    except Exception as e:
        print(f"Error starting server: {e}")

if __name__ == "__main__":
    # Start the server
    print("Game server starting...")
    asyncio.run(main())