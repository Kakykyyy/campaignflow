"""Testa páginas, APIs de leitura e proteção CSRF usando o cliente FastAPI."""
from datetime import date, datetime
import csv
import io
import json
from urllib.parse import unquote
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from app.services.customer_service import consolidate
from app.models.entities import Customer, ImportRun, ScheduledMessage, Simulation
from app.services.clock import today
from app.services.schedule_service import approve_customer, set_weekday
from app.services import whatsapp_service
from app.services.whatsapp_service import simulate_today

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
        detail=client.get('/clientes/1').text
        assert 'Jornada da campanha' in detail
        assert 'SEMANA ATUAL' in detail
        assert '1 de 6' in detail
        assert 'Próxima trilha:' in detail
        assert 'Mensagem 1 de 3' in client.get('/cronograma').text or '1 / 3' in client.get('/cronograma').text
    app.dependency_overrides.clear()

def test_history_filters_and_csv_export(db,sample_users,sample_carts,monkeypatch):
    monkeypatch.setenv('WHATSAPP_API_TOKEN','ENV-ONLY-SECRET')
    consolidate(db,sample_users,sample_carts)
    approve_customer(db,db.get(Customer,1),['ALTO VALOR'],start_date=date(2026,11,2))
    approve_customer(db,db.get(Customer,2),['GERAL'],start_date=date(2026,11,2))
    db.flush()
    ana_schedule=db.query(ScheduledMessage).filter_by(customer_id=1,track='ALTO VALOR',number=1).one()
    bruno_schedule=db.query(ScheduledMessage).filter_by(customer_id=2,track='GERAL',number=1).one()
    ana_schedule.status=bruno_schedule.status='SIMULADO'
    bruno_schedule.scheduled_date=date(2026,11,9)
    db.add_all([
        Simulation(scheduled_id=ana_schedule.id,customer_id=1,track='ALTO VALOR',number=1,
                   content='=1+1',simulated_at=datetime(2026,11,4,12),endpoint='https://example.test',
                   method='POST',headers={'access-token':'TOP-SECRET-VERY-PRIVATE',
                                          'Authorization':'Bearer TOP-SECRET-VERY-PRIVATE'},
                   payload={'chat':{'channelId':'<CONFIGURAR_CHANNEL_ID>','contactId':'5511999999999'},
                            'messages':[{'text':'=1+1 ENV-ONLY-SECRET'}]},status='SIMULADO'),
        Simulation(scheduled_id=bruno_schedule.id,customer_id=2,track='GERAL',number=1,
                   content='Olá, Bruno!',simulated_at=datetime(2026,11,9,12),endpoint='https://example.test',
                   method='POST',headers={'access-token':'[OCULTO]'},
                   payload={'chat':{'channelId':'bot-channel-01','contactId':'5511988887777'},
                            'messages':[{'text':'Olá, Bruno!'}]},status='SIMULADO'),
    ])
    db.commit()
    filters={'q':'Ana','start':'2026-11-04','end':'2026-11-04','track':'ALTO VALOR','status':'SIMULADO'}
    with client_for(db) as client:
        page=client.get('/historico',params=filters)
        assert page.status_code==200
        assert 'Ana Silva' in page.text
        assert 'Bruno Lima' not in page.text
        exported=client.get('/historico.csv',params=filters)
        assert exported.status_code==200
        assert 'attachment; filename="campaignflow-historico.csv"' in exported.headers['content-disposition']
        assert exported.content.startswith(b'\xef\xbb\xbf')
        csv_text=exported.content.decode('utf-8-sig')
        assert 'Ana Silva' in csv_text
        assert 'Bruno Lima' not in csv_text
        assert "'=1+1" in csv_text
        assert '[OCULTO]' in csv_text
        assert 'TOP-SECRET-VERY-PRIVATE' not in csv_text
        assert 'ENV-ONLY-SECRET' not in csv_text
        reader=csv.reader(io.StringIO(csv_text))
        rows=list(reader)
        assert len(rows[0])==15
        assert rows[0][:11]==[
            'ID','Cliente','Telefone','Trilha','Mensagem','Data e hora','Endpoint','Método',
            'Cabeçalhos','Corpo JSON','Status'
        ]
        assert rows[0][11:]==[
            'Número da mensagem','Data prevista','Canal Botmaker','Requisição JSON'
        ]
        assert rows[1][10:14]==['SIMULADO','1','2026-11-02','PLACEHOLDER']
        assert rows[1][5].startswith('2026-11-04')
        assert rows[1][9].count('=1+1')==1
        request_json=json.loads(rows[1][14])
        assert request_json=={
            'endpoint':'https://example.test','method':'POST',
            'headers':{'access-token':'[OCULTO]','Authorization':'[OCULTO]'},
            'body':{
                'chat':{'channelId':'<CONFIGURAR_CHANNEL_ID>','contactId':'5511999999999'},
                'messages':[{'text':'=1+1 [OCULTO]'}],
            },
        }
        all_rows=list(csv.reader(io.StringIO(client.get('/historico.csv').content.decode('utf-8-sig'))))
        assert [row[13] for row in all_rows[1:]]==['PLACEHOLDER','CONFIGURADO']
        assert client.get('/historico',params={'start':'data-invalida'}).status_code==400
    app.dependency_overrides.clear()

