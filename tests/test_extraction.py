"""Testa paginação, erros de API e persistência de arquivos brutos sem rede real."""
import json
from pathlib import Path
import pytest
import httpx
from app.services.dummyjson_service import fetch_all, save_raw, ExtractionError

@pytest.mark.parametrize('resource', ['users','carts'])
def test_fetch_all_paged_and_dedup(resource):
    calls=[]
    def handler(request):
        skip=int(request.url.params['skip']);limit=int(request.url.params['limit'])
        calls.append((skip,limit))
        return httpx.Response(200,json={resource:[{'id':i} for i in range(skip+1,min(skip+limit,5)+1)],'total':5,'skip':skip,'limit':limit})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        data=fetch_all(resource,client,page_size=2)
    assert [d['id'] for d in data]==[1,2,3,4,5]
    assert calls==[(0,2),(2,2),(4,2)]

def test_duplicates_detected_in_api():
    def handler(request):
        skip=int(request.url.params['skip'])
        return httpx.Response(200,json={'users':[{'id':1}] if skip==0 else [{'id':1}],'total':2})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ExtractionError,match='IDs únicos'): fetch_all('users',client,1)

@pytest.mark.parametrize('response', [httpx.Response(503),httpx.Response(200,text='not json'),httpx.Response(200,json={'foo':[]}),httpx.Response(200,json={'users':[],'total':2})])
def test_network_and_bad_response(response):
    with httpx.Client(transport=httpx.MockTransport(lambda req: response)) as client:
        with pytest.raises(ExtractionError):fetch_all('users',client,2)

def test_timeout_configured():
    def handler(request):
        assert request.extensions['timeout']['read']==12.0
        return httpx.Response(200,json={'users':[],'total':0})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert fetch_all('users',client)==[]

def test_raw_files_never_overwrite(tmp_path):
    files1=save_raw([{'id':1}],[{'id':2}],root=tmp_path)
    files2=save_raw([{'id':1}],[{'id':2}],root=tmp_path)
    assert len(set(files1+files2))==4
    assert len(list(tmp_path.rglob('*.json')))==4
    assert json.loads(Path(files1[0]).read_text())[0]['id']==1
