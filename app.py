from dataclasses import fields
import json
import logging 
import time


from fastapi  import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor


app = FastAPI(title="Todo API")


# ---------TRACING --------------
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)


#--------- Logs structuré -------------
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("api")



#enregistre logs en ajoutant auto trace_id de la requete en cours
def log_event(level, message, **fields):
    ctx = trace.get_current_span().get_span_context()
    fields["trace_id"] = format(ctx.trace_id, "032x")
    logger.log(level, json.dumps({"message": message, **fields}))


# --------- METRIQUES ----------------
REQUESTS = Counter("http_requests_total", "Total requests", ["method", "endpoint", "status"])
LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["endpoint"])

#--middleware pour observer les requetes et les erreurs
@app.middleware("http")
async def observe(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request) #asynchrone
    except Exception as e:
        log_event(logging.ERROR, "unhandled_error", error=str(e))
        response = JSONResponse({"error": "internal server error"}, status_code=500)
    duration = time.time() - start
    route = request.scope.get("route")
    endpoint = route.path if route else "unknown"
    REQUESTS.labels(
        request.method,
        endpoint,
        response.status_code
    ).inc()
    LATENCY.labels(endpoint).observe(duration)
    log_event(
        logging.INFO,
          "request",
            method=request.method,
              path=request.url.path,
              status=response.status_code,
                duration_ms=round(duration * 1000, 2)
                )
    return response

#on active le tracing OpenTelemetry pour FastAPI
FastAPIInstrumentor.instrument_app(app)

# ---------------API --------------------

class TaskIn(BaseModel):
    title: str =  Field(min_length=1)


tasks = {}
next_id = 1

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/tasks")
def list_tasks():
    return list(tasks.values())


@app.post("/tasks", status_code=201)
def create_task(data: TaskIn):
    global next_id
    task = {"id": next_id, "title": data.title, "done": False}
    tasks[next_id] = task
    next_id += 1
    return task

@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="not found")
    return tasks[task_id]


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int):
    if tasks.pop(task_id, None) is None:
        raise HTTPException(status_code=404, detail="not found")
    return Response(status_code=204)


