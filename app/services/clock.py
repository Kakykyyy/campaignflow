from datetime import datetime
from zoneinfo import ZoneInfo
# O banco armazena datetimes sem tzinfo; aqui usamos explicitamente o fuso de São Paulo.
TZ = ZoneInfo('America/Sao_Paulo')

def now():
    """Retorna o horário local como datetime sem informação de fuso."""
    return datetime.now(TZ).replace(tzinfo=None)

def today():
    """Retorna a data local, usada para comparar agendamentos com o dia atual."""
    return datetime.now(TZ).date()
