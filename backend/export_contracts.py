"""Run from backend after installing dependencies."""
import json
from pathlib import Path
from app.main import app
from app.schemas import ResourceSnapshot, DailyCost, Recommendation, ExecutionJob, ExecutionRequest

target=Path(__file__).resolve().parents[1]/'contracts'
target.mkdir(exist_ok=True)
(target/'openapi.json').write_text(json.dumps(app.openapi(),indent=2),encoding='utf-8')
for model in (ResourceSnapshot,DailyCost,Recommendation,ExecutionJob,ExecutionRequest):
    (target/(model.__name__+'.schema.json')).write_text(json.dumps(model.model_json_schema(),indent=2),encoding='utf-8')
print('Exported OpenAPI and shared JSON schemas to contracts/')

