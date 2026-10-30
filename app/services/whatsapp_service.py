"""Preparação da chamada Botmaker (nunca há chamada externa de envio).

A documentação Botmaker v2 especifica Chat Actions → Send messages, channelId,
contactId e header access-token; o caminho e payload exatos DEVEM ser
confirmados pelo OpenAPI exportado de uma conta antes de reutilizar em produção.
Como não foi possível confirmar o caminho no OpenAPI autenticado, registramos
um marcador explícito, e nunca inventamos um endpoint como se fosse oficial.
"""
import os
import re
from datetime import date
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.entities import ScheduledMessage, Simulation
from app.services.clock import now, today
from app.services.schedule_service import message_for

# Identificador descritivo, NÃO uma URL HTTP: contrato pendente de validação oficial.
ENDPOINT = 'NÃO VERIFICADO — Botmaker v2 / Chat Actions / Send messages'

def format_phone(phone: str, country='55') -> str:
    """Remove formatação e valida o número para o formato internacional E.164."""
    digits = re.sub(r'\D', '', phone or '')
    # A origem DummyJSON pode conter DDI internacional (+81, +1, etc.).
    # Só assume Brasil para número local sem o sinal +.
    if not (phone or '').strip().startswith('+') and len(digits) in (10,11) and country == '55':
        digits = '55' + digits
    if not (11 <= len(digits) <= 15) or digits.startswith('0'):
        raise ValueError('Telefone inválido. Informe DDI/DDD e número.')
    return digits

def personalize(template: str, name: str) -> str:
    """Troca o marcador {nome} pelo primeiro nome do cliente."""
    first = name.strip().split()[0] if name.strip() else ''
    return template.replace('{nome}',first)

def build_request(phone: str, content: str, channel_id: str | None = None):
    """Monta o corpo da requisição para auditoria, sem usar token nem fazer POST."""
    channel_id = channel_id if channel_id is not None else os.getenv('BOTMAKER_CHANNEL_ID','')
    if not channel_id: channel_id = '<CONFIGURAR_CHANNEL_ID>'
    payload = {'channelId':channel_id, 'contactId':format_phone(phone),
               'message':{'text':content}}
    # Cabeçalhos salváveis SEM credenciais, mesmo quando .env tem token verdadeiro.
    headers = {'Content-Type':'application/json', 'access-token':'[OCULTO]'}
    return {'endpoint':ENDPOINT,'method':'POST','headers':headers,'body':payload}

def simulate_today(session, run_date: date | None = None) -> tuple[int,int]:
    """Registra simulações de mensagens previstas para o dia, sem acessar rede externa.

    Retorna a quantidade simulada e a quantidade ignorada por dados inválidos.
    """
    run_date = run_date or today()
    scheduled = session.scalars(select(ScheduledMessage).where(
        ScheduledMessage.scheduled_date == run_date,
        ScheduledMessage.status == 'PENDENTE').order_by(ScheduledMessage.id)).all()
    done=0
    failed=0
    for entry in scheduled:
        customer = entry.customer
        # Confere novamente a aprovação para não simular campanhas revogadas.
        if not customer.approved or entry.track not in {t.track for t in customer.confirmed}:
            continue
        if session.scalar(select(Simulation.id).where(Simulation.scheduled_id == entry.id)) is not None:
            continue
        template = message_for(session, entry.track,entry.number)
        if template is None: failed+=1; continue
        content = personalize(template.content,customer.name)
        try:
            # A validação do telefone ocorre antes de criar o registro de simulação.
            request = build_request(customer.phone, content)
        except ValueError:
            failed+=1
            continue
        session.add(Simulation(scheduled_id=entry.id,customer_id=customer.id,
                               track=entry.track,number=entry.number,content=content,
                               simulated_at=now(),endpoint=request['endpoint'],
                               method=request['method'],headers=request['headers'],
                               payload=request['body']))
        entry.status = 'SIMULADO'
        done += 1
    session.flush()
    return done,failed
