#!/usr/bin/env python3
"""Public RSS travel lead finder. Results are discovery leads, not confirmed bookings."""
import base64, hashlib, hmac, html, os, re, smtplib, ssl, time, unicodedata, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
import requests
BASE=os.environ.get('SUPABASE_URL','').rstrip('/'); KEY=os.environ.get('SUPABASE_SERVICE_ROLE_KEY',''); SITE=os.environ.get('PUBLIC_SITE_URL','').rstrip('/'); TOKEN_SECRET=os.environ.get('MANAGE_TOKEN_SECRET','')
SMTP_HOST=os.environ.get('SMTP_HOST','smtp.web.de'); SMTP_PORT=int(os.environ.get('SMTP_PORT','587')); SMTP_USER=os.environ.get('SMTP_USER',''); SMTP_PASSWORD=os.environ.get('SMTP_PASSWORD',''); SMTP_FROM=os.environ.get('SMTP_FROM','') or SMTP_USER
MAX_ARTICLE_AGE_DAYS=int(os.environ.get('MAX_ARTICLE_AGE_DAYS','30'))
MAX_FEED_BYTES=2_000_000
LOCALES=[
 {'names':['croatia','hrvatska','hr'],'hl':'hr','gl':'HR','ceid':'HR:hr','bing':'hr-HR','terms':'hotel resort apartman smještaj ljetovanje ponuda akcija obiteljski odmor'},
 {'names':['germany','deutschland','njemačka','njemacka','de'],'hl':'de','gl':'DE','ceid':'DE:de','bing':'de-DE','terms':'hotel resort unterkunft angebot familienurlaub ferienangebot'},
 {'names':['austria','österreich','osterreich','austrija','at'],'hl':'de','gl':'AT','ceid':'AT:de','bing':'de-AT','terms':'hotel resort unterkunft angebot familienurlaub urlaub'},
 {'names':['italy','italia','italija','it'],'hl':'it','gl':'IT','ceid':'IT:it','bing':'it-IT','terms':'hotel resort appartamento vacanza offerta famiglia'},
 {'names':['slovenia','slovenija','si'],'hl':'sl','gl':'SI','ceid':'SI:sl','bing':'sl-SI','terms':'hotel resort apartma nastanitev ponudba družinske počitnice'},
 {'names':['france','francuska','fr'],'hl':'fr','gl':'FR','ceid':'FR:fr','bing':'fr-FR','terms':'hôtel resort séjour offre vacances famille'},
 {'names':['spain','españa','espana','španjolska','spanjolska','es'],'hl':'es','gl':'ES','ceid':'ES:es','bing':'es-ES','terms':'hotel resort alojamiento oferta vacaciones familia'},
 {'names':['greece','ellada','grčka','grcka','gr'],'hl':'el','gl':'GR','ceid':'GR:el','bing':'el-GR','terms':'ξενοδοχείο resort διακοπές προσφορά οικογένεια'},
 {'names':['portugal','pt'],'hl':'pt-PT','gl':'PT','ceid':'PT:pt-PT','bing':'pt-PT','terms':'hotel resort alojamento oferta férias família'},
 {'names':['netherlands','nederland','nizozemska','nl'],'hl':'nl','gl':'NL','ceid':'NL:nl','bing':'nl-NL','terms':'hotel resort accommodatie aanbieding vakantie gezin'},
 {'names':['united kingdom','uk','great britain','england','gb'],'hl':'en-GB','gl':'GB','ceid':'GB:en','bing':'en-GB','terms':'hotel resort accommodation family holiday deal offer'},
 {'names':['united states','usa','us'],'hl':'en-US','gl':'US','ceid':'US:en','bing':'en-US','terms':'hotel resort accommodation family vacation deal offer'}]
