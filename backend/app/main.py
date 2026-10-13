import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from app.api.routes import router
from app.api.settings import router as settings_router
from app.auth import auth_router, require_user, ensure_admin
from app.config import get_settings
from app.database import SessionLocal

async def schedule_loop():
    while True:
        await asyncio.sleep(60)
        try:
            from app.services.scheduler import tick
            await asyncio.to_thread(tick)
            from app.services.notifications import deliver
            await asyncio.to_thread(deliver)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Scheduled scan failed")

@asynccontextmanager
async def lifespan(app):
    if get_settings().auth_enabled:
        with SessionLocal() as db:
            ensure_admin(db)
    task=asyncio.create_task(schedule_loop()) if get_settings().job_mode=="local" else None
    yield
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

app=FastAPI(title="Cloud Infrastructure Optimizer",version="0.3.0",lifespan=lifespan,
            description="Cloud optimization, evidence-based advice, and approval-controlled execution.")
app.add_middleware(CORSMiddleware,allow_origins=get_settings().cors_origins.split(","),
    allow_methods=["GET","POST","PATCH"],allow_headers=["Content-Type","Authorization"])
app.include_router(auth_router)
app.include_router(router,dependencies=[Depends(require_user)])
app.include_router(settings_router,dependencies=[Depends(require_user)])

@app.exception_handler(HTTPException)
async def http_error(request:Request,exc:HTTPException):
    detail=exc.detail if isinstance(exc.detail,dict) else {"code":"http_error","message":str(exc.detail),"details":{}}
    return JSONResponse(status_code=exc.status_code,content={"error":detail})

@app.exception_handler(RequestValidationError)
async def validation_error(request:Request,exc:RequestValidationError):
    errors=[{"field":".".join(str(x) for x in e["loc"]),"message":e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422,content={"error":{"code":"validation_error","message":"Invalid request.","details":errors}})

# A production frontend build can be served by the same local process.
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
frontend_dist=Path(__file__).resolve().parents[2]/'frontend'/'dist'
if frontend_dist.exists():
    app.mount('/assets',StaticFiles(directory=frontend_dist/'assets'),name='assets')
    @app.get('/{path:path}',include_in_schema=False)
    def frontend_page(path:str):
        if path.startswith('api/') or path=='api':
            raise HTTPException(404,'API endpoint not found')
        return FileResponse(frontend_dist/'index.html')
