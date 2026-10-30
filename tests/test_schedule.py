"""Testa aprovação, ordenação semanal, reagendamento e prevenção de duplicatas."""
from datetime import date,timedelta
from sqlalchemy import select
import pytest
from app.models.entities import Customer, ScheduledMessage, Simulation
from app.services.customer_service import consolidate
from app.services.schedule_service import (approve_customer, next_weekday,set_weekday,
                                           regenerate_customer)

def setup_customer(db,users,carts):
    """Prepara um cliente realista no banco em memória para os testes de agenda."""
    consolidate(db,users,carts);db.commit()
    return db.get(Customer,1)

def test_manual_approval_and_sequence(db,sample_users,sample_carts):
    customer=setup_customer(db,sample_users,sample_carts)
    start=date(2026,11,2) # segunda
    approve_customer(db,customer,['PÚBLICO JOVEM','ALTO VALOR','COMPRA EM QUANTIDADE'],start_date=start)
    db.commit()
    plans=db.scalars(select(ScheduledMessage).where(ScheduledMessage.customer_id==1).order_by(ScheduledMessage.scheduled_date)).all()
    assert len(plans)==9
    assert [(p.track,p.number) for p in plans]==[(t,n) for t in ('ALTO VALOR','COMPRA EM QUANTIDADE','PÚBLICO JOVEM') for n in (1,2,3)]
    assert [p.scheduled_date for p in plans]==[start+timedelta(days=7*i) for i in range(9)]
    assert len({p.scheduled_date for p in plans})==9

def test_manual_add_and_remove(db,sample_users,sample_carts):
    c=setup_customer(db,sample_users,sample_carts)
    approve_customer(db,c,['GERAL'],start_date=date(2026,11,2));db.commit()
    assert [t.track for t in c.confirmed]==['GERAL']
    assert c.confirmed[0].source=='MANUAL'
    assert len(db.scalars(select(ScheduledMessage)).all())==3

def test_no_approval_no_schedule(db,sample_users,sample_carts):
    setup_customer(db,sample_users,sample_carts)
    assert db.scalars(select(ScheduledMessage)).all()==[]

def test_day_of_week_and_replan(db,sample_users,sample_carts):
    c=setup_customer(db,sample_users,sample_carts)
    approve_customer(db,c,['ALTO VALOR'],start_date=date(2026,11,2));db.commit()
    set_weekday(db,4,start_date=date(2026,11,2));db.commit()
    plans=db.scalars(select(ScheduledMessage).order_by(ScheduledMessage.scheduled_date)).all()
    assert [p.scheduled_date for p in plans]==[date(2026,11,6)+timedelta(days=7*i) for i in range(3)]

def test_repeated_approval_no_duplicates(db,sample_users,sample_carts):
    c=setup_customer(db,sample_users,sample_carts)
    for _ in range(3):
        approve_customer(db,c,['ALTO VALOR'],start_date=date(2026,11,2));db.commit()
    assert len(db.scalars(select(ScheduledMessage)).all())==3

def test_next_weekday_inclusive():
    assert next_weekday(date(2026,11,2),0)==date(2026,11,2)
    assert next_weekday(date(2026,11,2),0,False)==date(2026,11,9)
    assert next_weekday(date(2026,11,2),3)==date(2026,11,5)
    with pytest.raises(ValueError):next_weekday(date(2026,11,2),9)
