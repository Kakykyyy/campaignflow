"""Testa páginas, APIs de leitura e proteção CSRF usando o cliente FastAPI."""
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from app.services.customer_service import consolidate
from app.models.entities import Customer, ImportRun
from app.services.schedule_service import approve_customer

def client_for(db):
    """Substitui a dependência de banco para apontar ao SQLite isolado do teste."""
    def override():yield db
    app.dependency_overrides[get_db]=override
    return TestClient(app)

def test_dashboard_and_routes(db,sample_users,sample_carts):
    consolidate(db,sample_users,sample_carts);db.commit()
    db.add(ImportRun(users=3,carts=3,user_file='users.json',cart_file='carts.json'))
    db.commit()
    with client_for(db) as client:
        for url in ('/','/clientes','/clientes/1','/cronograma','/historico','/configuracoes','/health','/api/indicadores','/docs'):
            response=client.get(url)
            assert response.status_code==200,(url,response.text[:300])
        dashboard=client.get('/').text
        assert 'Última extração' in dashboard
        assert 'users.json' not in dashboard
        assert 'CONCLUÍDA EM' in dashboard
        assert 'Ana Silva' in client.get('/clientes').text
        assert '3' == str(client.get('/api/indicadores').json()['clientes'])
    app.dependency_overrides.clear()

def test_form_requires_csrf(db):
    with client_for(db) as client:
        response=client.post('/classify',data={'csrf_token':'invalid'},follow_redirects=False)
        assert response.status_code==403
    app.dependency_overrides.clear()

def test_approval_via_web_form(db,sample_users,sample_carts):
    consolidate(db,sample_users,sample_carts);db.commit()
    with client_for(db) as client:
        client.get('/clientes/1')
        token=client.cookies.get('session')
        assert token
        from itsdangerous import TimestampSigner
        # CSRF token aparece no HTML e não requer acessar segredos de sessão.
        from bs4 import BeautifulSoup
        html=client.get('/clientes/1').text
        soup=BeautifulSoup(html,'html.parser')
        csrf=soup.select_one('input[name=csrf_token]')['value']
        response=client.post('/clientes/1/aprovar',data={'csrf_token':csrf,'tracks':['ALTO VALOR','PÚBLICO JOVEM']},follow_redirects=False)
        assert response.status_code==303
        assert db.get(Customer,1).approved
        assert 'Mensagem 1 de 3' in client.get('/cronograma').text or '1 / 3' in client.get('/cronograma').text
    app.dependency_overrides.clear()
