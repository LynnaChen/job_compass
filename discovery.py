"""Public-source discovery. Search only user-approved skill/role terms, never CV text."""
import datetime as dt
import json,re,urllib.parse,xml.etree.ElementTree as ET
from html.parser import HTMLParser

TYPE_PATTERNS={
 'working_student':r'werkstudent|werkstudier|working.student|student.assistant|studentische|hilfskraft|hiwi',
 'thesis':r'\bthesis\b|master.?arbeit|bachelor.?arbeit|abschluss.?arbeit',
 'internship':r'\bintern(?:ship)?\b|praktik',
}
TYPE_LABELS={'working_student':'working student','thesis':'master thesis','internship':'internship','full_time':'jobs'}

def job_type_matches(title,selected):
 if 'full_time' in selected and not any(re.search(p,title,re.I) for p in TYPE_PATTERNS.values()):return True
 return any(re.search(TYPE_PATTERNS[t],title,re.I) for t in selected if t in TYPE_PATTERNS)

def queries(profile):
 themes=profile.get('roles',[])[:3] or profile.get('keywords',[])[:3] or profile.get('skills',[])[:3]
 country=profile.get('country','Germany')
 return list(dict.fromkeys(f'{TYPE_LABELS[t]} {theme} {country}' for theme in themes for t in profile.get('job_types',['working_student','thesis'])))[:9]

def external_links(profile):
 return [{'query':q,'url':'https://www.google.com/search?q='+urllib.parse.quote(q)} for q in queries(profile)]

def search_web(query,fetch,clean,relevant,selected):
 # RSS responses can be syntactically valid but completely empty. Report this as unavailable.
 xml=fetch('https://www.bing.com/search?format=rss&setlang=de&cc=de&q='+urllib.parse.quote(query))
 try:root=ET.fromstring(xml)
 except ET.ParseError:raise ValueError('搜索源没有返回可读取的结果；可使用页面上的外部搜索链接') from None
 items=root.findall('.//item')
 if not items:raise ValueError('搜索源返回空结果，不能确认已完整搜索；可使用外部搜索链接')
 rows=[]
 for item in items:
  title=clean(item.findtext('title'));desc=clean(item.findtext('description'));url=item.findtext('link','')
  if not job_type_matches(title,selected) or not relevant(title,desc):continue
  if any(t in urllib.parse.urlsplit(url).path.lower() for t in ('/jobs/search','/stellenangebote/','/search/')):continue
  rows.append({'url':url,'title':title,'description':desc,'source':'Bing 网页发现','published':''})
 return rows

def arbeitnow(fetch,clean,relevant,profile):
 if profile.get('country','Germany')!='Germany':return []
 rows=[]
 for page in range(1,3):
  data=json.loads(fetch('https://www.arbeitnow.com/api/job-board-api?page='+str(page),limit=12000000))
  for j in data.get('data',[]):
   title=j.get('title','');description=clean(j.get('description',''))
   if not job_type_matches(title,profile.get('job_types',[])) or not relevant(title,description):continue
   created=j.get('created_at');published=dt.datetime.fromtimestamp(created,dt.timezone.utc).date().isoformat() if isinstance(created,(int,float)) else ''
   rows.append({'url':j['url'],'title':title,'company':j.get('company_name',''),'location':j.get('location',''),'description':description,'published':published,'source':'Arbeitnow 公开接口','availability':'来源当前列出 · 请核实招聘方'})
 return rows

def fraunhofer(query,fetch,clean,relevant,profile):
 if profile.get('country','Germany')!='Germany':return []
 base='https://jobs.fraunhofer.de';source=fetch(base+'/search/?q='+urllib.parse.quote(query)+'&locale=de_DE')
 import html
 rows={}
 for href,label in re.findall(r'<a\b[^>]*href=["\x27]([^"\x27]+)["\x27][^>]*>(.*?)</a>',source,re.S|re.I):
  title=clean(label)
  if not href.startswith('/job/') or not job_type_matches(title,profile.get('job_types',[])) or not relevant(title,''):continue
  url=base+html.unescape(href)
  rows[url]={'url':url,'title':title,'company':'Fraunhofer-Gesellschaft','location':urllib.parse.unquote(href).split('/job/')[-1].split('-')[0]+', Deutschland','source':'Fraunhofer 官方职位搜索','description':'','availability':'官方列表发现 · 详情待核实'}
 return list(rows.values())
