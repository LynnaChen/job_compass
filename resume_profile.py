"""Local PDF-to-search profile extraction. Raw PDF/text is never persisted."""
import base64, binascii, datetime, io, json, os, re
from pathlib import Path
from functools import lru_cache
from uuid import uuid4

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PAGES = 15
SKILLS = {
 'Python': r'\bpython\b', 'SQL': r'\bsql\b', 'JavaScript': r'\bjavascript\b',
 'TypeScript': r'\btypescript\b', 'Java': r'\bjava\b', 'C++': r'\bc\+\+',
 'Bash': r'\bbash\b', 'R': r'\br programming\b|\br language\b',
 'PyTorch': r'\bpytorch\b', 'TensorFlow': r'\btensorflow\b', 'scikit-learn': r'scikit.learn',
 'LLM': r'\bllms?\b|large language model|大语言模型|大模型',
 'NLP': r'\bnlp\b|natural language processing|computational linguistics|自然语言处理',
 'RAG': r'\brag\b|retrieval.augmented', 'LangGraph': r'\blanggraph\b',
 'LangChain': r'\blangchain\b', 'LlamaIndex': r'\bllamaindex\b',
 'AI Agent': r'agentic|ai agents?|agent harness|智能体',
 'Reinforcement Learning': r'reinforcement learning|强化学习|\bgrpo\b|\brlhf\b',
 'Fine-tuning': r'fine.tun|微调', 'Machine Learning': r'machine learning|机器学习|maschinelles lernen',
 'Deep Learning': r'deep learning|深度学习', 'Computer Vision': r'computer vision|计算机视觉',
 'vLLM': r'\bvllm\b', 'GPU': r'\bgpu\b|\bgpus\b|\bcuda\b',
 'Docker': r'\bdocker\b', 'Kubernetes': r'\bkubernetes\b|\bk8s\b',
 'Linux': r'\blinux\b', 'Git': r'\bgit\b', 'PostgreSQL': r'\bpostgres(?:ql)?\b',
 'Pandas': r'\bpandas\b', 'NumPy': r'\bnumpy\b', 'Spark': r'\bspark\b',
 'Statistics': r'statistic|统计', 'Excel': r'\bexcel\b', 'Power BI': r'\bpower ?bi\b',
 'Tableau': r'\btableau\b', 'React': r'\breact\b', 'Node.js': r'\bnode\.?js\b',
 'Accounting': r'accounting|buchhaltung|会计', 'Financial Analysis': r'financial analysis|财务分析',
 'Marketing': r'marketing|市场营销', 'SEO': r'\bseo\b', 'UX': r'\bux\b|user experience',
 'CAD': r'\bcad\b|solidworks|catia', 'MATLAB': r'\bmatlab\b',
 'Robotics': r'robotics|机器人|robotik', 'Project Management': r'project management|项目管理',
}
DOMAINS = [
 ('AI / NLP', {'LLM','NLP','RAG','PyTorch','TensorFlow','AI Agent','Reinforcement Learning','Fine-tuning'}, ['AI Engineer','NLP','Machine Learning']),
 ('Data Science', {'Pandas','Statistics','Power BI','Tableau','Spark','NumPy'}, ['Data Science','Data Analyst']),
 ('Software Engineering', {'Python','JavaScript','TypeScript','Java','C++','React','Node.js'}, ['Software Engineering']),
 ('Finance', {'Accounting','Financial Analysis'}, ['Finance','Accounting']),
 ('Marketing / UX', {'Marketing','SEO','UX'}, ['Marketing','UX Research']),
 ('Engineering', {'CAD','MATLAB','Robotics'}, ['Engineering','Robotics']),
]
COUNTRIES = {'Germany','Austria','Switzerland'}
JOB_TYPES = {'working_student','thesis','internship','full_time'}

def empty_profile():
 return {'skills':[], 'keywords':[], 'roles':[], 'country':'Germany', 'preferred_cities':[],
         'job_types':['working_student','thesis'], 'summary':'尚未设置求职方向', 'updated_at':''}

def safe_terms(values, limit=30):
 if not isinstance(values,list): raise ValueError('关键词应为列表')
 result=[]
 for value in values:
  if not isinstance(value,str): raise ValueError('关键词应为文本')
  term=re.sub(r'\s+',' ',value).strip()
  if not term:continue
  if len(term)>60:raise ValueError('每条关键词最多 60 个字符')
  if re.search(r'@|https?://|\d{7,}|[\r\n<>]',term):raise ValueError('搜索方向中请勿填写邮箱、网址、电话号码或简历全文')
  if term.casefold() not in {t.casefold() for t in result}: result.append(term)
 if len(result)>limit:raise ValueError('关键词数量过多')
 return result

