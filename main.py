from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from config import ROOT
from database import Base, engine
from models.data_model import LDAPUser
from routers.data_router import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


app = FastAPI(title='HTG LDAP API', lifespan=lifespan)
app.include_router(router)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')


@app.get('/', include_in_schema=False)
def test_ui():
    return FileResponse(ROOT / 'static' / 'index.html')


@app.get('/health', tags=['Health'])
def health():
    return {'status': 'ok'}
