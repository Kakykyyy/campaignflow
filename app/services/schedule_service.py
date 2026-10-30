"""Cronograma materializado: semana a semana, sequência por prioridade, idempotente."""
from datetime import date, timedelta
from sqlalchemy import select
from app.models.entities import (Customer, ConfirmedTrack, ScheduledMessage,
                                 CampaignMessage, Setting)
from app.services.classification_service import PRIORITIES
from app.services.clock import today

WEEKDAYS = ('Segunda-feira','Terça-feira','Quarta-feira','Quinta-feira',
            'Sexta-feira','Sábado','Domingo')

def get_weekday(session):
    """Lê o dia semanal configurado; segunda-feira (0) é o padrão."""
    setting = session.get(Setting, 'send_weekday')
    return int(setting.value) if setting else 0

def next_weekday(start: date, weekday: int, inclusive=True) -> date:
    """Calcula a data mais próxima do dia desejado, incluindo a data inicial se permitido."""
    if weekday not in range(7): raise ValueError('Dia da semana inválido.')
    days = (weekday - start.weekday()) % 7
    if days == 0 and not inclusive: days = 7
    return start + timedelta(days=days)

def approve_customer(session, customer: Customer, tracks: list[str], start_date: date | None = None):
    """Confirma trilhas escolhidas e gera o cronograma daquele cliente."""
    if not customer.classified_at: raise ValueError('Execute a classificação antes da aprovação.')
    if not tracks or any(t not in PRIORITIES for t in tracks):
        raise ValueError('Selecione pelo menos uma trilha válida.')
    tracks = list(dict.fromkeys(tracks))
    customer.confirmed.clear()
    session.flush()
    suggestions = {s.track for s in customer.suggestions}
    for track in sorted(tracks, key=PRIORITIES.get):
        customer.confirmed.append(ConfirmedTrack(track=track, priority=PRIORITIES[track],
                                                  source='AUTO' if track in suggestions else 'MANUAL'))
    customer.approved = True
    session.flush()
    regenerate_customer(session, customer, start_date=start_date)

def regenerate_customer(session, customer: Customer, start_date: date | None = None):
    """Refaz mensagens pendentes, preservando simulações já registradas."""
    existing = session.scalars(select(ScheduledMessage).where(
        ScheduledMessage.customer_id == customer.id)).all()
    completed = {(x.track, x.number) for x in existing if x.status == 'SIMULADO'}
    last_date = max((x.scheduled_date for x in existing if x.status == 'SIMULADO'), default=None)
    for x in existing:
        if x.status == 'PENDENTE': session.delete(x)
    session.flush()
    if not customer.approved: return
    start = start_date or today()
    if last_date is not None and last_date >= start:
        start = last_date + timedelta(days=1)
    cursor = next_weekday(start, get_weekday(session))
    for ctrack in sorted(customer.confirmed, key=lambda t: t.priority):
        for number in (1,2,3):
            if (ctrack.track, number) in completed: continue
            session.add(ScheduledMessage(customer_id=customer.id, track=ctrack.track,
                                         number=number, scheduled_date=cursor, status='PENDENTE'))
            cursor += timedelta(days=7)

def regenerate_all(session, start_date: date | None = None):
    """Atualiza cronogramas de todos os clientes atualmente aprovados."""
    for customer in session.scalars(select(Customer).where(Customer.approved.is_(True))).all():
        regenerate_customer(session,customer,start_date=start_date)

def set_weekday(session, weekday: int, start_date: date | None = None):
    """Persiste o dia semanal e recalcula os agendamentos pendentes."""
    if weekday not in range(7): raise ValueError('Dia inválido.')
    item = session.get(Setting,'send_weekday')
    if item is None:
        item = Setting(key='send_weekday',value=str(weekday)); session.add(item)
    else: item.value = str(weekday)
    session.flush()
    regenerate_all(session,start_date=start_date)

def schedule_query():
    """Retorna consulta ordenada usada para exibir o cronograma."""
    return select(ScheduledMessage).order_by(ScheduledMessage.scheduled_date,
                                              ScheduledMessage.customer_id,
                                              ScheduledMessage.id)

def message_for(session, track, number):
    """Busca o template de mensagem correspondente à trilha e à etapa."""
    return session.scalar(select(CampaignMessage).where(CampaignMessage.track == track,
                                                        CampaignMessage.number == number))
