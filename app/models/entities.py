"""Modelos de persistência e restrições de unicidade."""
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import (String, Integer, Date, DateTime, Boolean, ForeignKey,
                        Numeric, UniqueConstraint, Text, JSON, CheckConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

# Cada classe abaixo representa uma tabela do banco. `Mapped` informa o tipo
# esperado no Python, enquanto `mapped_column` configura a coluna no SQLAlchemy.
class Customer(Base):
    """Cliente importado, com dados consolidados e classificação da campanha."""
    __tablename__ = 'customers'
    id: Mapped[int] = mapped_column(primary_key=True)  # Mantém o ID recebido do DummyJSON como chave primária.
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String(32), default='')
    state: Mapped[str] = mapped_column(String(120), default='')
    phone: Mapped[str] = mapped_column(String(64), default='')
    # Numeric evita imprecisão de ponto flutuante em valores monetários.
    total: Mapped[Decimal] = mapped_column(Numeric(14,2), default=Decimal('0.00'))
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    # O valor padrão é calculado quando cada registro é criado.
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    classified_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # `relationship` permite acessar registros relacionados como atributos Python.
    # O cascade também remove os registros filhos quando o cliente é removido.
    suggestions: Mapped[list['Suggestion']] = relationship(cascade='all, delete-orphan', order_by='Suggestion.priority')
    confirmed: Mapped[list['ConfirmedTrack']] = relationship(cascade='all, delete-orphan', order_by='ConfirmedTrack.priority')
    carts: Mapped[list['Cart']] = relationship(cascade='all, delete-orphan')

class Cart(Base):
    """Carrinho importado associado a um cliente."""
    __tablename__ = 'carts'
    id: Mapped[int] = mapped_column(primary_key=True)
    # Chave estrangeira liga o carrinho ao cliente; ondelete apaga carrinhos órfãos.
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), index=True)
    total: Mapped[Decimal] = mapped_column(Numeric(14,2))
    item_count: Mapped[int] = mapped_column(Integer)
    # JSON guarda a lista de produtos sem exigir uma tabela separada para cada item.
    products: Mapped[list] = mapped_column(JSON, default=list)

class Suggestion(Base):
    """Trilha sugerida pelo processo de classificação para um cliente."""
    __tablename__ = 'suggestions'
    # Impede que a mesma trilha apareça duas vezes para o mesmo cliente.
    __table_args__ = (UniqueConstraint('customer_id', 'track'),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), index=True)
    track: Mapped[str] = mapped_column(String(32))
    # A prioridade define a ordem em que as sugestões são apresentadas.
    priority: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)

class ConfirmedTrack(Base):
    """Trilha aprovada para participar da campanha de um cliente."""
    __tablename__ = 'confirmed_tracks'
    # Garante que não haja trilhas confirmadas duplicadas para o mesmo cliente.
    __table_args__ = (UniqueConstraint('customer_id', 'track'),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'), index=True)
    track: Mapped[str] = mapped_column(String(32))
    priority: Mapped[int] = mapped_column(Integer)
    # Registra se a confirmação veio automaticamente ou de uma ação manual.
    source: Mapped[str] = mapped_column(String(12), default='AUTO')

class CampaignMessage(Base):
    """Texto de cada mensagem disponível por trilha e posição na sequência."""
    __tablename__ = 'campaign_messages'
    # Para cada trilha, um número de mensagem só pode existir uma vez.
    __table_args__ = (UniqueConstraint('track', 'number'),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    track: Mapped[str] = mapped_column(String(32))
    number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)

class ScheduledMessage(Base):
    """Mensagem planejada para um cliente em uma data específica."""
    __tablename__ = 'scheduled_messages'
    # Evita agendar duas vezes a mesma posição da sequência para a trilha do cliente.
    # A checagem limita a sequência às mensagens de 1 a 3.
    __table_args__ = (UniqueConstraint('customer_id', 'track', 'number'),
                      CheckConstraint('number between 1 and 3'))
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'), index=True)
    track: Mapped[str] = mapped_column(String(32))
    number: Mapped[int] = mapped_column(Integer)
    scheduled_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(12), default='PENDENTE')
    # Relacionamento para consultar o cliente do agendamento sem fazer a busca manualmente.
    customer: Mapped['Customer'] = relationship()

class Simulation(Base):
    """Registro de uma simulação de envio, incluindo requisição e resposta planejadas."""
    __tablename__ = 'simulations'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Um agendamento só pode gerar uma simulação, evitando registros repetidos.
    scheduled_id: Mapped[int] = mapped_column(ForeignKey('scheduled_messages.id'), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id'))
    track: Mapped[str] = mapped_column(String(32))
    number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    simulated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # Mantém os detalhes da chamada que seria feita à integração externa.
    endpoint: Mapped[str] = mapped_column(String(240))
    method: Mapped[str] = mapped_column(String(10))
    headers: Mapped[dict] = mapped_column(JSON)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default='SIMULADO')
    # Os relacionamentos permitem navegar da simulação ao cliente e ao agendamento.
    customer: Mapped['Customer'] = relationship()
    scheduled: Mapped['ScheduledMessage'] = relationship()

class Setting(Base):
    """Configuração simples armazenada como chave e valor."""
    __tablename__ = 'settings'
    # A própria chave identifica unicamente cada configuração.
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256))

class ImportRun(Base):
    """Resumo de uma execução de importação e dos arquivos processados."""
    __tablename__ = 'import_runs'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # Quantidades importadas e caminhos ajudam a auditar cada execução.
    users: Mapped[int] = mapped_column(Integer)
    carts: Mapped[int] = mapped_column(Integer)
    user_file: Mapped[str] = mapped_column(String(260))
    cart_file: Mapped[str] = mapped_column(String(260))
