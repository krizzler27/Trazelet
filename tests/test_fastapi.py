import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from tracelet.integration.fastapi import FastAPIMiddleware 
import tracelet

db_config = {} #! Setup Db Config before Running
tracelet.init(max_workers=2, enabled=True, db_config=db_config)
app = FastAPI(title="Tracelet Test Suite")

# --- Middleware Registration ---
# This will wrap every request below
app.add_middleware(FastAPIMiddleware)

# --- Mock Data Models ---
class Item(BaseModel):
    name: str
    description: str | None = None
    price: float

# --- Test Routes ---

@app.get("/")
def root():
    """Basic fast route to test SUCCESS status."""
    return {"message": "Sentinel is watching"}

@app.get("/slow")
async def slow_api():
    """Simulates a slow database or external API call (3 seconds)."""
    await asyncio.sleep(3)
    return {"status": "completed", "waited": "3s"}

@app.get("/error")
def trigger_error():
    """Simulates a failure to test FAILED status in metrics."""
    raise HTTPException(status_code=500, detail="Simulated Server Crash")

@app.get("/not-found")
def not_found():
    """Simulates a 404 error."""
    raise HTTPException(status_code=404, detail="Resource missing")

@app.post("/items")
def create_item(item: Item):
    """Tests POST request handling."""
    return {"message": f"Item {item.name} created", "data": item}

@app.get("/heavy-compute/{number}")
def compute(number: int):
    """Simulates CPU-bound work to see how latency is tracked."""
    result = sum(i * i for i in range(number))
    return {"result": result}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)