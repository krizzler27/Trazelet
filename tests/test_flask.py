import time
from flask import Flask, jsonify, request, abort
from tracelet.integration.flask import FlaskMiddleware 
import tracelet

app = Flask(__name__)

# --- Middleware Registration ---
db_config = {} #! Setup Db Config before Running
tracelet.init(max_workers=2, enabled=True, db_config=db_config)
tracelet = FlaskMiddleware(app=app)

# --- Test Routes ---

@app.route("/")
def root():
    """Basic fast route to test SUCCESS status."""
    return jsonify({"message": "Tracelet is watching Flask"})

@app.route("/slow")
def slow_api():
    """Simulates a slow database or external API call (3 seconds)."""
    time.sleep(3)
    return jsonify({"status": "completed", "waited": "3s"})

@app.route("/error")
def trigger_error():
    """Simulates a failure to test FAILED status in metrics."""
    # Flask's way of raising HTTP exceptions
    abort(500, description="Simulated Server Crash")

@app.route("/not-found")
def not_found():
    """Simulates a 404 error."""
    abort(404, description="Resource missing")

@app.route("/items", methods=["POST"])
def create_item():
    """Tests POST request handling."""
    data = request.get_json()
    name = data.get("name", "Unknown")
    return jsonify({"message": f"Item {name} created", "data": data})

@app.route("/heavy-compute/<int:number>")
def compute(number):
    """
    Tests Normalization: 
    This should show up as /heavy-compute/<int:number> in your DB.
    """
    result = sum(i * i for i in range(number))
    return jsonify({"result": result})

if __name__ == "__main__":
    # Running on a different port than FastAPI to avoid conflict
    app.run(port=5001, debug=True)