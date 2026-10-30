"""Monta e registra requisições Botmaker v2 sem enviar chamadas externas.

O endpoint, autenticação e corpo seguem o OpenAPI público da operação
POST /chats-actions/send-messages. O token permanece apenas em memória durante
a montagem e é removido dos cabeçalhos antes de persistir a simulação.
"""
import os
import re
from datetime import date
from sqlalchemy import select
from app.models.entities import ScheduledMessage, Simulation
from app.services.clock import now, today
from app.services.schedule_service import message_for

ENDPOINT = 'https://api.botmaker.com/v2.0/chats-actions/send-messages'
LEGACY_ENDPOINT = 'NÃO VERIFICADO — Botmaker v2 / Chat Actions / Send messages'

def migrate_legacy_simulations(session) -> int:
    """Atualiza metadados de simulações antigas para o contrato documentado atual.

    Preserva cliente, mensagem, data e status. Nenhuma chamada HTTP é feita.
    """
    legacy_rows = session.scalars(
        select(Simulation).where(Simulation.endpoint == LEGACY_ENDPOINT)
    ).all()
    migrated = 0
    for row in legacy_rows:
        old_payload = row.payload
        old_message = old_payload.get('message') if isinstance(old_payload, dict) else None
        if not isinstance(old_payload, dict) or not isinstance(old_message, dict):
            raise ValueError(f'Payload legado inválido na simulação {row.id}.')
        channel_id = old_payload.get('channelId')
        contact_id = old_payload.get('contactId')
        text = old_message.get('text')
        if not all(isinstance(value, str) and value for value in (channel_id, contact_id, text)):
            raise ValueError(f'Campos incompletos no payload da simulação {row.id}.')

        row.endpoint = ENDPOINT
        row.payload = {
            'chat': {'channelId': channel_id, 'contactId': contact_id},
            'messages': [{'text': text}],
        }
        row.headers = {**row.headers, 'access-token': '[OCULTO]'}
        migrated += 1
    return migrated

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
    """Monta a requisição documentada para registro, sem fazer qualquer chamada HTTP."""
    channel_id = channel_id if channel_id is not None else os.getenv('BOTMAKER_CHANNEL_ID','')
    if not channel_id: channel_id = '<CONFIGURAR_CHANNEL_ID>'
    payload = {
        'chat':{'channelId':channel_id, 'contactId':format_phone(phone)},
        'messages':[{'text':content}],
    }
    # A credencial vem do ambiente; uma simulação continua possível sem token.
    token = os.getenv('WHATSAPP_API_TOKEN') or '<CONFIGURAR WHATSAPP_API_TOKEN>'
    headers = {'Content-Type':'application/json', 'access-token':token}
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
        # A credencial só existe na requisição em memória, nunca no histórico.
        safe_headers = {**request['headers'], 'access-token':'[OCULTO]'}
        session.add(Simulation(scheduled_id=entry.id,customer_id=customer.id,
                               track=entry.track,number=entry.number,content=content,
                               simulated_at=now(),endpoint=request['endpoint'],
                               method=request['method'],headers=safe_headers,
                               payload=request['body']))
        entry.status = 'SIMULADO'
        done += 1
    session.flush()
    return done,failed
