"""CampaignFlow - API e painel local para o teste técnico."""
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from app.database import Base, engine, SessionLocal
from app import models  # noqa
from app.models import entities  # noqa: F401
from app.services.message_seed import seed
from app.routers.pages import router

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s: %(message)s')

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Prepara o banco e os dados iniciais ao iniciar a aplicação."""
    # Cria as tabelas declaradas nos modelos sem apagar dados existentes.
    Base.metadata.create_all(bind=engine)
    # Garante que as mensagens padrão existam antes de atender requisições.
    with SessionLocal() as db: seed(db)
    yield

# O lifespan centraliza tarefas de inicialização e encerramento da aplicação.
app = FastAPI(title='CampaignFlow',version='1.0.0',description='Gestão de trilhas e simulação local de campanhas',lifespan=lifespan)
# A sessão guarda CSRF; em produção, configure SESSION_SECRET estável no ambiente.
app.add_middleware(SessionMiddleware,secret_key=os.getenv('SESSION_SECRET') or secrets.token_hex(32),same_site='lax',https_only=False)
# Arquivos estáticos (CSS e JavaScript) são servidos separadamente das rotas HTML.
app.mount('/static',StaticFiles(directory=Path(__file__).resolve().parent/'static'),name='static')
app.include_router(router)

@app.get('/health',tags=['Sistema'])
def health():
    """Endpoint simples para verificar se a aplicação está respondendo."""
    return {'status':'ok','delivery':'simulation-only'}
