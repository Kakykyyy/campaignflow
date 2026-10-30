"""Fixtures compartilhadas: banco isolado em memória e amostras determinísticas."""
import pytest
from datetime import date
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine, event
from app.database import Base
from app.models.entities import Customer
from app.services.message_seed import seed

@pytest.fixture
def db():
    """Fornece sessão SQLite nova por teste e limpa recursos ao final."""
    engine=create_engine('sqlite:///:memory:',connect_args={'check_same_thread':False},poolclass=StaticPool)
    @event.listens_for(engine,'connect')
    def fk(dbapi,record): dbapi.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    session=sessionmaker(bind=engine,expire_on_commit=False)()
    seed(session)
    yield session
    session.close();engine.dispose()

@pytest.fixture
def sample_users():
    """Perfis de clientes usados pelos testes de consolidação e classificação."""
    return [
        {'id':1,'firstName':'Ana','lastName':'Silva','age':24,'gender':'female','phone':'(11) 99999-9999','address':{'state':'São Paulo'}},
        {'id':2,'firstName':'Bruno','lastName':'Lima','age':44,'gender':'male','phone':'11988887777','address':{'state':'Rio de Janeiro'}},
        {'id':3,'firstName':'Carla','lastName':'Souza','age':30,'gender':'female','phone':'11977776666','address':{'state':'São Paulo'}}]

@pytest.fixture
def sample_carts():
    """Carrinhos com múltiplos produtos para testar soma de valores e quantidades."""
    return [
        {'id':100,'userId':1,'total': '6500.05','totalProducts':2,'totalQuantity':9,'products':[{'title':'A','quantity':8},{'title':'B','quantity':1}]},
        {'id':101,'userId':1,'total':'3999.95','totalProducts':1,'totalQuantity':7,'products':[{'title':'C','quantity':7}]},
        {'id':102,'userId':2,'total':'1500','totalProducts':1,'totalQuantity':2,'products':[{'title':'D','quantity':2}]}]