DEFAULT_LOCALE={'hl':'en','gl':'US','ceid':'US:en','bing':'en-US','terms':'hotel resort accommodation family holiday deal offer'}
PUBLIC_DEAL_FEEDS=[('Travelzoo public feed','https://www.travelzoo.com/feed/','Travelzoo','https://www.travelzoo.com/'),('Travel-Dealz public feed','https://travel-dealz.com/feed/','Travel-Dealz','https://travel-dealz.com/')]
_PUBLIC_DEAL_CACHE=None
_RSS_CACHE={}
SESSION=requests.Session(); SESSION.headers.update({'User-Agent':'HolidayRadar/1.0 (public travel lead discovery)','Accept':'application/rss+xml, application/xml, text/xml, */*'})
class RadarError(Exception): pass
def now(): return datetime.now(timezone.utc)
def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def management_token(sub_id):
    secret=os.environ.get('MANAGE_TOKEN_SECRET','')
    if not secret: raise RadarError('MANAGE_TOKEN_SECRET is missing')
    raw=hmac.new(secret.encode(),('holiday-radar/manage/'+str(sub_id)).encode(),hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')
def db(method,table,params=None,payload=None,prefer=None):
    if not BASE or not KEY: raise RadarError('Supabase settings are missing')
    h={'apikey':KEY,'Authorization':'Bearer '+KEY,'Content-Type':'application/json'}
    if prefer:h['Prefer']=prefer
    r=requests.request(method,BASE+'/rest/v1/'+table,params=params,json=payload,headers=h,timeout=20);r.raise_for_status()
    return r.json() if r.content else []
def canonical(url):
    try:
        p=urlsplit(url.strip())
        if p.scheme not in ('http','https') or not p.netloc:return None
        q=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in {'gclid','fbclid','mc_cid','mc_eid'}]
        return urlunsplit((p.scheme,p.netloc.lower(),p.path or '/',urlencode(q),''))
    except Exception:return None
def plain(s):return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',s or ''))).strip()
def normalize_text(value):
    value=unicodedata.normalize('NFKD',value or '')
    return re.sub(r'\s+',' ',''.join(c for c in value if not unicodedata.combining(c))).strip().lower()
def parse_published(value):
    value=plain(value)
    if not value:return None
    try:dt=parsedate_to_datetime(value)
    except (TypeError,ValueError,OverflowError):
        try:dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError:return None
    if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()
def local_name(tag):return tag.rsplit('}',1)[-1].lower()
def parse_feed(data,feed_name):
    if len(data)>MAX_FEED_BYTES:return []
    try:root=ET.fromstring(data)
    except ET.ParseError:return []
    entries=[n for n in root.iter() if local_name(n.tag) in ('item','entry')]
    rows=[]
    for node in entries[:40]:
        fields={}
        for child in list(node):fields.setdefault(local_name(child.tag),child)
        title_node=fields.get('title');title=plain(''.join(title_node.itertext()) if title_node is not None else '')
        link_nodes=[child for child in list(node) if local_name(child.tag)=='link']
        link_node=next((child for child in link_nodes if child.attrib.get('rel','alternate')=='alternate'),link_nodes[0] if link_nodes else None)
        raw_link=''
        if link_node is not None:raw_link=link_node.attrib.get('href','') or ''.join(link_node.itertext()).strip()
        link=canonical(raw_link)
        if not link:
            for child in node.iter():
                if local_name(child.tag)=='link':
                    link=canonical(child.attrib.get('href','') or ''.join(child.itertext()))
                    if link:break
        desc_node=fields.get('description')
        if desc_node is None:desc_node=fields.get('summary')
        if desc_node is None:desc_node=fields.get('content')
        snippet=plain(''.join(desc_node.itertext()) if desc_node is not None else '')
        date_node=fields.get('pubdate')
        if date_node is None:date_node=fields.get('published')
        if date_node is None:date_node=fields.get('updated')
        if date_node is None:date_node=fields.get('date')
        published=parse_published(''.join(date_node.itertext()) if date_node is not None else '')
        source_node=fields.get('source');publisher=plain(''.join(source_node.itertext()) if source_node is not None else '')
        publisher_url=canonical(source_node.attrib.get('url','')) if source_node is not None else None
        if title and link:rows.append({'title':title[:350],'url':link,'snippet':snippet[:1200],'published_at':published,'publisher':publisher[:160],'publisher_url':publisher_url,'source':feed_name,'sources':[feed_name],'links':[{'label':feed_name,'url':link}]})
    return rows
