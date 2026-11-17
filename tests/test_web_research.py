import io,json
from dataclasses import replace,asdict
import pytest
from horse_racing.engine.publications import article_content,publisher_source,x_oembed,date_claim,public_url
from horse_racing.engine.discovery import entities,StdioSearch,Explorer
from horse_racing.engine.leakage import provenance_reasons,deterministic_gate,JudgePanel
from horse_racing.engine.model import Audit
from horse_racing.engine.pipeline import forecast

URL='https://www.hipodromodelazarzuela.es/noticias-destacadas/example'
RESPONSE=dict(text='',observed_at='2026-11-05T12:00:00Z',sha256='fixture_hash')
CUTOFF='2026-01-03T22:59:00Z'
TASK=dict(race_id='r',date='2026-01-04',venue='La Zarzuela',cutoff_utc=CUTOFF,track='publisher_documented',
    runners=[dict(runner_id='a',horse_name='ALPHA',jockey_name='J.TEST',trainer_name='T.TEST',stable_name='STABLE A'),
             dict(runner_id='b',horse_name='BETA',jockey_name='J.TEST',trainer_name='U.TEST',stable_name='STABLE B')])


def article(published='2025-12-20T12:00:00+01:00',modified=None):
    node={'@type':'NewsArticle','url':URL,'datePublished':published}
    if modified:node['dateModified']=modified
    return '<html><script type="application/ld+json">'+json.dumps(node)+'</script><article><h1>Earlier ALPHA form</h1><div class="field--name-body"><p>ALPHA trained with J.TEST over this distance before the planned January race. Earlier preparations were consistent.</p></div></article></html>'


def sourced(body):
    paragraphs,claims,meta=article_content(body,URL)
    return publisher_source(URL,RESPONSE,paragraphs,claims,**meta)


def test_publisher_evidence_requires_explicit_policy():
    s=sourced(article())
    assert provenance_reasons(s,CUTOFF,'publisher-dated')==[]
    assert 'publisher_dates_disallowed_in_strict_mode' in provenance_reasons(s,CUTOFF)
    assert s.receipt['edit_history'].startswith('Not independently')


def test_late_publication_and_late_update_are_hard_drops():
    for html in [article('2026-01-05T00:00:00Z'),article(modified='2026-01-06T00:00:00Z')]:
        s=sourced(html)
        assert 'source_available_after_cutoff' in provenance_reasons(s,CUTOFF,'publisher-dated')
    s=sourced(article());s=replace(s,available_at='2025-01-01T00:00:00Z')
    assert 'publisher_date_claim_mismatch' in provenance_reasons(s,CUTOFF,'publisher-dated')


def test_no_date_is_not_invented_from_search_snippets_or_fetch_time():
    html='<article><p>ALPHA has useful earlier racing form, but this article has no publication date or verifiable archive.</p></article>'
    paragraphs,claims,_=article_content(html,URL)
    with pytest.raises(ValueError,match='No supported'):publisher_source(URL,RESPONSE,paragraphs,claims)
    assert date_claim('2025-12-20T12:00:00','timezone_missing') is None


def test_sidebar_publication_dates_are_not_article_dates():
    html='<article><div class="field--name-field-date-published">20/12/2025</div><p>ALPHA has earlier racing form and preparation for similar conditions over this distance.</p></article><aside><div class="field--name-field-date-published">05/11/2026</div></aside>'
    s=sourced(html)
    assert provenance_reasons(s,CUTOFF,'publisher-dated')==[]
    assert len(s.receipt['date_claims'])==1


def test_future_race_preview_date_is_not_automatically_a_realized_fact():
    s=sourced(article())
    text='ALPHA won an earlier race and will run in the upcoming race on 2026-01-04.'
    assert deterministic_gate(s,text,CUTOFF,'publisher-dated')['allow']
    assert not deterministic_gate(s,'ALPHA won the race on 2026-01-04.',CUTOFF,'publisher-dated')['allow']


def test_x_extraction_keeps_single_post_not_live_engagement_counts():
    url='https://x.com/HipodromoMadrid/status/1943678985956737151'
    body=dict(url=url,author_name='Synthetic author',author_url='https://x.com/HipodromoMadrid',
         html='<blockquote class="twitter-tweet"><p>ALPHA prepared for the earlier race with jockey J.TEST.</p>July 11, 2025</blockquote>')
    s=x_oembed(url,dict(RESPONSE,text=json.dumps(body)))
    assert s.receipt['platform']=='X' and s.available_at.startswith('2025-07-11')
    assert s.passages==('ALPHA prepared for the earlier race with jockey J.TEST.',)
    body['url']='https://x.com/other/status/1943678985956737152'
    with pytest.raises(ValueError,match='identity'):x_oembed(url,dict(RESPONSE,text=json.dumps(body)))


def test_all_entity_kinds_are_scheduled_without_duplicate_connections():
    e=entities(TASK)
    assert [x['kind'] for x in e[:4]]==['horse','jockey','trainer','stable']
    assert len([x for x in e if x['kind']=='jockey'])==1


def test_stdio_search_bridge_matches_request_and_does_not_create_evidence():
    from horse_racing.db import uid
    query='ALPHA horse';request=uid(query,CUTOFF,'web')
    output=io.StringIO();provider=StdioSearch(io.StringIO(json.dumps(dict(request_id=request,results=[dict(url=URL,title='Discovery only',snippet='UNTRUSTED LATER OUTCOME')]))+'\n'),output)
    results=provider(query,CUTOFF,'web')
    assert results[0]['snippet']=='UNTRUSTED LATER OUTCOME'
    assert json.loads(output.getvalue())['event']=='web_search_request'
    with pytest.raises(ValueError):StdioSearch(io.StringIO('{"request_id":"wrong","results":[]}\n'),io.StringIO())(query,CUTOFF,'web')


def test_explorer_cannot_fetch_model_invented_urls(tmp_path):
    explorer=Explorer(tmp_path/'cache',Audit(tmp_path/'audit.jsonl'),None,TASK)
    with pytest.raises(ValueError,match='not discovered'):explorer.page('https://example.com/model-invented',CUTOFF)
    for u in ['https://127.0.0.1/a','https://foo.local/a','https://user:pass@example.com/a','http://example.com/a','https://example.com:444/a']:
        assert not public_url(u)


def test_article_body_preferred_over_empty_header_and_footer_widgets():
    html='<article><div class="field--name-body"><h1>News</h1></div><div class="field--name-field-date-published">20/12/2025</div><div class="field--name-field-description"><p>ALPHA prepared consistently with jockey J.TEST for earlier races over a similar distance.</p></div></article><footer><div class="field--name-body"><p>Unrelated current social media and site navigation material must never replace the article body.</p></div></footer>'
    s=sourced(html)
    assert len(s.passages)==1 and s.passages[0].startswith('ALPHA prepared')


def test_nested_publisher_related_articles_do_not_supply_primary_article_dates():
    html='<article class="node--view-mode-full"><div class="field--name-field-date-published">20/12/2025</div><div class="field--name-field-description"><p>ALPHA prepared consistently with J.TEST for earlier races over a similar distance and surface.</p></div><article class="node--view-mode-teaser"><div class="field--name-field-date-published">04/11/2026</div><p>A separate current news story and its publication date belong to a different article entirely.</p></article></article>'
    s=sourced(html)
    assert len(s.receipt['date_claims'])==1 and provenance_reasons(s,CUTOFF,'publisher-dated')==[]
    assert len(s.passages)==1 and 'separate current' not in s.passages[0]
