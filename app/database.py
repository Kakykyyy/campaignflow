"""Configuração isolável do SQLite. Use DATABASE_URL para substituir em testes."""
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()
# ROOT permite que caminhos padrão funcionem independentemente do diretório atual.
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / 'data' / 'campaignflow.db'
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{DEFAULT_DB}')

class Base(DeclarativeBase):
    """Base comum para os modelos que o SQLAlchemy transforma em tabelas."""
    pass

def make_engine(url: str):
    """Cria a conexão do banco e ativa chaves estrangeiras quando for SQLite."""
    engine = create_engine(url, connect_args={'check_same_thread': False} if url.startswith('sqlite:') else {})
    if url.startswith('sqlite:'):
        @event.listens_for(engine, 'connect')
        def enable_foreign_keys(dbapi_connection, record):
            # SQLite não aplica chaves estrangeiras por padrão em algumas configurações.
            cursor = dbapi_connection.cursor()
            cursor.execute('PRAGMA foreign_keys=ON')
            cursor.close()
    return engine

# Engine é compartilhada; cada operação recebe sua própria sessão.
engine = make_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def get_db():
    """Dependência FastAPI: abre uma sessão por requisição e fecha ao final."""
    with SessionLocal() as session:
        yield session
