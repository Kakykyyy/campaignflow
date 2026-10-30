"""Valida registros antes de consolidar. Commit feito pelo chamador."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from sqlalchemy import select
from app.models.entities import Customer, Cart
from app.services.classification_service import reclassify
from app.services.clock import now

CENT = Decimal('0.01')

def decimal_money(value):
    """Converte, arredonda para centavos e rejeita valores inválidos ou negativos."""
    try:
        v = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
        if not v.is_finite() or v < 0: raise ValueError()
        return v
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Total de carrinho inválido.')

def positive_int(value, field):
    """Valida inteiros não negativos; bool é rejeitado apesar de ser subtipo de int."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f'{field} inválido.')
    return value

def normalize_cart(cart):
    """Valida o formato de um carrinho e retorna seus dados em forma consistente."""
    cid = positive_int(cart.get('id'), 'ID do carrinho')
    user_id = positive_int(cart.get('userId'), 'ID do usuário')
    products = cart.get('products')
    if not isinstance(products, list): raise ValueError('Produtos inválidos no carrinho.')
    quantities = sum(positive_int(p.get('quantity'), 'Quantidade') for p in products if isinstance(p, dict))
    if len(products) != len([p for p in products if isinstance(p,dict)]):
        raise ValueError('Produto malformado.')
    # O requisito exige soma das quantidades, não totalProducts.
    return cid, user_id, decimal_money(cart.get('total')), quantities, [
        {'title':str(p.get('title',''))[:160], 'quantity':p['quantity']} for p in products
    ]

def consolidate(session, users, carts):
    """Valida dados importados, consolida compras e atualiza clientes no banco.

    Não confirma a transação: o chamador decide se deve fazer commit ou rollback.
    """
    # Validações iniciais evitam persistir dados duplicados ou referências quebradas.
    if len({u.get('id') for u in users}) != len(users): raise ValueError('IDs de usuários repetidos.')
    if len({c.get('id') for c in carts}) != len(carts): raise ValueError('IDs de carrinhos repetidos.')
    normalized = [normalize_cart(cart) for cart in carts]
    grouped = defaultdict(list)
    for cart in normalized: grouped[cart[1]].append(cart)
    user_ids = {u['id'] for u in users}
    if any(uid not in user_ids for uid in grouped):
        raise ValueError('Carrinho vinculado a usuário ausente na extração.')
    # Monta todos os registros antes de alterar o banco, separando validação de gravação.
    prepared=[]
    for u in users:
        uid = positive_int(u.get('id'), 'ID do usuário')
        age = positive_int(u.get('age'), 'Idade')
        name = f"{str(u.get('firstName','')).strip()} {str(u.get('lastName','')).strip()}".strip()
        if not name: raise ValueError('Nome de cliente vazio.')
        state = (u.get('address') or {}).get('state','')
        related = grouped.get(uid, [])
        total = sum((c[2] for c in related), Decimal('0.00'))
        count = sum(c[3] for c in related)
        prepared.append((uid, name[:160], age, str(u.get('gender') or '')[:32], str(state)[:120], str(u.get('phone') or '')[:64], total, count, related))
    for uid,name,age,gender,state,phone,total,count,related in prepared:
        customer = session.get(Customer, uid)
        changed = bool(customer and (customer.total != total or customer.item_count != count or customer.age != age))
        if not customer:
            customer = Customer(id=uid)
            session.add(customer)
        customer.name,customer.age,customer.gender,customer.state,customer.phone = name,age,gender,state,phone
        customer.total,customer.item_count,customer.imported_at = total,count,now()
        if changed and customer.approved:
            # Mudanças nos dados usados pela segmentação invalidam aprovações pendentes.
            customer.approved = False
            customer.confirmed.clear()
            from app.models.entities import ScheduledMessage
            for pending in session.scalars(select(ScheduledMessage).where(
                ScheduledMessage.customer_id == uid, ScheduledMessage.status == 'PENDENTE')).all():
                session.delete(pending)
        for old in list(customer.carts): session.delete(old)
        session.flush()
        for id_,_,amount,qty,products in related:
            session.add(Cart(id=id_,customer_id=uid,total=amount,item_count=qty,products=products))
        reclassify(session,customer)
    return len(prepared), len(normalized)
