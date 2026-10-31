"""Verifica validação, consolidação idempotente e invalidação de aprovações."""
from decimal import Decimal
import pytest
from sqlalchemy import select,func
from app.models.entities import Cart, Customer, ScheduledMessage
from app.services.classification_service import reclassify
from app.services.customer_service import consolidate, normalize_cart
from app.services.schedule_service import approve_customer

def test_sums_and_zero(db,sample_users,sample_carts):
    assert consolidate(db,sample_users,sample_carts)==(3,3)
    db.commit()
    ana=db.get(Customer,1)
    assert ana.total==Decimal('10500.00')
    assert ana.item_count==16
    assert len(ana.carts)==2
    assert [s.track for s in ana.suggestions]==['ALTO VALOR','COMPRA EM QUANTIDADE','PÚBLICO JOVEM']
    carla=db.get(Customer,3)
    assert carla.total==Decimal('0.00') and carla.item_count==0
    assert [s.track for s in carla.suggestions]==['INCENTIVO']

def test_reimport_idempotent(db,sample_users,sample_carts):
    consolidate(db,sample_users,sample_carts);db.commit()
    approve_customer(db,db.get(Customer,1),['ALTO VALOR']);db.commit()
    consolidate(db,sample_users,sample_carts);db.commit()
    assert db.scalar(select(func.count(Cart.id)))==3
    assert db.scalar(select(func.count(Customer.id)))==3
    assert db.get(Customer,1).approved is True
    assert len(db.scalars(select(ScheduledMessage)).all())==3

def test_reclassification_replaces_suggestions_without_duplicates(db,sample_users,sample_carts):
    consolidate(db,sample_users,sample_carts)
    customer=db.get(Customer,1)
    for _ in range(3):
        reclassify(db,customer)
        db.flush()
    assert [suggestion.track for suggestion in customer.suggestions]==[
        'ALTO VALOR','COMPRA EM QUANTIDADE','PÚBLICO JOVEM'
    ]
    assert len({suggestion.track for suggestion in customer.suggestions})==3

def test_changed_data_demands_new_approval(db,sample_users,sample_carts):
    consolidate(db,sample_users,sample_carts);db.commit()
    approve_customer(db,db.get(Customer,1),['ALTO VALOR']);db.commit()
    changed=[{**x,'total':'900'} if x['id']==100 else x for x in sample_carts]
    consolidate(db,sample_users,changed);db.commit()
    assert db.get(Customer,1).approved is False
    assert len(db.scalars(select(ScheduledMessage)).all())==0

def test_reject_invalid_data(db,sample_users,sample_carts):
    bad=[{**sample_carts[0],'products':[{'quantity':-1}]}]
    with pytest.raises(ValueError):consolidate(db,sample_users,bad)
    assert db.scalar(select(func.count(Customer.id)))==0

def test_duplicate_carts(db,sample_users,sample_carts):
    with pytest.raises(ValueError,match='repetidos'):
        consolidate(db,sample_users,sample_carts+[sample_carts[0]])
