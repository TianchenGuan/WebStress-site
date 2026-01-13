"""
LLMOS Playground - Interactive Web OS Server

A FastAPI backend that wraps the LLMOS simulator, allowing humans to interact
with the simulated OS through a web interface.
"""

import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Add parent directory to path to import llmos
sys.path.insert(0, str(Path(__file__).parent.parent))

from llmos.core.simulator import Simulator

app = FastAPI(
    title="LLMOS Playground",
    description="Interactive web-based OS simulator",
    version="0.1.0",
)

# Global simulator instance
simulator: Optional[Simulator] = None


class ResetRequest(BaseModel):
    template: str = "desktop"
    instruction: str = ""
    difficulty: str = "easy"


class ActionRequest(BaseModel):
    action_type: str
    bid: Optional[str] = None
    text: Optional[str] = None
    key: Optional[str] = None
    button: Optional[str] = None
    direction: Optional[str] = None
    amount: Optional[int] = None
    url: Optional[str] = None
    options: Optional[list[str]] = None
    from_bid: Optional[str] = None
    to_bid: Optional[str] = None
    success: Optional[bool] = None


@app.post("/api/episode/reset")
async def reset_episode(request: ResetRequest):
    """Reset the simulator with a new episode."""
    global simulator

    try:
        simulator = Simulator(difficulty=request.difficulty)
        instruction = {"instruction": request.instruction} if request.instruction else None
        observation = simulator.reset(
            template_name=request.template,
            instruction=instruction,
        )
        return {
            "observation": observation,
            "tick": 0,
            "status": "running",
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Template not found: {request.template}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/episode/step")
async def step_episode(request: ActionRequest):
    """Execute an action and return the new state."""
    global simulator

    if simulator is None:
        raise HTTPException(status_code=400, detail="No episode started. Call /api/episode/reset first.")

    # Build action dict from request, excluding None values
    action = {"action_type": request.action_type}
    for field in ["bid", "text", "key", "button", "direction", "amount",
                  "url", "options", "from_bid", "to_bid", "success"]:
        value = getattr(request, field)
        if value is not None:
            action[field] = value

    try:
        observation, done, info = simulator.step(action)
        return {
            "observation": observation,
            "done": done,
            "info": info,
            "tick": simulator.current_state["meta"]["tick"] if simulator.current_state else 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/episode/state")
async def get_state():
    """Get the current observation."""
    global simulator

    if simulator is None:
        raise HTTPException(status_code=400, detail="No episode started. Call /api/episode/reset first.")

    return {
        "observation": simulator.get_observation(),
        "tick": simulator.current_state["meta"]["tick"] if simulator.current_state else 0,
        "status": simulator.current_state["meta"]["status"] if simulator.current_state else "unknown",
    }


@app.get("/api/episode/history")
async def get_history():
    """Get the action history for the current episode."""
    global simulator

    if simulator is None:
        raise HTTPException(status_code=400, detail="No episode started. Call /api/episode/reset first.")

    return {
        "history": simulator.get_history(),
    }


@app.get("/api/templates")
async def list_templates():
    """List available templates."""
    templates_dir = Path(__file__).parent.parent / "llmos" / "templates"
    templates = []

    if templates_dir.exists():
        for f in templates_dir.glob("*.json"):
            templates.append(f.stem)

    return {"templates": sorted(templates)}


# Serve static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def serve_index():
    """Serve the main HTML page."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="index.html not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("playground.server:app", host="0.0.0.0", port=8000, reload=True)
