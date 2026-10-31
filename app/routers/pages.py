"""Rotas SSR. Ações com token CSRF e redirects PRG."""
import hmac
import logging
import os
import secrets
import csv
import io
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session, selectinload
from app.database import get_db
from app.models.entities import (Customer, Cart, Suggestion, ConfirmedTrack, ScheduledMessage,
                                 Simulation, CampaignMessage, ImportRun)
from app.services.clock import today
from app.services.classification_service import TRACKS, PRIORITIES, br_money, reclassify_all
from app.services.dummyjson_service import extract, ExtractionError
from app.services.customer_service import consolidate
from app.services.schedule_service import WEEKDAYS,get_weekday,approve_customer,set_weekday,schedule_query
from app.services.whatsapp_service import simulate_today, personalize

logger=logging.getLogger(__name__)
router=APIRouter()
# Os templates ficam fora do pacote de rotas e são renderizados pelo Jinja2.
templates=Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent/'templates'))
templates.env.filters['money']=br_money

def csrf(request):
    """Cria e reutiliza um token de sessão para proteger formulários contra CSRF."""
    if 'csrf' not in request.session: request.session['csrf']=secrets.token_urlsafe(32)
    return request.session['csrf']

def verify(request, token):
    """Compara tokens em tempo constante e bloqueia formulários sem token válido."""
    if not token or not hmac.compare_digest(csrf(request), token):
        raise HTTPException(403,'Formulário inválido (CSRF). Recarregue a página.')

def render(request, name, **data):
    """Centraliza variáveis comuns enviadas a todas as páginas HTML."""
    return templates.TemplateResponse(request,name,{'csrf':csrf(request),'tracks':TRACKS,'today':today(),**data})

def back(url, message=None, error=None):
    """Redireciona após uma ação (PRG), exibindo mensagem de sucesso ou erro."""
    if error: url += ('&' if '?' in url else '?') + 'error=' + quote(str(error)[:220])
    if message: url += ('&' if '?' in url else '?') + 'msg=' + quote(str(message)[:220])
    return RedirectResponse(url,status_code=303)

def history_query(q='',start='',end='',track='',status=''):
    """Constrói uma consulta comum para a listagem e exportação do histórico."""
    query=select(Simulation).join(Customer)
    if q: query=query.where(Customer.name.ilike(f'%{q[:80]}%'))
    try:
        if start: query=query.where(Simulation.simulated_at>=datetime.combine(date.fromisoformat(start),time.min))
        if end: query=query.where(Simulation.simulated_at<=datetime.combine(date.fromisoformat(end),time.max))
    except ValueError as exc:
        raise HTTPException(400,'Data inválida.') from exc
    if track:
        if track not in TRACKS: raise HTTPException(400,'Trilha inválida.')
        query=query.where(Simulation.track==track)
    if status:
        if status != 'SIMULADO': raise HTTPException(400,'Status inválido.')
        query=query.where(Simulation.status==status)
    return query.order_by(Simulation.simulated_at.desc(),Simulation.id.desc())

def csv_cell(value):
    """Neutraliza valores de origem externa que planilhas poderiam executar como fórmula."""
    text=str(value if value is not None else '')
    if text.lstrip(' \t\r\n').startswith(('=','+','-','@')):
        return "'"+text
    return text

def sensitive_key(key):
    normalized=key.casefold().replace('_','-')
    return any(part in normalized for part in ('token','authorization','secret','api-key','apikey','password'))

def collect_secrets(value):
    """Obtém credenciais conhecidas do registro legado para redigi-las em todo o CSV."""
    secrets_found={os.getenv('WHATSAPP_API_TOKEN','')}
    if isinstance(value,dict):
        for key,item in value.items():
            if sensitive_key(str(key)) and isinstance(item,str) and item:
                secrets_found.add(item)
            secrets_found.update(collect_secrets(item))
    elif isinstance(value,list):
        for item in value:
            secrets_found.update(collect_secrets(item))
    secrets_found.discard('')
    return secrets_found

