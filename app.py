"""Private local job search and application journal. Python 3.11+; optional local PDF parsing with pypdf."""
from __future__ import annotations
import argparse, concurrent.futures, datetime as dt, hashlib, html, ipaddress, json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from pathlib import Path
import re, secrets, socket, sqlite3, threading, time
import urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from research import classify, TRACKS
import resume_profile, discovery
ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('JOB_COMPASS_OSS_DATA',str(ROOT/'data')))
DB=DATA/'jobs.sqlite3'
PORT=int(os.environ.get('JOB_COMPASS_OSS_PORT','18866'))
TOKEN=secrets.token_urlsafe(32)
LOCK=threading.Lock()
STATUSES=['已投递','已回复','面试中','Offer','已拒绝','已撤回']
AI=re.compile(r'\b(ai|ki|llm|nlp|rag|ml|python|data science|machine learning|deep learning|natural language|computer vision|generative|agentic|agents?|language model)\b|künstliche intelligenz|sprachverarbeitung|maschinelles lernen',re.I)
STUDENT=re.compile(r'werkstudent|werkstudier|hiwi|working.student|student.assistant|studentische|hilfskraft|\bthesis\b|master.?arbeit|bachelor.?arbeit|abschluss.?arbeit|student.*research|research.*student',re.I)
CITIES=['frankfurt','darmstadt','berlin','munich','münchen','stuttgart','hamburg','cologne','köln','karlsruhe','mannheim','heidelberg','walldorf','tübingen','vienna','wien','zurich','zürich','remote','germany','deutschland']

def now():
    # Europe/Berlin rules, independent of optional Windows tzdata package.
    utc=dt.datetime.now(dt.timezone.utc)
    def sunday(month):
        d=dt.datetime(utc.year,month,31,1,tzinfo=dt.timezone.utc)
        return d-dt.timedelta(days=(d.weekday()+1)%7)
    return utc.astimezone(dt.timezone(dt.timedelta(hours=2 if sunday(3)<=utc<sunday(10) else 1)))
def stamp():return now().isoformat(timespec='seconds')
def today():return now().date().isoformat()
def connect():
    c=sqlite3.connect(DB,timeout=30);c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA foreign_keys=ON');return c
def init():
    DATA.mkdir(parents=True,exist_ok=True)
    with connect() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,url TEXT UNIQUE NOT NULL,title TEXT NOT NULL,company TEXT DEFAULT '',location TEXT DEFAULT '',kind TEXT DEFAULT '',description TEXT DEFAULT '',languages TEXT DEFAULT '',source TEXT DEFAULT '',published TEXT DEFAULT '',first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,verified_at TEXT DEFAULT '',deadline TEXT DEFAULT '',score INTEGER DEFAULT 0,region INTEGER DEFAULT 0,saved INTEGER DEFAULT 0,hidden INTEGER DEFAULT 0,availability TEXT DEFAULT '未核实');
CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT UNIQUE NOT NULL REFERENCES jobs(id),applied_on TEXT NOT NULL,status TEXT NOT NULL DEFAULT '已投递',next_followup TEXT DEFAULT '',notes TEXT DEFAULT '',updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,application_id INTEGER NOT NULL REFERENCES applications(id),occurred_on TEXT NOT NULL,status TEXT NOT NULL,note TEXT DEFAULT '',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT,started TEXT NOT NULL,finished TEXT DEFAULT '',state TEXT DEFAULT 'running',added INTEGER DEFAULT 0,details TEXT DEFAULT '[]');
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);''')
        columns={r[1] for r in c.execute('PRAGMA table_info(jobs)')}
        for name in ('research_meta','organization_type','opportunity_type','opportunity_note'):
            if name not in columns:c.execute('ALTER TABLE jobs ADD COLUMN '+name+" TEXT NOT NULL DEFAULT ''")
        for row in c.execute('SELECT * FROM jobs').fetchall():
            metadata=classify(dict(row))
            c.execute('UPDATE jobs SET research_meta=? WHERE id=?',(json.dumps(metadata,ensure_ascii=False),row['id']))
        for k,v in {'daily_hour':'9','auto_update':'false','extra_queries':'[]'}.items():c.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',(k,v))
def clean(s):return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]+>',' ',str(s or '')))).strip()
def canonical(url):
    p=urllib.parse.urlsplit(url.strip())
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:raise ValueError('请输入完整的 http 或 https 招聘链接')
    q=[(k,v) for k,v in urllib.parse.parse_qsl(p.query,keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in ('gclid','fbclid','ref','source','trackingid') and not (p.hostname.endswith('.jobs.personio.com') and k=='language')]
    return urllib.parse.urlunsplit((p.scheme,p.netloc.lower(),p.path.rstrip('/') or '/',urllib.parse.urlencode(q),''))
def public_url(url):
    url=canonical(url);p=urllib.parse.urlsplit(url)
    if p.port not in (None,80,443):raise ValueError('仅支持标准网页端口')
    for e in socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(e[4][0]).is_global:raise ValueError('招聘链接必须是公开网站，不能是本机或内网地址')
    return url
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        public_url(newurl);return super().redirect_request(req,fp,code,msg,headers,newurl)
def fetch(url,limit=4000000):
    url=public_url(url)
    proxy=urllib.request.ProxyHandler() if os.environ.get('JOB_COMPASS_SYSTEM_PROXY')=='1' else urllib.request.ProxyHandler({})
    opener=urllib.request.build_opener(proxy,Redirect())
    req=urllib.request.Request(url,headers={'User-Agent':'JobCompass/1.0 (personal job research)','Accept':'text/html,application/json,application/xml,*/*'})
    with opener.open(req,timeout=18) as r:
        raw=r.read(limit+1)
        if len(raw)>limit:raise ValueError('网页内容过大')
        return raw.decode(r.headers.get_content_charset() or 'utf-8',errors='replace')
class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.ld=[];self.meta={};self.title='';self.body=[];self.mode='';self.buf='';self.skip=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='script':self.mode='ld' if a.get('type','').lower()=='application/ld+json' else 'skip';self.buf=''
        elif tag=='style':self.skip+=1
        elif tag=='title':self.mode='title';self.buf=''
        elif tag=='meta':self.meta[a.get('property',a.get('name','')).lower()]=a.get('content','')
    def handle_endtag(self,tag):
        if tag=='script':
            if self.mode=='ld':
                try:self.ld.append(json.loads(self.buf))
                except ValueError:pass
            self.mode='';self.buf=''
        elif tag=='style':self.skip=max(0,self.skip-1)
        elif tag=='title':self.title=self.buf;self.mode='';self.buf=''
    def handle_data(self,data):
        if self.mode in ('ld','title'):self.buf+=data
        elif self.mode!='skip' and not self.skip:self.body.append(data)
def ld_jobs(v):
    if isinstance(v,list):
        for x in v:yield from ld_jobs(x)
    if isinstance(v,dict):
        typ=v.get('@type',[])
        if 'JobPosting' in (typ if isinstance(typ,list) else [typ]):yield v
        for k in ('@graph','mainEntity','itemListElement','item'):
            if k in v:yield from ld_jobs(v[k])
def loc_ld(v):
    if isinstance(v,list):return ', '.join(filter(None,[loc_ld(x) for x in v]))
    if isinstance(v,dict):
        a=v.get('address',v)
        if isinstance(a,str):return a
        if isinstance(a,dict):return ', '.join(str(a.get(k,'')) for k in ('addressLocality','addressRegion','addressCountry') if a.get(k))
    return ''
def rank(j):
    return resume_profile.match_job(resume_profile.load_profile(DATA),j)

def prepare(j):
    j=dict(j);j['url']=canonical(j['url']);j['id']=hashlib.sha256(j['url'].encode()).hexdigest()[:20]
    j['title']=clean(j.get('title')) or '待补充岗位名称';j['description']=clean(j.get('description'))[:16000]
    content=j['title']+' '+j['description']
    if not j.get('location'):
        hint=j['title']+' '+urllib.parse.unquote(urllib.parse.urlsplit(j['url']).path)
        j['location']=', '.join(x.title() for x in CITIES if re.search(r'(?<!\w)'+re.escape(x)+r'(?!\w)',hint,re.I))[:180] or '地点待核实'
    j['kind']='论文岗位' if re.search(r'thesis|master.?arbeit|bachelor.?arbeit|abschluss.?arbeit',j['title'],re.I) else '学生工' if STUDENT.search(j['title']) else '类型待核实'
    if not j.get('languages'):j['languages']=' / '.join(label for pat,label in [(r'\benglish|englisch','英语（详见原文）'),(r'\bgerman\b|deutsch','德语（详见原文）')] if re.search(pat,content,re.I)) or '未提取到要求 · 请查看原文'
    if re.search(r'internship|praktik',j['title'],re.I):j['kind']='实习'
    if j['kind']=='类型待核实' and 'full_time' in resume_profile.load_profile(DATA)['job_types']:j['kind']='全职／其他'
    if j.get('opportunity_type')=='topic':j['kind']='论文课题'
    meta=classify(j);j['research_meta']=json.dumps(meta,ensure_ascii=False)
    j['organization_type']=meta['organization_type']
    j['opportunity_type']=j.get('opportunity_type') or 'job'
    j['opportunity_note']=j.get('opportunity_note','')
    j['score'],j['region'],_=rank(j);return j
def upsert(j,c=None):
    own=c is None;c=c or connect()
    try:
        j=dict(j);identity=hashlib.sha256(canonical(j['url']).encode()).hexdigest()[:20]
        old=c.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone()
        if old:
            for key in ('organization_type','opportunity_type','opportunity_note'):
                if not j.get(key):j[key]=old[key]
        j=prepare(j)
        fields=['url','title','company','location','kind','description','languages','source','published','verified_at','deadline','score','region','availability','research_meta','organization_type','opportunity_type','opportunity_note']
        if old:
            u={k:j[k] for k in fields if k in j and j[k] not in ('',None,'地点待核实','类型待核实','待补充岗位名称')}
            if not j.get('verified_at'):u={k:v for k,v in u.items() if k in ('url','source') or not old[k]}
            u['last_seen']=stamp();c.execute('UPDATE jobs SET '+','.join(k+'=?' for k in u)+' WHERE id=?',list(u.values())+[j['id']])
        else:
            cols=['id']+[k for k in fields if k in j]+['first_seen','last_seen'];vals=[j['id']]+[j[k] for k in fields if k in j]+[stamp(),stamp()]
            c.execute('INSERT INTO jobs ('+','.join(cols)+') VALUES ('+','.join('?' for _ in cols)+')',vals)
        if own:c.commit()
        return j['id'],not bool(old)
    finally:
        if own:c.close()
def extract(url):
    url=canonical(url);p=Page();p.feed(fetch(url));jobs=list(ld_jobs(p.ld));j=jobs[0] if jobs else {}
    org=j.get('hiringOrganization',{});company=org.get('name','') if isinstance(org,dict) else str(org)
    title=clean(j.get('title') or p.meta.get('og:title') or p.title)
    desc=clean(j.get('description') or ' '.join(p.body) or p.meta.get('description') or p.meta.get('og:description'))
    if not j and (not discovery.job_type_matches(title+' '+desc,resume_profile.load_profile(DATA)['job_types']) or re.search(r'access denied|just a moment|verify you are human|captcha',title,re.I)):raise ValueError('页面未显示明确岗位内容，可能已下架或需要浏览器验证')
    if not company:
        company=p.meta.get('og:site_name','');parts=re.split(r'\s+[|–—]\s+|\s+bei\s+',title)
        if len(parts)>1 and not company:company=parts[-1]
    loc=loc_ld(j.get('jobLocation',{}))
    host=urllib.parse.urlsplit(url).hostname
    if host=='jobs.fraunhofer.de':
        company=company or 'Fraunhofer-Gesellschaft'
        if not loc:
            match=re.search(r'/job/([^/]+?)-',urllib.parse.unquote(urllib.parse.urlsplit(url).path))
            if match:loc=match.group(1)+', Deutschland'
    if host in ('jobs.sap.com','careers.sap.com'):company=company or 'SAP'
    if j.get('jobLocationType')=='TELECOMMUTE':loc=(loc+' / Remote').strip(' /')
    deadline=str(j.get('validThrough',''))[:10];closed=bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}',deadline) and deadline<today())
    published=str(j.get('datePosted',''))[:10]
    if not published and host=='jobs.fraunhofer.de':
        m=re.search(r'Datum:\s*(\d{2})\.(\d{2})\.(\d{4})',desc)
        if m:published='-'.join([m[3],m[2],m[1]])
    return prepare({'url':url,'title':title,'company':clean(company),'location':loc,'description':desc,'source':urllib.parse.urlsplit(url).hostname,'published':published,'deadline':deadline,'verified_at':stamp(),'availability':'已过截止日期' if closed else '页面可访问 · 招聘状态请核实'})
def relevant(title,description):
    p=resume_profile.load_profile(DATA)
    terms=p['skills']+p['keywords']+p['roles']
    if any(resume_profile.term_matches(t,title) for t in terms):return True
    technical=re.search(r'software|entwickl|developer|engineer|data|daten|research|forschung|informatik|technolog|scientific|wissenschaft',title,re.I)
    generic=bool(re.fullmatch(r'\s*(werkstudent|working student|masterarbeit|master thesis|abschlussarbeit)(\s*\([^)]+\))?\s*',title,re.I))
    return bool((technical or generic) and any(resume_profile.term_matches(t,description) for t in terms))

def bing(q):
    return discovery.search_web(q,fetch,clean,relevant,resume_profile.load_profile(DATA)['job_types'])


def settings():
    with connect() as c:return dict(c.execute('SELECT key,value FROM settings').fetchall())
def refresh():
    if not LOCK.acquire(blocking=False):return False
    rid=None
    try:
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            active=c.execute("SELECT id FROM runs WHERE state='running' AND started>?",((now()-dt.timedelta(minutes=20)).isoformat(),)).fetchone()
            if active:return False
            c.execute("UPDATE runs SET state='interrupted',finished=? WHERE state='running'",(stamp(),))
            rid=c.execute('INSERT INTO runs(started) VALUES (?)',(stamp(),)).lastrowid
        profile=resume_profile.load_profile(DATA)
        if not (profile['skills'] or profile['keywords'] or profile['roles']):raise ValueError('请先上传简历或设置求职方向')
        details=[];added=0;candidates=[]
        sources=[('Arbeitnow · 德国公开招聘',lambda:discovery.arbeitnow(fetch,clean,relevant,profile))] if profile['country']=='Germany' else []
        themes=(profile['keywords'] or profile['skills'] or profile['roles'])[:3]
        if profile['country']=='Germany':
            sources += [('Fraunhofer 官方搜索 · '+term,lambda term=term:discovery.fraunhofer(term,fetch,clean,relevant,profile)) for term in themes]
        searches=list(dict.fromkeys(discovery.queries(profile)+json.loads(settings()['extra_queries'])))[:15]
        sources += [('网页搜索 · '+q,lambda q=q:bing(q)) for q in searches]
        sources += [('研究课题源 · '+spec['company'],lambda spec=spec:research_opportunity(spec)) for spec in research_specs()]
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures={pool.submit(fn):name for name,fn in sources}
            for f in concurrent.futures.as_completed(futures):
                try:
                    rows=f.result();candidates.extend(rows);details.append({'name':futures[f],'ok':True,'count':len(rows)})
                except Exception as e:
                    name=futures[f];details.append({'name':name,'ok':False,'error':str(e)[:200]})
                    if name.startswith('研究课题源 · '):
                        with connect() as c:
                            c.execute("UPDATE jobs SET availability='本次未能核实 · 请查看更新来源' WHERE company=? AND opportunity_type='topic'",(name.removeprefix('研究课题源 · '),))
        unique={canonical(j['url']):j for j in candidates}
        enrich=[j for j in unique.values() if not j.get('verified_at')];enrich.sort(key=lambda j:(-prepare(j)['region'],-prepare(j)['score']))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            fs={pool.submit(extract,j['url']):j for j in enrich[:16]}
            for f in concurrent.futures.as_completed(fs):
                try:
                    j=f.result();j['source']=fs[f]['source'];j['company']=j.get('company') or fs[f].get('company','');unique[canonical(j['url'])]=j
                except Exception:pass
        with connect() as c:
            for j in unique.values():
                if j.get('deadline') and j['deadline']<today():j['availability']='已过截止日期'
                _,new=upsert(j,c);added+=int(new)
            good=sum(d['ok'] for d in details)
            c.execute('UPDATE runs SET finished=?,state=?,added=?,details=? WHERE id=?',(stamp(),'success' if good==len(details) else 'partial' if good else 'failed',added,json.dumps(details,ensure_ascii=False),rid))
        return True
    except Exception as e:
        if rid:
            with connect() as c:c.execute('UPDATE runs SET finished=?,state=?,details=? WHERE id=?',(stamp(),'failed',json.dumps([{'name':'刷新流程','ok':False,'error':str(e)}],ensure_ascii=False),rid))
        return False
    finally:LOCK.release()
def research_specs():
    path=DATA/'research_sources.json'
    return json.loads(path.read_text('utf-8-sig')) if path.exists() else []

def research_opportunity(spec):
    payload=fetch(spec['url'])
    if spec.get('pdf'):
        if not payload.lstrip().startswith('%PDF'):raise ValueError('官方课题文件未返回有效 PDF')
        availability='课题文件可访问 · 名额及有效性待确认'
    else:
        parser=Page();parser.feed(payload);body=clean(' '.join(parser.body))
        if any(term.casefold() not in body.casefold() for term in spec.get('expected',[])):
            raise ValueError('官方页面未找到预期课题，请人工复核名额与内容')
        availability='课题页仍列出方向 · 名额/报酬待确认'
    allowed=('url','title','company','location','organization_type','opportunity_type','opportunity_note','description','languages')
    job={k:spec[k] for k in allowed if k in spec}
    job.update(source='研究课题官方来源',published='',verified_at=stamp(),availability=availability)
    return [job]


def schedule_loop():
    attempted=''
    while True:
        try:
            s=settings()
            with connect() as c:last=c.execute("SELECT started FROM runs WHERE state IN ('success','partial') ORDER BY id DESC LIMIT 1").fetchone()
            due=not last or (last[0][:10]<today() and now().hour>=int(s['daily_hour']))
            if s['auto_update']=='true' and due and attempted!=today():attempted=today();refresh()
        except Exception:pass
        time.sleep(60)
def state():
    with connect() as c:
        jobs=[dict(r) for r in c.execute('SELECT j.*,a.id application_id,a.status,a.applied_on,a.next_followup FROM jobs j LEFT JOIN applications a ON a.job_id=j.id ORDER BY j.region DESC,j.score DESC,j.first_seen DESC')]
        apps=[dict(r) for r in c.execute('SELECT a.*,j.title,j.company,j.location,j.url,j.kind FROM applications a JOIN jobs j ON a.job_id=j.id ORDER BY a.updated_at DESC')]
        for a in apps:a['events']=[dict(r) for r in c.execute('SELECT * FROM events WHERE application_id=? ORDER BY occurred_on DESC,id DESC',(a['id'],))]
        runs=[dict(r) for r in c.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 12')]
    for j in jobs:
        j['tags']=rank(j)[2]
        j['research']=json.loads(j['research_meta']) if j.get('research_meta') else classify(j)
    for r in runs:r['details']=json.loads(r['details'])
    profile=resume_profile.load_profile(DATA)
    install=ROOT/'data'/'scheduler.json';scheduler=json.loads(install.read_text('utf-8-sig')) if install.exists() else {'installed':False}
    return {'jobs':jobs,'applications':apps,'runs':runs,'settings':settings(),'profile':profile,'today':today(),'token':TOKEN,'statuses':STATUSES,'scheduler':scheduler,'research_tracks':TRACKS,'search_links':discovery.external_links(profile),'profile_ready':bool(profile['skills'] or profile['keywords'] or profile['roles'])}
def valid_date(value,optional=False):
    if optional and not value:return ''
    try:return dt.date.fromisoformat(value).isoformat()
    except (ValueError,TypeError):raise ValueError('日期格式应为 YYYY-MM-DD')
def apply_job(p):
    if p.get('job'):
        j=p['job']
        if not str(j.get('title','')).strip() or not str(j.get('company','')).strip():raise ValueError('请补充公司和岗位名称')
        allowed={k:str(j.get(k,'')).strip()[:16000] for k in ('url','title','company','location','description','source','published','verified_at','deadline','availability','languages')}
        jid,_=upsert(allowed)
    else:jid=p.get('job_id')
    day=valid_date(p.get('applied_on') or today())
    with connect() as c:
        old=c.execute('SELECT id FROM applications WHERE job_id=?',(jid,)).fetchone()
        if old:return {'id':old['id'],'duplicate':True}
        if not c.execute('SELECT 1 FROM jobs WHERE id=?',(jid,)).fetchone():raise ValueError('岗位不存在')
        aid=c.execute('INSERT INTO applications(job_id,applied_on,updated_at) VALUES (?,?,?)',(jid,day,stamp())).lastrowid
        c.execute('INSERT INTO events(application_id,occurred_on,status,note,created_at) VALUES (?,?,?,?,?)',(aid,day,'已投递',p.get('note',''),stamp()))
    return {'id':aid,'duplicate':False}
def rejection_note(text):
    """Recognize explicit rejection updates; ignore negated, hypothetical and self-declined offers."""
    for clause in re.split(r'[\n。.!?！？;；]+',str(text or '')):
        if re.search(r'还没|尚未|并未|没有|未被|未收到|不是|不会|避免|担心|如果|是否|可能|会不会|不想|不算|\b(?:not|no|never|waiting|if|worried|haven.t|hasn.t)\b',clause,re.I):continue
        if re.search(r'拒绝.{0,12}(?:offer|录用|邀请|这家公司)|\bI\s+(?:have\s+)?rejected\b|\brejection\s+rate\b',clause,re.I):continue
        if re.search(r'拒绝|拒信|被拒|\brejected\b|\brejection\b|\bAbsage\b',clause,re.I):return True
    return False

def update_application(p):
    status=p.get('status','已投递')
    if status not in STATUSES:raise ValueError('无效申请状态')
    if p.get('status_manual') is not True and rejection_note(p.get('note','')):status='已拒绝'
    day=valid_date(p.get('occurred_on') or today());follow=valid_date(p.get('next_followup',''),True);applied=valid_date(p.get('applied_on') or today())
    if day<applied:raise ValueError('进展日期不能早于投递日期')
    with connect() as c:
        if not c.execute('SELECT 1 FROM applications WHERE id=?',(p['id'],)).fetchone():raise ValueError('申请不存在')
        c.execute('UPDATE applications SET applied_on=?,status=?,next_followup=?,notes=?,updated_at=? WHERE id=?',(applied,status,follow,p.get('notes','')[:16000],stamp(),p['id']))
        c.execute('INSERT INTO events(application_id,occurred_on,status,note,created_at) VALUES (?,?,?,?,?)',(p['id'],day,status,p.get('note','')[:16000],stamp()))
    return {'ok':True,'status':status}
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,value,status=200,mime='application/json; charset=utf-8'):
        data=(json.dumps(value,ensure_ascii=False) if mime.startswith('application/json') else value).encode('utf-8') if isinstance(value,(dict,list,str)) else value
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers();self.wfile.write(data)
    def safe_host(self):return self.headers.get('Host') in (f'127.0.0.1:{PORT}',f'localhost:{PORT}')
    def do_GET(self):
        if not self.safe_host():return self.send({'error':'Host rejected'},403)
        path=urllib.parse.urlsplit(self.path).path
        if path=='/api/state':return self.send(state())
        if path=='/api/health':return self.send({'app':'job-compass-open-source','ok':True})
        if path=='/api/export':
            s=state();s.pop('token',None);return self.send(s)
        files={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
        if path in files:
            name,mime=files[path];return self.send((ROOT/'static'/name).read_bytes(),mime=mime)
        self.send({'error':'Not found'},404)
    def do_POST(self):
        if not self.safe_host() or self.headers.get('X-Job-Token')!=TOKEN:return self.send({'error':'请刷新页面后重试'},403)
        if self.headers.get('Origin') not in (None,f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}'):return self.send({'error':'Origin rejected'},403)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=8*1024*1024:raise ValueError('请求内容过大或为空')
            p=json.loads(self.rfile.read(length));path=urllib.parse.urlsplit(self.path).path
            if path=='/api/resume':return self.send(resume_profile.parse_pdf(p.get('pdf_base64')))
            if path=='/api/profile':
                profile=resume_profile.save_profile(DATA,p)
                with connect() as c:
                    for row in c.execute('SELECT * FROM jobs').fetchall():
                        score,region,_=resume_profile.match_job(profile,dict(row));c.execute('UPDATE jobs SET score=?,region=? WHERE id=?',(score,region,row['id']))
                return self.send({'profile':profile})
            if path=='/api/refresh':
                profile=resume_profile.load_profile(DATA)
                if not (profile['skills'] or profile['keywords'] or profile['roles']):raise ValueError('请先上传简历或设置求职方向')
                threading.Thread(target=refresh,daemon=True).start();return self.send({'ok':True,'queued':True},202)
            if path=='/api/extract':
                url=canonical(p['url'])
                try:return self.send({'job':extract(url),'warning':''})
                except Exception as e:return self.send({'job':{'url':url,'title':'','company':'','location':'','description':''},'warning':'网页未能自动读取，请补充岗位和公司后保存。原因：'+str(e)[:180]})
            if path=='/api/apply':return self.send(apply_job(p))
            if path=='/api/application':return self.send(update_application(p))
            if path=='/api/job':
                with connect() as c:c.execute('UPDATE jobs SET saved=COALESCE(?,saved),hidden=COALESCE(?,hidden) WHERE id=?',(p.get('saved'),p.get('hidden'),p['id']))
                return self.send({'ok':True})
            if path=='/api/settings':
                hour=int(p.get('daily_hour',9));qs=p.get('extra_queries',[])
                if hour not in range(24):raise ValueError('时间应为 0–23 点')
                if not isinstance(qs,list) or len(qs)>12 or any(not isinstance(q,str) or len(q)>250 for q in qs):raise ValueError('最多 12 条搜索词，每条不超过 250 字')
                with connect() as c:
                    for k,v in {'daily_hour':str(hour),'auto_update':'true' if p.get('auto_update') else 'false','extra_queries':json.dumps(qs,ensure_ascii=False)}.items():c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(k,v))
                return self.send({'ok':True})
            self.send({'error':'Not found'},404)
        except (ValueError,KeyError,TypeError) as e:self.send({'error':str(e)},400)
        except Exception as e:self.send({'error':'操作未保存：'+str(e)[:200]},500)
def main():
    p=argparse.ArgumentParser();p.add_argument('--refresh-only',action='store_true');p.add_argument('--no-scheduler',action='store_true');args=p.parse_args();init()
    if args.refresh_only:refresh();return
    try:server=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    except OSError as error:
        message=f'{stamp()} Failed to bind 127.0.0.1:{PORT}: {error!r}. '
        message+=('Windows has denied this port; check system-reserved port ranges.' if getattr(error,'winerror',None)==10013 else 'Check whether another process is using this port.')
        with (DATA/'service-error.log').open('a',encoding='utf-8') as log:log.write(message+'\n')
        print(message);return
    if not args.no_scheduler:threading.Thread(target=schedule_loop,daemon=True).start()
    print(f'Job Compass: http://127.0.0.1:{PORT}',flush=True);server.serve_forever()
if __name__=='__main__':main()
