"""Confere formatação e personalização sem permitir chamadas de envio externas."""
from datetime import date
from sqlalchemy import select
import pytest
from app.models.entities import Customer,ScheduledMessage,Simulation
from app.services.customer_service import consolidate
from app.services.schedule_service import approve_customer
from app.services.whatsapp_service import format_phone, personalize,build_request,simulate_today

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
