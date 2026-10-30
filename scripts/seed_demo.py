"""Carga de demonstração local opcional, sem conexão externa."""
from app.database import SessionLocal,Base,engine
from app.models.entities import Customer
from app.services.message_seed import seed
from app.services.customer_service import consolidate
from app.services.schedule_service import approve_customer

users=[
 {'id':10001,'firstName':'Mariana','lastName':'Costa','age':25,'gender':'female','phone':'11988888888','address':{'state':'São Paulo'}},
 {'id':10002,'firstName':'Lucas','lastName':'Ribeiro','age':37,'gender':'male','phone':'11977777777','address':{'state':'Rio de Janeiro'}},
 {'id':10003,'firstName':'Patrícia','lastName':'Alves','age':42,'gender':'female','phone':'11966666666','address':{'state':'Minas Gerais'}},
]
# Dados pequenos e previsíveis permitem demonstrar o fluxo sem consultar a DummyJSON.
carts=[
 {'id':20001,'userId':10001,'total':'12450.50','products':[{'title':'Fones de ouvido','quantity':16}]},
 {'id':20002,'userId':10002,'total':'2500.00','products':[{'title':'Cafeteira','quantity':2}]}]

def main():
    """Cria tabelas, popula dados de exemplo e aprova uma campanha inicial."""
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed(session)
        if session.get(Customer,10001):
            print('Dados de demonstração já presentes.');return
        consolidate(session,users,carts)
        approve_customer(session,session.get(Customer,10001),['ALTO VALOR','COMPRA EM QUANTIDADE','PÚBLICO JOVEM'])
        session.commit()
        print('Exemplo carregado (3 clientes). Não substitui a importação DummyJSON.')

# Executa a carga apenas quando o arquivo é chamado diretamente como script.
if __name__=='__main__':main()