def redact_export_value(value,secrets_found):
    """Redige chaves sensíveis e qualquer credencial conhecida antes de serializar."""
    if isinstance(value,dict):
        return {key:('[OCULTO]' if sensitive_key(str(key)) else redact_export_value(item,secrets_found))
                for key,item in value.items()}
    if isinstance(value,list):
        return [redact_export_value(item,secrets_found) for item in value]
    if isinstance(value,str):
        for secret in secrets_found:
            value=value.replace(secret,'[OCULTO]')
    return value

def validate_export_record(row):
    """Recusa simulações sem vínculo válido com uma mensagem aprovada e prevista."""
    scheduled=row.scheduled
    # O serviço só marca um agendamento como SIMULADO após validar aprovação e trilha confirmada.
    if (row.status!='SIMULADO' or scheduled is None or scheduled.status!='SIMULADO'
            or scheduled.id!=row.scheduled_id or scheduled.customer_id!=row.customer_id
            or scheduled.track!=row.track or scheduled.number!=row.number
            or scheduled.scheduled_date>row.simulated_at.date()):
        raise HTTPException(409,f'Simulação {row.id} não corresponde a um agendamento simulado válido.')

@router.get('/',response_class=HTMLResponse,include_in_schema=False)
def dashboard(request:Request,db:Session=Depends(get_db)):
    """Calcula indicadores do banco para a tela inicial."""
    total=db.scalar(select(func.count(Customer.id))) or 0
    classified=db.scalar(select(func.count(Customer.id)).where(Customer.classified_at.is_not(None))) or 0
    approved=db.scalar(select(func.count(Customer.id)).where(Customer.approved.is_(True))) or 0
    tracks=db.scalar(select(func.count(ConfirmedTrack.id))) or 0
    today_count=db.scalar(select(func.count(ScheduledMessage.id)).where(ScheduledMessage.scheduled_date==today(),ScheduledMessage.status=='PENDENTE')) or 0
    simulated=db.scalar(select(func.count(Simulation.id))) or 0
    distribution={track:db.scalar(select(func.count(Suggestion.id)).where(Suggestion.track==track)) or 0 for track in TRACKS}
    upcoming=db.scalars(schedule_query().where(ScheduledMessage.status=='PENDENTE',ScheduledMessage.scheduled_date>=today()).limit(8)).all()
    last_import=db.scalar(select(ImportRun).order_by(ImportRun.created_at.desc(),ImportRun.id.desc()).limit(1))
    return render(request,'dashboard.html',active='dashboard',total=total,classified=classified,
                  approved=approved,pending=total-approved,tracks_count=tracks,today_count=today_count,
                  simulated=simulated,distribution=distribution,upcoming=upcoming,last_import=last_import)

@router.post('/import',include_in_schema=False)
def import_now(request:Request,csrf_token:str=Form(...),db:Session=Depends(get_db)):
    """Importa as fontes externas e persiste os dados validados em transação."""
    verify(request,csrf_token)
    try:
        users,carts,files=extract()
        with db.begin():
            count_users,count_carts=consolidate(db,users,carts)
            db.add(ImportRun(users=count_users,carts=count_carts,user_file=files[0],cart_file=files[1]))
        return back('/clientes',message=f'Extração concluída: {count_users} clientes e {count_carts} carrinhos.')
    except (ExtractionError,ValueError) as exc:
        db.rollback(); logger.warning('Importação não realizada: %s',exc)
        return back('/',error=str(exc))
    except Exception:
        db.rollback(); logger.exception('Erro ao importar')
        return back('/',error='Não foi possível importar. Consulte os logs.')

@router.post('/classify',include_in_schema=False)
def classify_now(request:Request,csrf_token:str=Form(...),db:Session=Depends(get_db)):
    """Executa novamente as regras de classificação para todos os clientes."""
    verify(request,csrf_token)
    reclassify_all(db)
    return back('/clientes',message='Sugestões automáticas atualizadas.')

