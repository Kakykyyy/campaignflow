from sqlalchemy import select
from app.models.entities import CampaignMessage, Setting

MESSAGES = {
'ALTO VALOR': [
'Olá, {nome}! Você é um dos nossos clientes especiais: a partir desta semana, tem frete grátis em todos os pedidos.',
'{nome}, separamos produtos que combinam com suas últimas compras. Confira no app.',
'{nome}, queremos ouvir você: responda nossa pesquisa de 1 minuto e ganhe um cupom de 10%.'],
'COMPRA EM QUANTIDADE': [
'Olá, {nome}! Pedidos acima de 20 itens têm 5% de desconto automático.',
'{nome}, você pode agendar a entrega para o dia que preferir. Veja como no app.',
'{nome}, monte sua lista de compras recorrentes e receba um lembrete na hora de repor.'],
'INCENTIVO': [
'Olá, {nome}! Use o cupom BEMVINDO e ganhe 15% na próxima compra.',
'{nome}, temos produtos a partir de R$ 9,90 com entrega rápida. Aproveite para experimentar.',
'{nome}, seu cupom de 15% expira em 7 dias. Não deixe passar!'],
'PÚBLICO JOVEM': [
'E aí, {nome}! Siga a gente nas redes e veja os lançamentos antes de todo mundo.',
'{nome}, indique um amigo e vocês dois ganham R$ 20 de desconto.',
'{nome}, chegou a nova coleção. Dá uma olhada e conta pra gente o que achou.'],
'GERAL': [
'Olá, {nome}! Obrigado por comprar com a gente. Confira as novidades da semana.',
'{nome}, ative as notificações do app para não perder nenhuma promoção.',
'{nome}, conta pra gente como foi sua última compra respondendo uma pesquisa rápida.']}

def seed(session):
    """Insere templates padrão apenas quando ainda não existem no banco."""
    # Inserir apenas templates ausentes. Os modelos existentes não são sobrescritos.
    existing = {(m.track,m.number) for m in session.scalars(select(CampaignMessage)).all()}
    for track, messages in MESSAGES.items():
        for n, content in enumerate(messages,1):
            if (track,n) not in existing:
                session.add(CampaignMessage(track=track,number=n,content=content))
    if session.get(Setting,'send_weekday') is None:
        session.add(Setting(key='send_weekday',value='0'))
    session.commit()