def country_locales(f):
    selected=[]
    for country in f.get('countries') or []:
        normalized=normalize_text(str(country))
        for locale in LOCALES:
            if any(normalized==normalize_text(alias) for alias in locale['names']):
                if locale not in selected:selected.append(locale)
                break
        if len(selected)>=2:break
    if not selected:selected=[DEFAULT_LOCALE]
    if len(selected)==1 and selected[0] is not DEFAULT_LOCALE and selected[0]['gl']!='US':selected.append(DEFAULT_LOCALE)
    return selected[:2]
def queries(f):
    places=(f.get('destinations') or [])[:8]+(f.get('countries') or [])[:5]
    place=' OR '.join('"'+str(x).replace('"','')[:80]+'"' for x in places if str(x).strip())
    kind={'hotel':'hotel OR resort OR accommodation','apartment':'apartment OR apartman OR Ferienwohnung','camping':'camping OR campsite','resort':'resort OR hotel','holiday_home':'holiday home OR villa OR vacation rental'}.get(f.get('accommodation'),'hotel OR resort OR apartment OR accommodation')
    result=[]
    for locale in country_locales(f):
        q=f'({place}) ({kind}) ({locale["terms"]})'
        meal={'breakfast':'breakfast OR frühstück OR doručak','half_board':'half board OR polupansion OR halbpension','full_board':'full board OR puni pansion','all_inclusive':'all inclusive OR all-inclusive','self_catering':'self catering OR kuhinja'}.get(f.get('meal_plan'))
        if meal:q+=' ('+meal+')'
        if f.get('features'):q+=' '+' '.join(str(x)[:40] for x in f['features'][:2])
        q+=' after:'+ (now()-timedelta(days=MAX_ARTICLE_AGE_DAYS)).date().isoformat()
        result.append((locale,q[:650]))
    return result
def feeds(q,locale):
    return [('Google News RSS','https://news.google.com/rss/search',{'q':q,'hl':locale['hl'],'gl':locale['gl'],'ceid':locale['ceid']}),('Bing News RSS','https://www.bing.com/news/search',{'q':q,'format':'rss','count':'40','cc':locale['gl'],'setlang':locale['bing']})]
def fetch_feed(url,params=None):
    key=(url,tuple(sorted((params or {}).items())))
    if key in _RSS_CACHE:return _RSS_CACHE[key]
    error=None
    for attempt in range(3):
        try:
            response=SESSION.get(url,params=params or {},timeout=20)
            if response.status_code in (429,500,502,503,504):
                try:wait=min(8,max(1,int(response.headers.get('Retry-After',''))))
                except ValueError:wait=1+attempt*2
                time.sleep(wait)
            response.raise_for_status()
            data=response.content if len(response.content)<=MAX_FEED_BYTES else b''
            _RSS_CACHE[key]=data
            return data
        except requests.RequestException as exc:
            error=exc
            if attempt<2:time.sleep(1+attempt*2)
    print('RSS request retries exhausted:',type(error).__name__ if error else 'unknown error')
    _RSS_CACHE[key]=b''
    return b''
def public_deal_offers():
    global _PUBLIC_DEAL_CACHE
    if _PUBLIC_DEAL_CACHE is not None:return _PUBLIC_DEAL_CACHE
    _PUBLIC_DEAL_CACHE=[]
    for name,url,publisher,publisher_home in PUBLIC_DEAL_FEEDS:
        try:
            items=parse_feed(fetch_feed(url),name)
            for item in items:
                item['publisher']=item.get('publisher') or publisher
                item['publisher_url']=item.get('publisher_url') or canonical(publisher_home)
                item['sources']=[name];item['source']=name
                _PUBLIC_DEAL_CACHE.append(item)
        except requests.RequestException as exc:print('public deal feed unavailable:',name,type(exc).__name__)
        time.sleep(.5)
    return _PUBLIC_DEAL_CACHE