@router.get('/clientes',response_class=HTMLResponse,include_in_schema=False)
def customers_page(request:Request,q:str='',track:str='',state:str='',status:str='',page:int=Query(1,ge=1),db:Session=Depends(get_db)):
    """Lista clientes com filtros e paginação para limitar o volume carregado."""
    query=select(Customer)
    if q: query=query.where(Customer.name.ilike(f'%{q[:80]}%'))
    if track in TRACKS: query=query.where(Customer.suggestions.any(Suggestion.track==track))
    if state: query=query.where(Customer.state==state)
    if status=='approved': query=query.where(Customer.approved.is_(True))
    if status=='pending': query=query.where(Customer.approved.is_(False))
    total=db.scalar(select(func.count()).select_from(query.subquery())) or 0
    records=db.scalars(query.options(selectinload(Customer.suggestions),selectinload(Customer.confirmed)).order_by(Customer.name).offset((page-1)*25).limit(25)).all()
    states=db.scalars(select(Customer.state).distinct().order_by(Customer.state)).all()
    return render(request,'customers.html',active='customers',customers=records,q=q,track=track,
                  state=state,status=status,page=page,pages=max(1,(total+24)//25),count=total,states=states)

@router.get('/clientes/{customer_id}',response_class=HTMLResponse,include_in_schema=False)
def customer_detail(request:Request,customer_id:int,db:Session=Depends(get_db)):
    """Carrega o perfil e relações necessárias para a página de detalhes."""
    customer=db.scalar(select(Customer).options(selectinload(Customer.suggestions),selectinload(Customer.confirmed),selectinload(Customer.carts)).where(Customer.id==customer_id))
    if not customer: raise HTTPException(404,'Cliente não encontrado.')
    sent=db.scalar(select(func.count(ScheduledMessage.id)).where(ScheduledMessage.customer_id==customer_id,ScheduledMessage.status=='SIMULADO')) or 0
    timeline=db.scalars(select(ScheduledMessage).where(
        ScheduledMessage.customer_id==customer_id
    ).order_by(ScheduledMessage.scheduled_date,ScheduledMessage.id)).all()
    next_index=next((i for i,row in enumerate(timeline) if row.status=='PENDENTE'),None)
    next_message=timeline[next_index] if next_index is not None else None
    simulated=[row for row in timeline if row.status=='SIMULADO']
    current_track=(next_message.track if next_message else simulated[-1].track if simulated else None)
    ordered_tracks=[item.track for item in sorted(customer.confirmed,key=lambda item:item.priority)]
    current_track_index=ordered_tracks.index(current_track) if current_track in ordered_tracks else -1
    next_track=ordered_tracks[current_track_index+1] if current_track_index+1<len(ordered_tracks) else None
    progress=round(len(simulated)/len(timeline)*100) if timeline else 0
    planned_finish=max((row.scheduled_date for row in timeline),default=None)
    contents={(item.track,item.number):item.content for item in db.scalars(select(CampaignMessage))}
    return render(request,'customer_detail.html',active='customers',customer=customer,sent=sent,
                  timeline=timeline,next_message=next_message,
                  current_week=(next_index+1 if next_index is not None else len(timeline)),
                  current_track=current_track,next_track=next_track,progress=progress,
                  planned_finish=planned_finish,contents=contents)

@router.post('/clientes/{customer_id}/aprovar',include_in_schema=False)
async def customer_approve(request:Request,customer_id:int,db:Session=Depends(get_db)):
    """Valida o formulário e confirma trilhas antes de persistir o cronograma."""
    form=await request.form()
    verify(request,form.get('csrf_token'))
    customer=db.scalar(select(Customer).options(selectinload(Customer.suggestions),selectinload(Customer.confirmed)).where(Customer.id==customer_id))
    if not customer: raise HTTPException(404)
    tracks=form.getlist('tracks')
    try:
        approve_customer(db,customer,tracks)
        db.commit()
    except ValueError as exc:
        db.rollback(); return back(f'/clientes/{customer_id}',error=str(exc))
    return back(f'/clientes/{customer_id}',message='Trilhas confirmadas e cronograma atualizado.')

@router.post('/clientes/{customer_id}/revogar',include_in_schema=False)
def customer_revoke(request:Request,customer_id:int,csrf_token:str=Form(...),db:Session=Depends(get_db)):
    """Revoga a aprovação e remove somente mensagens pendentes, preservando histórico."""
    verify(request,csrf_token)
    customer=db.get(Customer,customer_id)
    if not customer: raise HTTPException(404)
    customer.approved=False
    db.query(ConfirmedTrack).filter(ConfirmedTrack.customer_id==customer_id).delete()
    db.query(ScheduledMessage).filter(ScheduledMessage.customer_id==customer_id,ScheduledMessage.status=='PENDENTE').delete()
    db.commit()
    return back(f'/clientes/{customer_id}',message='Aprovação revogada. Histórico preservado.')

@router.get('/cronograma',response_class=HTMLResponse,include_in_schema=False)
def schedule_page(request:Request,start:str='',end:str='',q:str='',track:str='',page:int=Query(1,ge=1),db:Session=Depends(get_db)):
    """Exibe agendamentos filtrados por data, cliente e trilha."""
    query=schedule_query().join(Customer)
    try:
        if start: query=query.where(ScheduledMessage.scheduled_date>=date.fromisoformat(start))
        if end: query=query.where(ScheduledMessage.scheduled_date<=date.fromisoformat(end))
    except ValueError: raise HTTPException(400,'Data inválida.')
    if q: query=query.where(Customer.name.ilike(f'%{q[:80]}%'))
    if track in TRACKS: query=query.where(ScheduledMessage.track==track)
    records=db.scalars(query.offset((page-1)*50).limit(50)).all()
    count=db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    contents={(m.track,m.number):m.content for m in db.scalars(select(CampaignMessage))}
    return render(request,'schedule.html',active='schedule',records=records,contents=contents,
                  start=start,end=end,q=q,track=track,page=page,pages=max(1,(count+49)//50),count=count)

@router.post('/simulate',include_in_schema=False)
def simulate_action(request:Request,csrf_token:str=Form(...),db:Session=Depends(get_db)):
    """Executa a simulação local e salva resultados sem efetuar chamadas externas."""
    verify(request,csrf_token)
    try:
        simulated,failed=simulate_today(db)
        db.commit()
    except Exception:
        db.rollback();logger.exception('Erro interno na simulação')
        return back('/cronograma',error='Falha interna na simulação. Consulte os logs.')
    return back('/historico',message=f'{simulated} mensagens simuladas; {failed} ignoradas por telefone inválido ou template ausente.')

@router.get('/historico.csv',include_in_schema=False)
def history_csv(q:str='',start:str='',end:str='',track:str='',status:str='',db:Session=Depends(get_db)):
    """Exporta simulações verificadas na ordem prevista, sem expor credenciais."""
    query=history_query(q,start,end,track,status).join(
        ScheduledMessage,Simulation.scheduled_id==ScheduledMessage.id
    ).order_by(None).order_by(
        ScheduledMessage.scheduled_date,Simulation.customer_id,Simulation.id
    )
    records=db.scalars(query.options(selectinload(Simulation.customer),
                                    selectinload(Simulation.scheduled))).all()
    output=io.StringIO(newline='')
    writer=csv.writer(output)
    writer.writerow(['ID','Cliente','Telefone','Trilha','Mensagem','Data e hora','Endpoint','Método','Cabeçalhos','Corpo JSON','Status',
                     'Número da mensagem','Data prevista','Canal Botmaker','Requisição JSON'])
    for row in records:
        validate_export_record(row)
        secrets_found=collect_secrets({'headers':row.headers,'payload':row.payload})
        safe_headers=redact_export_value(row.headers,secrets_found)
        safe_payload=redact_export_value(row.payload,secrets_found)
        request_json=redact_export_value(
            {'endpoint':row.endpoint,'method':row.method,
             'headers':safe_headers,'body':safe_payload},
            secrets_found,
        )
        channel_id=safe_payload.get('chat',{}).get('channelId') if isinstance(safe_payload,dict) else None
        channel_status='PLACEHOLDER' if not channel_id or str(channel_id).startswith('<CONFIGURAR') else 'CONFIGURADO'
        clean=lambda value: csv_cell(redact_export_value(value,secrets_found))
        writer.writerow([row.id,clean(row.customer.name),clean(row.customer.phone),row.track,clean(row.content),
                        clean(row.simulated_at.isoformat(sep=' ')),clean(row.endpoint),clean(row.method),
                        json.dumps(safe_headers,ensure_ascii=False,sort_keys=True),
                        json.dumps(safe_payload,ensure_ascii=False,sort_keys=True),row.status,
                        row.number,row.scheduled.scheduled_date.isoformat(),channel_status,
                        json.dumps(request_json,ensure_ascii=False,sort_keys=True)])
    return Response(content='\ufeff'+output.getvalue(),media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition':'attachment; filename="campaignflow-historico.csv"'})

@router.get('/historico',response_class=HTMLResponse,include_in_schema=False)
def history_page(request:Request,q:str='',start:str='',end:str='',track:str='',status:str='',
                 page:int=Query(1,ge=1),db:Session=Depends(get_db)):
    """Lista simulações filtradas e paginadas."""
    query=history_query(q,start,end,track,status)
    count=db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    records=db.scalars(query.options(selectinload(Simulation.customer))
                       .offset((page-1)*40).limit(40)).all()
    return render(request,'history.html',active='history',records=records,page=page,
                  count=count,pages=max(1,(count+39)//40),q=q,start=start,end=end,
                  track=track,status=status)

@router.get('/historico/{simulation_id}',response_class=HTMLResponse,include_in_schema=False)
def history_detail(request:Request,simulation_id:int,db:Session=Depends(get_db)):
    """Apresenta metadados e payload persistidos de uma simulação."""
    simulation=db.get(Simulation,simulation_id)
    if not simulation: raise HTTPException(404)
    return render(request,'history_detail.html',active='history',simulation=simulation)

@router.get('/configuracoes',response_class=HTMLResponse,include_in_schema=False)
def settings_page(request:Request,db:Session=Depends(get_db)):
    """Exibe as preferências atuais de agendamento."""
    return render(request,'settings.html',active='settings',weekday=get_weekday(db),weekdays=WEEKDAYS)

@router.post('/configuracoes',include_in_schema=False)
def settings_save(request:Request,csrf_token:str=Form(...),weekday:int=Form(...),db:Session=Depends(get_db)):
    """Valida e salva o dia semanal, atualizando os agendamentos pendentes."""
    verify(request,csrf_token)
    try:
        set_weekday(db,weekday)
        db.commit()
    except ValueError as exc:
        db.rollback();return back('/configuracoes',error=str(exc))
    return back('/configuracoes',message='Dia de envio salvo. Cronograma pendente atualizado.')

@router.get('/api/indicadores',tags=['Leitura'])
def api_stats(db:Session=Depends(get_db)):
    """API somente leitura com totais resumidos para integrações e monitoramento."""
    return {'clientes':db.scalar(select(func.count(Customer.id))) or 0,
            'aprovados':db.scalar(select(func.count(Customer.id)).where(Customer.approved.is_(True))) or 0,
            'simulados':db.scalar(select(func.count(Simulation.id))) or 0}

@router.get('/api/clientes',tags=['Leitura'])
def api_customers(db:Session=Depends(get_db),limit:int=Query(25,ge=1,le=100),skip:int=Query(0,ge=0)):
    """API paginada de clientes; limites evitam respostas grandes sem controle."""
    return [{'id':c.id,'nome':c.name,'idade':c.age,'estado':c.state,'total':str(c.total),
             'itens':c.item_count,'aprovado':c.approved} for c in db.scalars(select(Customer).order_by(Customer.id).limit(limit).offset(skip))]
