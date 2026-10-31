"""Testa limites, múltiplas trilhas e prioridade das classificações."""
from decimal import Decimal
import pytest
from app.services.classification_service import classify, PRIORITIES, TRACKS

def names(total,items,age):
    """Extrai apenas os nomes para deixar as expectativas das regras legíveis."""
    return [x[0] for x in classify(Decimal(str(total)),items,age)]

@pytest.mark.parametrize('total,items,age,expected',[
    (10000,1,50,['ALTO VALOR']),
    (10000,15,24,['ALTO VALOR','COMPRA EM QUANTIDADE','PÚBLICO JOVEM']),
    (9999.99,15,20,['COMPRA EM QUANTIDADE','PÚBLICO JOVEM']),
    (9000,15,40,['COMPRA EM QUANTIDADE']),
    (999.99,15,29,['COMPRA EM QUANTIDADE','INCENTIVO','PÚBLICO JOVEM']),
    (999.99,0,40,['INCENTIVO']),
    (1000,14,29,['PÚBLICO JOVEM']),
    (1500,1,29,['PÚBLICO JOVEM']),
    (1500,1,30,['GERAL']),
    (0,20,25,['COMPRA EM QUANTIDADE','INCENTIVO','PÚBLICO JOVEM']),
    (1000,14,30,['GERAL']),
])
def test_rules(total,items,age,expected):assert names(total,items,age)==expected

def test_four_rule_conditions_cannot_match_together():
    # Alto valor (>= 10000) e incentivo (< 1000) são mutuamente exclusivos.
    assert len(names(10000,15,29))==3
    assert len(names(999.99,15,29))==3

def test_reasons_and_priority():
    hits=classify(Decimal('12450.00'),18,24)
    assert hits[0][1].startswith('Valor total R$ 12.450,00')
    assert [PRIORITIES[track] for track,_ in hits]==[1,2,4]
    assert all(reason for _,reason in hits)
    assert len(TRACKS)==5
