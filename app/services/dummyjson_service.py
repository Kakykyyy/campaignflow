"""Extração robusta em páginas. Nunca escreve arquivos se uma das APIs falhar."""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import httpx
from app.database import ROOT

logger = logging.getLogger(__name__)
BASE_URL = 'https://dummyjson.com'
PAGE_SIZE = 50

class ExtractionError(RuntimeError):
    """Erro explícito quando a API ou seus dados não permitem concluir a extração."""
    pass

def fetch_all(resource: str, client: httpx.Client, page_size: int = PAGE_SIZE) -> list[dict]:
    """Busca todas as páginas do recurso, validando resposta e IDs únicos."""
    if resource not in ('users', 'carts'):
        raise ValueError('Recurso desconhecido.')
    seen = set()
    result = []
    skip = 0
    total = None
    # DummyJSON pagina resultados com offset (`skip`) e quantidade (`limit`).
    while total is None or skip < total:
        try:
            response = client.get(f'{BASE_URL}/{resource}', params={'limit':page_size,'skip':skip}, timeout=12.0)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.exception('Falha na extração de %s, página %s', resource, skip)
            raise ExtractionError(f'Falha ao extrair {resource} (posição {skip}).') from exc
        if not isinstance(payload, dict) or not isinstance(payload.get(resource), list) or not isinstance(payload.get('total'), int) or payload['total'] < 0:
            raise ExtractionError(f'Resposta inválida de {resource} na página {skip}.')
        page = payload[resource]
        if total is not None and payload['total'] != total:
            raise ExtractionError(f'Total instável durante extração de {resource}.')
        total = payload['total']
        if not page and skip < total:
            raise ExtractionError(f'Página vazia inesperada: {resource}, skip={skip}.')
        for item in page:
            if not isinstance(item, dict) or not isinstance(item.get('id'), int):
                raise ExtractionError(f'Registro inválido em {resource}.')
            if item['id'] not in seen:
                seen.add(item['id'])
                result.append(item)
        skip += len(page)
        logger.info('Extração %s: %s/%s', resource, skip, total)
    if len(result) != total:
        raise ExtractionError(f'Quantidade de IDs únicos de {resource} ({len(result)}) não confere com o total ({total}).')
    return result

def save_raw(users, carts, root: Path | None = None):
    """Arquiva as respostas JSON em arquivos únicos, preservando a extração original."""
    root = root or ROOT / 'data' / 'raw'
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    stamp_dir = root / datetime.now().strftime('%Y-%m-%d')
    stamp_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for name, records in [('users',users), ('carts',carts)]:
        target = stamp_dir / f'{name}_{timestamp}_{uuid4().hex[:8]}.json'
        # Exclusividade O_EXCL impede sobrescrever até sob concorrência.
        with target.open('x', encoding='utf-8') as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2)
        files.append(str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else str(target))
    return files

def extract(client: httpx.Client | None = None):
    """Extrai usuários e carrinhos e só então salva os arquivos brutos."""
    if client is not None:
        users = fetch_all('users', client)
        carts = fetch_all('carts', client)
    else:
        with httpx.Client(follow_redirects=True) as http:
            users = fetch_all('users', http)
            carts = fetch_all('carts', http)
    file_names = save_raw(users, carts)
    logger.info('Arquivos de extração salvos: %s', file_names)
    return users, carts, file_names
