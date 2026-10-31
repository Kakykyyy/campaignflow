"""Classificação exclusiva por prioridade; GERAL só quando nenhuma regra anterior se aplica."""
from decimal import Decimal
from app.models.entities import Customer, Suggestion

TRACKS = ('ALTO VALOR','COMPRA EM QUANTIDADE','INCENTIVO','PÚBLICO JOVEM','GERAL')
# O índice da trilha na tupla também representa sua prioridade de execução.
PRIORITIES = {track: index + 1 for index, track in enumerate(TRACKS)}

def br_money(value):
    """Formata um valor decimal no padrão monetário brasileiro."""
    return 'R$ ' + f'{Decimal(str(value)):,.2f}'.replace(',','X').replace('.',',').replace('X','.')

def classify(total: Decimal, items: int, age: int) -> list[tuple[str,str]]:
    """Retorna somente a trilha de maior prioridade aplicável ao cliente."""
    total = Decimal(str(total))
    if total >= Decimal('10000'):
        return [('ALTO VALOR', f'Valor total {br_money(total)} é maior ou igual a R$ 10.000,00.')]
    if items >= 15:
        return [('COMPRA EM QUANTIDADE', f'Cliente comprou {items} itens, atingindo o mínimo de 15.')]
    if total < Decimal('1000'):
        return [('INCENTIVO', f'Valor total de compras {br_money(total)} é inferior a R$ 1.000,00.')]
    if age < 30:
        return [('PÚBLICO JOVEM', f'Cliente possui {age} anos, idade inferior a 30 anos.')]
    return [('GERAL', 'Cliente não atende aos critérios das outras quatro trilhas.')]

def reclassify(session, customer: Customer):
    """Substitui sugestões antigas e registra a data da nova classificação."""
    customer.suggestions.clear()
    session.flush()
    for track, reason in classify(customer.total, customer.item_count, customer.age):
        customer.suggestions.append(Suggestion(track=track, priority=PRIORITIES[track], reason=reason))
    from app.services.clock import now
    customer.classified_at = now()

def reclassify_all(session):
    """Reclassifica todos os clientes e persiste as mudanças em uma transação."""
    from sqlalchemy import select
    for customer in session.scalars(select(Customer)).all():
        reclassify(session, customer)
    session.commit()