def test_history_csv_rejects_simulation_mismatched_to_schedule(db,sample_users,sample_carts):
    consolidate(db,sample_users,sample_carts)
    approve_customer(db,db.get(Customer,1),['ALTO VALOR'],start_date=date(2026,11,2))
    schedule=db.query(ScheduledMessage).filter_by(customer_id=1,number=1).one()
    schedule.status='SIMULADO'
    db.add(Simulation(scheduled_id=schedule.id,customer_id=1,track='INCENTIVO',number=1,
                      content='Mensagem inválida',simulated_at=datetime(2026,11,2,12),
                      endpoint='https://example.test',method='POST',headers={},payload={},status='SIMULADO'))
    db.commit()
    with client_for(db) as client:
        response=client.get('/historico.csv')
        assert response.status_code==409
    app.dependency_overrides.clear()

def test_history_csv_rejects_simulation_before_scheduled_date(db,sample_users,sample_carts):
    consolidate(db,sample_users,sample_carts)
    approve_customer(db,db.get(Customer,1),['ALTO VALOR'],start_date=date(2026,11,2))
    schedule=db.query(ScheduledMessage).filter_by(customer_id=1,number=1).one()
    schedule.status='SIMULADO'
    db.add(Simulation(scheduled_id=schedule.id,customer_id=1,track=schedule.track,number=schedule.number,
                      content='Mensagem',simulated_at=datetime(2026,11,1,12),
                      endpoint='https://example.test',method='POST',headers={},payload={},status='SIMULADO'))
    db.commit()
    with client_for(db) as client:
        assert client.get('/historico.csv').status_code==409
    app.dependency_overrides.clear()

def test_import_to_simulation_and_history_flow(db,sample_users,sample_carts,monkeypatch):
    from app.routers import pages
    monkeypatch.setattr(pages,'extract',lambda:(sample_users,sample_carts,['users.json','carts.json']))
    scheduled_dates=[]
    def simulate_next_scheduled_date(session):
        run_date=scheduled_dates.pop(0) if scheduled_dates else scheduled_dates_last
        monkeypatch.setattr(whatsapp_service,'now',lambda:datetime.combine(run_date,datetime.min.time()))
        return simulate_today(session,run_date=run_date)
    scheduled_dates_last=today()
    monkeypatch.setattr(pages,'simulate_today',simulate_next_scheduled_date)
    with client_for(db) as client:
        from bs4 import BeautifulSoup
        dashboard=BeautifulSoup(client.get('/').text,'html.parser')
        csrf=dashboard.select_one('form[action="/import"] input[name="csrf_token"]')['value']
        db.rollback()
        imported=client.post('/import',data={'csrf_token':csrf},follow_redirects=False)
        assert imported.status_code==303
        assert '3 clientes e 3 carrinhos' in unquote(imported.headers['location'])
        ana=db.get(Customer,1)
        assert [item.track for item in ana.suggestions]==[
            'ALTO VALOR','COMPRA EM QUANTIDADE','PÚBLICO JOVEM'
        ]

        set_weekday(db,today().weekday())
        db.commit()
        customer_page=BeautifulSoup(client.get('/clientes/1').text,'html.parser')
        csrf=customer_page.select_one('form[action="/clientes/1/aprovar"] input[name="csrf_token"]')['value']
        approved=client.post('/clientes/1/aprovar',data={
            'csrf_token':csrf,
            'tracks':['ALTO VALOR','COMPRA EM QUANTIDADE','PÚBLICO JOVEM'],
        },follow_redirects=False)
        assert approved.status_code==303
        assert db.get(Customer,1).approved
        schedules=db.query(ScheduledMessage).filter(ScheduledMessage.customer_id==1).order_by(
            ScheduledMessage.scheduled_date).all()
        assert len(schedules)==9
        assert [(row.track,row.number) for row in schedules]==[
            (track,number) for track in ('ALTO VALOR','COMPRA EM QUANTIDADE','PÚBLICO JOVEM')
            for number in (1,2,3)
        ]
        scheduled_dates.extend(row.scheduled_date for row in schedules)

        for _ in schedules:
            schedule_page=BeautifulSoup(client.get('/cronograma').text,'html.parser')
            csrf=schedule_page.select_one('form[action="/simulate"] input[name="csrf_token"]')['value']
            simulated=client.post('/simulate',data={'csrf_token':csrf},follow_redirects=False)
            assert simulated.status_code==303
        history=client.get('/historico')
        assert history.status_code==200
        assert 'Ana Silva' in history.text
        assert db.query(Simulation).count()==9
        exported=client.get('/historico.csv')
        export_rows=list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig'))))
        assert len(export_rows)==10
        assert [(row[3],int(row[11])) for row in export_rows[1:]]==[
            (track,number) for track in ('ALTO VALOR','COMPRA EM QUANTIDADE','PÚBLICO JOVEM')
            for number in (1,2,3)
        ]
        assert [row[12] for row in export_rows[1:]]==[
            row.scheduled_date.isoformat() for row in schedules
        ]
        final_page=BeautifulSoup(client.get('/cronograma').text,'html.parser')
        csrf=final_page.select_one('form[action="/simulate"] input[name="csrf_token"]')['value']
        client.post('/simulate',data={'csrf_token':csrf},follow_redirects=False)
        assert db.query(Simulation).count()==9
    app.dependency_overrides.clear()
