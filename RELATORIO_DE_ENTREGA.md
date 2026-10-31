# Relatório de entrega — CampaignFlow

**Teste técnico:** Desenvolvedor Júnior — Automações e Integrações

**Projeto:** CampaignFlow
**Data:** 30/10/2026
**Repositório público:** https://github.com/Kakykyyy/campaignflow

## 1. Funcionalidades implementadas

- Importação paginada de todos os clientes e carrinhos do DummyJSON, com validação, timeout, logs e arquivos JSON únicos por execução.
- Consolidação transacional em SQLite, relacionamento por `userId`, arredondamento monetário decimal e somatório de quantidades efetivas.
- Classificação automática reproduzível em todas as trilhas aplicáveis, ordenadas por prioridade e com motivos em português.
- Confirmação manual de trilhas, inclusão/remoção, revogação e persistência da aprovação.
- Cronograma semanal configurável, três etapas por trilha e ausência de trilhas simultâneas.
- Simulação local de mensagens previstas para hoje, com personalização do primeiro nome, formatação de número e proteção por unicidade no banco.
- Histórico detalhado de cada simulação, incluindo cabeçalhos redigidos e corpo JSON.
- Histórico com filtros combinados e CSV UTF-8 com BOM; exportação preserva as 11 colunas existentes, adiciona número da mensagem, data prevista, sinalização de channelId placeholder e JSON completo da requisição; credenciais são redigidas e valores de planilha protegidos contra fórmulas.
- Dashboard com indicadores reais, gráficos CSS, filtros, pesquisa e layout responsivo.
- Dashboard mostra a data e o volume da extração concluída mais recente.
- Perfil do cliente exibe linha do tempo calculada dos agendamentos persistidos, incluindo progresso e próxima mensagem.
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

- `python -m pytest -q`: **56 testes aprovados** após as correções desta auditoria.
- `python -m compileall -q app scripts tests`: compilação concluída sem erros.
- Smoke test com `TestClient` em `/`, `/clientes`, `/clientes/10001`, `/cronograma`, `/historico`, `/configuracoes`, `/docs`, `/health`, `/api/indicadores`: **todos retornaram HTTP 200**.
- Extração ao vivo do DummyJSON: **208 clientes e 208 carrinhos**, com paginação completa; os IDs vão de 1 a 208 em cada fonte. A consolidação gravou 208 clientes e 208 carrinhos no SQLite, classificou todos os clientes e registrou a execução. Os arquivos brutos ficaram em `data/raw/`, pasta ignorada pelo Git. As quantidades dos produtos somam 2.417 unidades.
- Homologação no navegador: as oito páginas principais (`/`, `/clientes`, `/clientes/1`, `/cronograma`, `/historico`, `/historico/1`, `/configuracoes` e `/docs`) retornaram HTTP 200 em viewport desktop e mobile, sem overflow horizontal. Busca/filtro de clientes e filtro de cronograma foram exercitados; formulários de aprovação e simulação e seus tokens CSRF foram conferidos. A simulação não foi submetida nesta revisão porque não havia mensagens pendentes para hoje.
- Testes HTTP automatizados continuam usando mocks; somente a extração foi executada contra a API pública real. Nenhum envio à Botmaker foi executado.

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

## 7. Limitações e próximos passos (fora do escopo do teste)

- O envio real à Botmaker permanece desabilitado, conforme o requisito de simulação. O contrato HTTP está documentado e a requisição que seria enviada é registrada sem credenciais.
- Não há login de operadores. A aplicação é para uso local em avaliação; antes de hospedá-la publicamente, implemente autenticação, autorização, HTTPS, auditoria e proteção contra excesso de requisições.

As validações funcionais pendentes de extração ao vivo e revisão visual foram concluídas; detalhes e evidências estão nas issues encerradas do repositório.

## 8. Checklist de atendimento

| Requisito | Situação |
| --- | --- |
| Estrutura Python/FastAPI/SQLAlchemy/SQLite | Implementado |
| Interface administrativa em português | Implementado |
| Extração paginada completa | Implementado, testado com mocks e validado ao vivo (208 clientes e 208 carrinhos) |
| Backup bruto JSON com timestamps únicos | Implementado, testado e validado; arquivos locais ignorados pelo Git |
| Consolidação de carrinhos e clientes | Implementado, testado e validado ao vivo no SQLite |
| Classificação em múltiplas trilhas por prioridade e inclusão manual | Implementado e testado |
| Aprovação manual e persistência | Implementado e testado |
| Cronograma sequencial de três mensagens | Implementado e testado |
| Configuração do dia da semana | Implementado e testado |
| Simulação de WhatsApp sem envio real | Implementado e testado |
| Histórico com filtros, exportação CSV, integridade de cronograma e credenciais redigidas | Implementado e testado |
| Jornada visual derivada do cronograma persistido | Implementada e testada |
| Estrutura da simulação Botmaker conforme OpenAPI público | Implementado; envio real desabilitado |
| Histórico técnico e token oculto | Implementado e testado |
| Dashboard com dados do banco | Implementado e testado |
| Testes automatizados | 56 aprovados nesta auditoria local |
| Homologação das páginas principais em desktop e mobile | Validada no navegador; sem overflow horizontal |
| Docker, configuração local opcional por .env, CI e README | Implementado |
| Repositório GitHub publicado | https://github.com/Kakykyyy/campaignflow |