def country_match_terms(filters):
    terms=list(filters.get('destinations') or [])+list(filters.get('countries') or [])
    for country in filters.get('countries') or []:
        key=normalize_text(str(country))
        for locale in LOCALES:
            if any(key==normalize_text(alias) for alias in locale['names']):
                terms.extend(locale['names']);break
    return [normalize_text(str(x)) for x in terms if len(str(x).strip())>2]
def relevant_public_deal(item,filters):
    text=normalize_text(item.get('title','')+' '+item.get('snippet',''))
    place=any(term in text for term in country_match_terms(filters))
    stay=any(normalize_text(x) in text for x in ('hotel','resort','apartment','apartman','accommodation','ferienwohnung','vacation rental','camping','campsite','smještaj','smjestaj','stay in','room rate'))
    return place and stay
def merge_item(found,item):
    publisher_host=(urlsplit(item.get('publisher_url') or '').hostname or '').lower()
    pubday=(item.get('published_at') or '')[:10]
    key=hashlib.sha256((publisher_host+'|'+normalize_text(item['title'])+'|'+pubday).encode()).hexdigest() if publisher_host else item['url']
    if key not in found:
        found[key]=item
        return
    old=found[key]
    for source in item.get('sources',[]):
        if source not in old['sources']:old['sources'].append(source)
    old['source']=' + '.join(old['sources'])
    old['links'].extend(x for x in item.get('links',[]) if x not in old['links'])
    if not old.get('publisher') and item.get('publisher'):old['publisher']=item['publisher']
    if not old.get('publisher_url') and item.get('publisher_url'):old['publisher_url']=item['publisher_url']
    if not old.get('published_at') and item.get('published_at'):old['published_at']=item['published_at']
    if 'news.google.com' in (urlsplit(old['url']).hostname or '') and 'news.google.com' not in (urlsplit(item['url']).hostname or ''):old['url']=item['url']
def price_mention(text,currency):
    sym={'EUR':r'(?:€|EUR)','USD':r'(?:\$|USD)','GBP':r'(?:£|GBP)','CHF':r'CHF','CAD':r'(?:C\$|CAD)','AUD':r'(?:A\$|AUD)'}.get(currency,r'€')
    for pat in (rf'{sym}\s?([0-9][0-9., ]{{1,12}})',rf'([0-9][0-9., ]{{1,12}})\s?{sym}'):
        m=re.search(pat,text,re.I)
        if not m:continue
        raw=m.group(1).replace(' ','')
        if ',' in raw and '.' in raw:
            decimal=',' if raw.rfind(',')>raw.rfind('.') else '.';thousands='.' if decimal==',' else ','
            raw=raw.replace(thousands,'').replace(decimal,'.')
        elif ',' in raw or '.' in raw:
            sep=',' if ',' in raw else '.';left,right=raw.rsplit(sep,1)
            raw=left+right if len(right)==3 and len(left)<=3 else left+'.'+right
        try:
            value=float(raw)
            if 1<=value<=10_000_000:return value
        except ValueError:pass
    return None
