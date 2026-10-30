# Relatório de entrega — CampaignFlow

**Teste técnico:** Desenvolvedor Júnior — Automações e Integrações

**Projeto:** CampaignFlow
**Data:** 30/10/2026
**Repositório público:** https://github.com/Kakykyyy/campaignflow

## 1. Funcionalidades implementadas

- Importação paginada de todos os clientes e carrinhos do DummyJSON, com validação, timeout, logs e arquivos JSON únicos por execução.
- Consolidação transacional em SQLite, relacionamento por `userId`, arredondamento monetário decimal e somatório de quantidades efetivas.
- Classificação automática reproduzível, com motivos em português e suporte a várias trilhas por cliente.
- Confirmação manual de trilhas, inclusão/remoção, revogação e persistência da aprovação.
- Cronograma semanal configurável, três etapas por trilha e ausência de trilhas simultâneas.
- Simulação local de mensagens previstas para hoje, com personalização do primeiro nome, formatação de número e proteção por unicidade no banco.
- Histórico detalhado de cada simulação, incluindo cabeçalhos redigidos e corpo JSON.
- Dashboard com indicadores reais, gráficos CSS, filtros, pesquisa e layout responsivo.
- API FastAPI de consulta, documentação Swagger, script opcional de demonstração, Docker e GitHub Actions.

## 2. Estrutura final

`app/` (models, routers, services, templates, static); `tests/`; `scripts/`; `data/raw/`; `.github/workflows/`; `README.md`; `requirements.txt`; `.gitignore`; `Dockerfile`; `docker-compose.yml`.

## 3. Tecnologias

Python 3.11+, FastAPI, SQLAlchemy, SQLite, Jinja2, HTTPX, pytest, python-dotenv, Bootstrap 5 e JavaScript.

## 4. Decisões técnicas

- Serviços de negócio independentes das rotas de interface.
- Separação entre classificação sugerida e trilhas aprovadas.
- Replanejamento exclusivo de mensagens pendentes, preservando histórico.
- Idempotência por restrições únicas e transações.
- Proteção CSRF de formulários e credenciais nunca persistidas nos históricos.
- Simulação local deliberadamente sem função de envio real.

## 5. Testes executados e resultados

- `python -m pytest -q`: **47 testes aprovados**.
- `python -m compileall -q app scripts tests`: compilação concluída sem erros.
- Smoke test com `TestClient` em `/`, `/clientes`, `/clientes/10001`, `/cronograma`, `/historico`, `/configuracoes`, `/docs`, `/health`, `/api/indicadores`: **todos retornaram HTTP 200**.
- Testes HTTP externos foram simulados com mocks. **Não foi possível executar uma importação ao vivo** do DummyJSON neste ambiente, por indisponibilidade de acesso de rede de saída.

## 6. Como iniciar

```bash
cd campaignflow
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Abra `http://127.0.0.1:8000`. O README contém instruções de instalação para Windows, Linux e Docker.

## 7. O que falta para concluir literalmente 100% da especificação

1. **Importação ao vivo:** repetir a execução manual de extração com acesso à internet no computador do avaliador.
2. **Homologação no navegador:** as telas principais têm capturas reais; ainda é recomendada uma revisão interativa completa dos fluxos.

**Observação:** a aplicação não implementa login de operadores. Foi construída para uso local em teste; antes de hospedá-la publicamente, implementar autenticação, autorização, HTTPS, auditoria e proteção de rate limits.

## 8. Checklist de atendimento

| Requisito | Situação |
| --- | --- |
| Estrutura Python/FastAPI/SQLAlchemy/SQLite | Implementado |
| Interface administrativa em português | Implementado |
| Extração paginada completa | Implementado e testado com mocks |
| Backup bruto JSON com timestamps únicos | Implementado e testado |
| Consolidação de carrinhos e clientes | Implementado e testado |
| Classificação com prioridade e múltiplas trilhas | Implementado e testado |
| Aprovação manual e persistência | Implementado e testado |
| Cronograma sequencial de três mensagens | Implementado e testado |
| Configuração do dia da semana | Implementado e testado |
| Simulação de WhatsApp sem envio real | Implementado e testado |
| Estrutura da simulação Botmaker conforme OpenAPI público | Implementado; envio real desabilitado |
| Histórico técnico e token oculto | Implementado e testado |
| Dashboard com dados do banco | Implementado e testado |
| Testes automatizados | 47 aprovados |
| Docker, configuração local opcional por .env, CI e README | Implementado |
| Repositório GitHub publicado | https://github.com/Kakykyyy/campaignflow |
