from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import asyncio
import httpx
import time
from faker import Faker
from typing import Optional

app = FastAPI()

templates = Jinja2Templates(directory="templates")

fake = Faker(locale="zh_CN")

# shared state
_state = {
    "running": False,
    "total_requests": 0,
    "success": 0,
    "failure": 0,
    "total_time": 0.0,
    "start_time": None,
    "end_time": None,
    "last_response": None,  # store last response text/status
}

# task management
_tasks = []



@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/start")
async def start_test(concurrency: int = Form(...), duration: int = Form(...), target: str = Form(...)):
    if _state["running"]:
        return JSONResponse({"error": "test already running"}, status_code=400)

    # reset state
    _state.update({
        "running": True,
        "total_requests": 0,
        "success": 0,
        "failure": 0,
        "total_time": 0.0,
        "start_time": time.time(),
        "end_time": None,
        "last_response": None,
    })

    # cancel any leftover tasks
    global _tasks
    for t in _tasks:
        if not t.done():
            t.cancel()
    _tasks = []

    # start background job tasks
    loop = asyncio.get_event_loop()
    # create worker controller task
    controller = loop.create_task(_run_load(concurrency, duration, target))
    _tasks.append(controller)

    return {"status": "started"}


@app.get("/status")
async def status():
    running = _state["running"]
    elapsed = None
    if _state["start_time"]:
        elapsed = time.time() - _state["start_time"]
    avg_resp = None
    if _state["total_requests"] > 0:
        avg_resp = _state["total_time"] / _state["total_requests"]

    return {
        "running": running,
        "total_requests": _state["total_requests"],
        "success": _state["success"],
        "failure": _state["failure"],
        "average_response_time": avg_resp,
        "elapsed": elapsed,
        "last_response": _state.get("last_response"),
    }


async def _worker(client: httpx.AsyncClient, target: str, stop_at: float):
    # build url with random name
    try:
        name = fake.name()
        params = {"q": name}
        start = time.time()
        resp = await client.get(target, params=params, timeout=10.0)
        elapsed = time.time() - start
        _state["total_requests"] += 1
        _state["total_time"] += elapsed
        if 200 <= resp.status_code < 300:
            _state["success"] += 1
        else:
            _state["failure"] += 1
        # try to record last response text (shorten if too long)
        text = None
        try:
            text = resp.text
        except Exception:
            text = repr(resp.content)[:1000]
        _state["last_response"] = {"status_code": resp.status_code, "body": text[:2000]}
    except Exception:
        _state["total_requests"] += 1
        _state["failure"] += 1
        _state["last_response"] = {"status_code": None, "body": "exception"}


async def _run_load(concurrency: int, duration: int, target: str):
    end_time = time.time() + duration
    async with httpx.AsyncClient() as client:
        # spawn a fixed number of concurrent worker loops
        sem = asyncio.Semaphore(concurrency)

        async def loop_worker():
            while time.time() < end_time and _state["running"]:
                # run a single request then loop
                await _worker(client, target, end_time)
                # allow other tasks to run
                await asyncio.sleep(0)

        # create concurrency number of tasks
        workers = [asyncio.create_task(loop_worker()) for _ in range(concurrency)]
        # store tasks so they can be cancelled
        global _tasks
        _tasks.extend(workers)
        try:
            await asyncio.gather(*workers)
        except asyncio.CancelledError:
            # cancellation requested via /stop
            for w in workers:
                if not w.done():
                    w.cancel()
        finally:
            # ensure remaining tasks are cancelled
            for w in workers:
                if not w.done():
                    w.cancel()

    _state["running"] = False
    _state["end_time"] = time.time()


@app.post('/stop')
async def stop_test():
    if not _state["running"]:
        return JSONResponse({"status": "not running"}, status_code=400)
    _state["running"] = False
    # cancel tasks
    global _tasks
    for t in _tasks:
        if not t.done():
            t.cancel()
    _tasks = []
    _state["end_time"] = time.time()
    return {"status": "stopped"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
