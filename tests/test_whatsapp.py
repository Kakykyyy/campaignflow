"""Confere formatação e personalização sem permitir chamadas de envio externas."""
from datetime import date, datetime
from sqlalchemy import select
import pytest
from app.models.entities import Customer,ScheduledMessage,Simulation
from app.services.customer_service import consolidate
from app.services.schedule_service import approve_customer
from app.services.whatsapp_service import (
    ENDPOINT,
    LEGACY_ENDPOINT,
    build_request,
    format_phone,
    migrate_legacy_simulations,
    personalize,
    simulate_today,
)

@pytest.mark.parametrize('raw,expected',[
    ('11999999999','5511999999999'),('(11) 99999-9999','5511999999999'),
    ('+55 (11) 99999-9999','5511999999999'),('5511999999999','5511999999999'),('+81 965-431-3024','819654313024')])
def test_phones(raw,expected): assert format_phone(raw)==expected

@pytest.mark.parametrize('raw',['','000','abc','1199999999999999999'])
def test_invalid_phones(raw):
    with pytest.raises(ValueError):format_phone(raw)

def test_personalization():assert personalize('Olá, {nome}!','Ana Silva')=='Olá, Ana!'

def test_request_matches_botmaker_openapi_and_reads_token_from_environment(monkeypatch):
    monkeypatch.setenv('WHATSAPP_API_TOKEN','TOP-SECRET-VERY-PRIVATE')
    result=build_request('11999999999','Oi, Ana!','channel-1')
    assert result['endpoint']=='https://api.botmaker.com/v2.0/chats-actions/send-messages'
    assert result['method']=='POST'
    assert result['headers']=={
        'Content-Type':'application/json',
        'access-token':'TOP-SECRET-VERY-PRIVATE',
    }
    assert result['body']=={
        'chat':{'channelId':'channel-1','contactId':'5511999999999'},
        'messages':[{'text':'Oi, Ana!'}],
    }

def test_request_without_token_uses_configuration_marker(monkeypatch):
    monkeypatch.delenv('WHATSAPP_API_TOKEN',raising=False)
    result=build_request('11999999999','Oi, Ana!','channel-1')
    assert result['headers']['access-token']=='<CONFIGURAR WHATSAPP_API_TOKEN>'

def test_legacy_simulation_metadata_is_migrated_without_changing_history(db):
    db.add(Customer(id=1,name='Ana Silva',age=30))
    db.add(ScheduledMessage(
        id=1,
        customer_id=1,
        track='INCENTIVO',
        number=1,
        scheduled_date=date(2026,11,2),
        status='SIMULADO',
    ))
    db.flush()
    simulation=Simulation(
        scheduled_id=1,
        customer_id=1,
        track='INCENTIVO',
        number=1,
        content='Oi, Ana!',
        simulated_at=datetime(2026,10,30,12,0,0),
        endpoint=LEGACY_ENDPOINT,
        method='POST',
        headers={'Content-Type':'application/json','access-token':'[OCULTO]'},
        payload={
            'channelId':'channel-1',
            'contactId':'5511999999999',
            'message':{'text':'Oi, Ana!'},
        },
        status='SIMULADO',
    )
    db.add(simulation)
    db.flush()
    simulation_id=simulation.id
    original_timestamp=simulation.simulated_at

    assert migrate_legacy_simulations(db)==1
    db.flush()
    migrated=db.get(Simulation,simulation_id)
    assert migrated.endpoint==ENDPOINT
    assert migrated.payload=={
        'chat':{'channelId':'channel-1','contactId':'5511999999999'},
        'messages':[{'text':'Oi, Ana!'}],
    }
    assert migrated.content=='Oi, Ana!'
    assert migrated.simulated_at==original_timestamp
    assert migrated.status=='SIMULADO'
    assert migrated.headers['access-token']=='[OCULTO]'
    assert migrate_legacy_simulations(db)==0

def test_simulation_idempotent_and_no_external_requests(db,sample_users,sample_carts,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Nenhuma chamada externa permitida')
    import requests,httpx
    monkeypatch.setenv('WHATSAPP_API_TOKEN','TOP-SECRET-VERY-PRIVATE')
    monkeypatch.setattr(requests,'post',forbidden)
    monkeypatch.setattr(httpx,'post',forbidden)
    consolidate(db,sample_users,sample_carts);db.commit()
    c=db.get(Customer,1)
    day=date(2026,11,2)
    approve_customer(db,c,['ALTO VALOR'],start_date=day);db.commit()
    assert simulate_today(db,run_date=day)==(1,0)
    db.commit()
    assert simulate_today(db,run_date=day)==(0,0)
    db.commit()
    simulations=db.scalars(select(Simulation)).all()
    assert len(simulations)==1
    assert simulations[0].content.startswith('Olá, Ana!')
    assert db.scalars(select(ScheduledMessage).where(ScheduledMessage.status=='SIMULADO')).all()
    assert simulations[0].headers['access-token']=='[OCULTO]'
    assert 'TOP-SECRET-VERY-PRIVATE' not in str(simulations[0].headers)
    assert simulations[0].payload['chat']['contactId']=='5511999999999'
    assert simulations[0].payload['messages'][0]['text']==simulations[0].content

def test_invalid_phone_is_skipped(db,sample_users,sample_carts):
    sample_users[0]['phone']='foo'
    consolidate(db,sample_users,sample_carts);db.commit()
    c=db.get(Customer,1)
    day=date(2026,11,2)
    approve_customer(db,c,['ALTO VALOR'],start_date=day);db.commit()
    assert simulate_today(db,run_date=day)==(0,1)
    assert db.scalars(select(Simulation)).all()==[]