def validate_profile(value):
 if not isinstance(value,dict):raise ValueError('无效的求职设置')
 p=empty_profile()
 for key,limit in (('skills',30),('keywords',30),('roles',6),('preferred_cities',8)):
  p[key]=safe_terms(value.get(key,[]),limit)
 p['country']=value.get('country','Germany')
 if p['country'] not in COUNTRIES:raise ValueError('目前支持德国、奥地利、瑞士搜索范围')
 types=value.get('job_types',['working_student','thesis'])
 if not isinstance(types,list) or not types or any(t not in JOB_TYPES for t in types):raise ValueError('请至少选择一种有效岗位类型')
 p['job_types']=list(dict.fromkeys(types))
 if not (p['roles'] or p['keywords'] or p['skills']):raise ValueError('请填写至少一个求职方向或关键词')
 p['summary']=' / '.join(p['roles'][:3]) or ' / '.join((p['keywords'] or p['skills'])[:4])
 p['updated_at']=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
 return p

def profile_from_text(text):
 skills=[label for label,pattern in SKILLS.items() if re.search(pattern,text,re.I)]
 ranked=sorted([(len(set(skills)&signals),name,roles) for name,signals,roles in DOMAINS],reverse=True)
 roles=ranked[0][2] if ranked and ranked[0][0]>0 else []
 p=empty_profile();p.update(skills=skills[:30],keywords=skills[:12],roles=roles)
 p['summary']=' / '.join(roles) or '未识别出明确方向，请手动补充'
 return p

def parse_pdf(encoded):
 if not isinstance(encoded,str) or len(encoded)>MAX_PDF_BYTES*4//3+8:raise ValueError('PDF 最大 5 MB')
 try:raw=base64.b64decode(encoded,validate=True)
 except (binascii.Error,ValueError):raise ValueError('无效的 PDF 数据') from None
 if not raw.startswith(b'%PDF-') or len(raw)>MAX_PDF_BYTES:raise ValueError('请上传有效的 PDF，最大 5 MB')
 try:
  from pypdf import PdfReader
 except ImportError:raise ValueError('缺少 PDF 解析依赖，请安装 requirements.txt') from None
 try:
  reader=PdfReader(io.BytesIO(raw))
  if reader.is_encrypted:raise ValueError('请先解除 PDF 密码保护')
  if not 1<=len(reader.pages)<=MAX_PAGES:raise ValueError('请上传 1 至 15 页的简历 PDF')
  text='\n'.join((page.extract_text() or '') for page in reader.pages)
 except ValueError:raise
 except Exception:raise ValueError('无法读取该 PDF，请导出带可选择文字的 PDF 后重试') from None
 if len(text.strip())<40:raise ValueError('未读到足够文字。扫描版 PDF 暂不支持，请上传可选择文字的简历或手动填写方向')
 if len(text)>120000:raise ValueError('简历文字过多，请上传精简版 PDF')
 return {'profile':profile_from_text(text),'notice':'已在本机提取技能；原始 PDF、全文和联系方式均未保存。请核对求职方向后保存。'}

@lru_cache(maxsize=8)
def _read_profile(path,mtime):
 try:return json.loads(Path(path).read_text('utf-8'))
 except (OSError,ValueError):return empty_profile()

def load_profile(data):
 p=Path(data)/'profile.json'
 return _read_profile(str(p),p.stat().st_mtime_ns) if p.exists() else empty_profile()

def save_profile(data,value):
 profile=validate_profile(value);root=Path(data);root.mkdir(parents=True,exist_ok=True)
 tmp=root/('.profile-'+uuid4().hex+'.tmp')
 try:
  tmp.write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
  os.replace(tmp,root/'profile.json')
 finally:tmp.unlink(missing_ok=True)
 return profile

def term_matches(term,text):
 return bool(re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',text,re.I))

def match_job(profile,job):
 body=' '.join(str(job.get(k,'')) for k in ('title','description','location'))
 terms=list(dict.fromkeys(profile.get('skills',[])+profile.get('keywords',[])+profile.get('roles',[])))
 matches=[t for t in terms if term_matches(t,body)]
 cities=profile.get('preferred_cities',[])
 near=any(term_matches(city,job.get('location','')) for city in cities)
 score=0 if not matches else min(99,35+int(55*len(matches)/max(1,min(len(terms),8)))+10*any(term_matches(t,job.get('title','')) for t in terms))
 return score,int(near),matches[:8]