def freshness(o,reference=None):
    stamp=o.get('published_at')
    if not stamp:return None,'datum objave nije dostupan'
    try:
        dt=datetime.fromisoformat(stamp.replace('Z','+00:00'))
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        days=max(0,int(((reference or now())-dt).total_seconds()//86400))
    except (ValueError,TypeError):return None,'datum objave nije moguće protumačiti'
    return days,('objavljeno danas' if days==0 else 'objavljeno jučer' if days==1 else f'objavljeno prije {days} dana')
def rank(o,f,reference=None):
    text=normalize_text(o['title']+' '+o['snippet']);terms=[]
    place_terms=country_match_terms(f)
    place_matches=[str(t) for t in place_terms if len(str(t).strip())>2 and normalize_text(str(t)) in text]
    terms.extend(place_terms);terms.extend(f.get('features') or [])
    terms+= {'hotel':['hotel'],'apartment':['apartment','apartments','apartman'],'camping':['camping','campsite'],'resort':['resort'],'holiday_home':['holiday home','villa']}.get(f.get('accommodation'),[])
    matched=sorted(set(normalize_text(str(t)) for t in terms if len(str(t).strip())>2 and normalize_text(str(t)) in text))
    age,age_text=freshness(o,reference); price=price_mention(text,f.get('currency','EUR'))
    stay=any(normalize_text(x) in text for x in ('hotel','resort','apartment','apartman','accommodation','ferienwohnung','vacation rental','camping','campsite','smještaj','smjestaj','hôtel','alojamiento'))
    deal=any(normalize_text(x) in text for x in ('deal','offer','discount','package','last minute','ponuda','akcija','popust','angebot','rabatt','offerta','oferta'))
    points=0;evidence=[]
    if o.get('publisher'):points+=1;evidence.append('RSS navodi izdavača')
    if age is not None:
        if age<=7:points+=2
        elif age<=MAX_ARTICLE_AGE_DAYS:points+=1
        evidence.append(age_text)
    else:evidence.append(age_text)
    if place_matches:points+=2;evidence.append('destinacija/država spomenuta u naslovu/opisu')
    else:evidence.append('destinacija nije potvrđena u naslovu/opisu')
    if stay:points+=1;evidence.append('spominje se smještaj')
    if deal or price is not None:points+=1;evidence.append('spominje se ponuda ili iznos')
    if len(o.get('sources',[]))>1:points+=1;evidence.append('pronađeno u više RSS feedova')
    # This grades metadata completeness and relevance, not provider legitimacy or booking certainty.
    grade='jači trag' if points>=6 else 'srednji trag' if points>=4 else 'slab trag'
    return points,matched,price,{'published_age_days':age,'freshness':age_text,'evidence':evidence,'evidence_grade':grade}
def find(f):
    found={}
    for locale,q in queries(f):
        for source,url,params in feeds(q,locale):
            try:
                for item in parse_feed(fetch_feed(url,params),source):merge_item(found,item)
            except requests.RequestException as exc:print('RSS source unavailable:',source,type(exc).__name__)
            time.sleep(.5)
    # Curated public deal-editor feeds are polled once per Actions run, then locally filtered per user.
    for cached in public_deal_offers():
        item={**cached,'sources':list(cached.get('sources',[])),'links':[dict(link) for link in cached.get('links',[])]}
        if relevant_public_deal(item,f):merge_item(found,item)
    rows=[]
    for item in found.values():
        item['score'],item['matched'],item['price_mention'],meta=rank(item,f);item.update(meta)
        if item['published_age_days'] is not None and item['published_age_days']>MAX_ARTICLE_AGE_DAYS:continue
        rows.append(item)
    return sorted(rows,key=lambda item:(-item['score'],item['published_age_days'] if item['published_age_days'] is not None else 999,item['title'].lower()))[:10]
def site(q):return SITE+'/?'+q
def send(to,subject,text,body):
    if not all((SMTP_USER,SMTP_PASSWORD,SMTP_FROM,SMTP_HOST)):raise RadarError('SMTP settings incomplete')
    msg=EmailMessage();msg['Subject']=subject;msg['From']=SMTP_FROM;msg['To']=to;msg['Reply-To']=SMTP_FROM;msg.set_content(text);msg.add_alternative(body,subtype='html')
    if SMTP_PORT==465:
        with smtplib.SMTP_SSL(SMTP_HOST,SMTP_PORT,timeout=30,context=ssl.create_default_context()) as s:s.login(SMTP_USER,SMTP_PASSWORD);s.send_message(msg)
    else:
        with smtplib.SMTP(SMTP_HOST,SMTP_PORT,timeout=30) as s:s.ehlo();s.starttls(context=ssl.create_default_context());s.ehlo();s.login(SMTP_USER,SMTP_PASSWORD);s.send_message(msg)
def send_confirmation(row):
    import secrets
    confirm=secrets.token_urlsafe(36);manage=management_token(row['id'])
    db('PATCH','subscriptions',{'id':'eq.'+row['id']},{'confirm_token_hash':digest(confirm),'manage_token_hash':digest(manage),'updated_at':now().isoformat()},'return=minimal')
    c=site('confirm='+quote(confirm));m=site('manage='+quote(manage));u=site('unsubscribe='+quote(manage))
    text=f'Potvrdi e-mail: {c}\n\nUpravljanje postavkama: {m}\nOdjava: {u}\n\nAko nisi zatražio/la pretplatu, zanemari poruku.'
    body=f'<h2>Potvrdi svoj Holiday Radar</h2><p><a href="{html.escape(c)}">Potvrdi e-mail</a></p><p><a href="{html.escape(m)}">Upravljanje postavkama</a> · <a href="{html.escape(u)}">Odjava</a></p><p>Ako nisi zatražio/la pretplatu, zanemari poruku.</p>'
    send(row['email'],'Potvrdi svoj Holiday Radar',text,body)
    db('PATCH','subscriptions',{'id':'eq.'+row['id']},{'confirmation_sent_at':now().isoformat()},'return=minimal')
def stable_offer_hash(item):
    host=(urlsplit(item.get('publisher_url') or '').hostname or '').lower()
    if host and item.get('title'):
        identity=host+'|'+normalize_text(item['title'])+'|'+(item.get('published_at') or '')[:10]
        return digest(identity)
    return digest(item['url'])
def trip(f):
    d=', '.join(f.get('destinations') or []) or 'odabrana destinacija';period=(f.get('date_from') or 'fleksibilno')+' – '+(f.get('date_to') or 'fleksibilno')
    guests=f"{f.get('adults',2)} odraslih"+((', djeca: '+', '.join(map(str,f['children_ages']))+' g.') if f.get('children_ages') else '')
    return f'{d} · {period} · {guests}'
def process(row):
    f=row.get('filters') or {}
    frequency=int(f.get('frequency_hours') or 24)
    last=row.get('last_scanned_at')
    if last:
        try:
            if now()-datetime.fromisoformat(last.replace('Z','+00:00'))<timedelta(hours=frequency):return
        except ValueError:pass
    offers=find(f)
    old=db('GET','deliveries',{'select':'offer_hash','subscription_id':'eq.'+row['id'],'order':'sent_at.desc','limit':'500'})
    seen={x['offer_hash'] for x in old}
    token=management_token(row['id']);tokenhash=digest(token)
    if row.get('manage_token_hash')!=tokenhash:
        db('PATCH','subscriptions',{'id':'eq.'+row['id']},{'manage_token_hash':tokenhash},'return=minimal')
    manage_url=site('manage='+quote(token));unsubscribe_url=site('unsubscribe='+quote(token));sent=0
    for o in offers:
        offer_hash=stable_offer_hash(o)
        legacy_hash=digest(o['url'])
        if offer_hash in seen or legacy_hash in seen or sent>=3:continue
        title=o['title'];source=o.get('source','RSS');url=o['url'];summary=trip(f)
        publisher=o.get('publisher') or 'izdavač nije naveden u RSS-u'
        age=o.get('freshness','datum objave nije dostupan')
        evidence='; '.join(o.get('evidence',[])) or 'ograničeni RSS metapodaci'
        grade=o.get('evidence_grade','slab trag');score_value=o.get('score',0)
        if o.get('price_mention') is None:
            price='Nije pronađen iznos u RSS naslovu/opisu.'
        else:
            price=(f"RSS tekst spominje {o['price_mention']:,.2f} {f.get('currency','EUR')} — nije potvrđeno da je to cijena smještaja ili ukupna cijena.").replace(',',' ')
        alternate_links=[x for x in o.get('links',[]) if x.get('url') and x['url']!=url][:3]
        alternate_text=''.join('\nAlternativni RSS rezultat ('+str(x.get('label','RSS'))+'): '+x['url'] for x in alternate_links)
        alternate_html=''.join(f"<li><a href=\"{html.escape(x.get('url',''),quote=True)}\">Alternativni RSS rezultat ({html.escape(x.get('label','RSS'))})</a></li>" for x in alternate_links)
        publisher_url=o.get('publisher_url')
        publisher_link='';publisher_link_text=''
        if publisher_url:
            publisher_link='\nWeb-stranica izdavača (nije nužno izravni članak): '+publisher_url
            publisher_link_text=f'<br><a href="{html.escape(publisher_url,quote=True)}">Web-stranica izdavača (nije nužno izravni članak)</a>'
        text=(f"{grade.upper()} · {title}\n\nČlanak / rezultat: {url}{alternate_text}{publisher_link}\n\nIzdavač: {publisher}\nDatum: {age}\nRSS kanal(i): {source}\nSignal: {score_value}/8 ({evidence})\nPutovanje: {summary}\n{price}\n\nOvo nije potvrđena raspoloživost ni ponuda. Provjeri cijenu, datume, goste, poreze i uvjete na izvornoj stranici.\n\nUredi kriterije: {manage_url}\nOdjava: {unsubscribe_url}")
        safe_title=html.escape(title)
        body=(f'<h2>{html.escape(grade.capitalize())}: {safe_title}</h2>'
              f'<p><a href="{html.escape(url,quote=True)}">Otvori članak / rezultat</a></p>'
              + (f'<ul>{alternate_html}</ul>' if alternate_html else '')
              + f'<p>Izdavač: {html.escape(publisher)}{publisher_link_text}<br>Datum: {html.escape(age)}<br>'
              f'RSS kanal(i): {html.escape(source)}<br>Signal: {score_value}/8 — {html.escape(evidence)}<br>'
              f'Putovanje: {html.escape(summary)}<br>{html.escape(price)}</p>'
              '<p><strong>Ovo nije potvrđena raspoloživost ni ponuda.</strong> Provjeri cijenu, datume, goste, poreze i uvjete na izvoru.</p>'
              f'<p><a href="{html.escape(manage_url)}">Uredi kriterije</a> · <a href="{html.escape(unsubscribe_url)}">Odjava</a></p>')
        send(row['email'],f"{grade.capitalize()}: {title[:90]}",text,body)
        try:
            db('POST','deliveries',payload={'subscription_id':row['id'],'offer_hash':offer_hash,'source_url':url},prefer='return=minimal')
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code!=409:raise
        seen.add(offer_hash);seen.add(legacy_hash);sent+=1
    db('PATCH','subscriptions',{'id':'eq.'+row['id']},{'last_scanned_at':now().isoformat(),'updated_at':now().isoformat()},'return=minimal')
    print('scanned one subscription; new lead messages:',sent)

def main():
    if not SITE.startswith('https://'):raise RadarError('PUBLIC_SITE_URL must be the published HTTPS URL')
    pending=db('GET','subscriptions',{'select':'id,email,created_at,confirmation_sent_at','status':'eq.pending','order':'created_at.asc','limit':'50'})
    for row in pending:
        try:
            created=datetime.fromisoformat(row['created_at'].replace('Z','+00:00'))
            if now()-created>timedelta(days=14):db('DELETE','subscriptions',{'id':'eq.'+row['id']});continue
            last=row.get('confirmation_sent_at');due=not last or now()-datetime.fromisoformat(last.replace('Z','+00:00'))>timedelta(hours=24)
            if due:
                try:send_confirmation(row);print('confirmation sent')
                except Exception as e:print('confirmation delivery failed:',type(e).__name__)
        except Exception as e:print('pending processing failed:',type(e).__name__)
    active=db('GET','subscriptions',{'select':'id,email,filters,manage_token_hash,last_scanned_at','status':'eq.active','order':'created_at.asc','limit':'500'})
    for row in active:
        try:process(row)
        except Exception as e:print('active scan failed:',type(e).__name__)
if __name__=='__main__':main()
