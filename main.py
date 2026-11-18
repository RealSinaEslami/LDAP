from contextlib import asynccontextmanager
from fastapi import FastAPI
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


@app.get('/health', tags=['Health'])
def health():
    return {'status': 'ok'}
