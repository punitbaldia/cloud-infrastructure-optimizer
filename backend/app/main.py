from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from app.api.routes import router
from app.config import get_settings

app=FastAPI(title='Cloud Infrastructure Optimizer',version='0.2.0',
            description='Local capstone demo. Mock data and simulated actions; authentication is not implemented.')
app.add_middleware(CORSMiddleware,allow_origins=get_settings().cors_origins.split(','),
                   allow_methods=['GET','POST'],allow_headers=['Content-Type'],allow_credentials=False)
app.include_router(router)

@app.exception_handler(HTTPException)
async def http_error(request:Request,exc:HTTPException):
    detail=exc.detail if isinstance(exc.detail,dict) else {'code':'http_error','message':str(exc.detail),'details':{}}
    return JSONResponse(status_code=exc.status_code,content={'error':detail})

@app.exception_handler(RequestValidationError)
async def validation_error(request:Request,exc:RequestValidationError):
    errors=[{'field':'.'.join(str(x) for x in e['loc']),'message':e['msg']} for e in exc.errors()]
    return JSONResponse(status_code=422,content={'error':{'code':'validation_error','message':'Invalid request.','details':errors}})

