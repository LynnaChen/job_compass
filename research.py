"""Evidence-based research tracks. No external services or model API required."""
import re
TRACKS={'agent_evolution':'Agent 自进化','post_training':'后训练与对齐','model_training':'模型训练与持续学习'}
MODEL=re.compile(r'\b(llms?|slms?|language models?|foundation models?|neural|deep learning|nlp|multimodal|transformers?|agentic|agents?)\b|sprachmodell|ki-agent|agenten|语言模型|大模型',re.I)
RULES={
 'agent_evolution':[
  (r'self[ -](?:evolv\w*|improv\w*)','自进化 / 自我改进'),
  (r'agent\s+harness','Agent harness'),
  (r'selbst[ -]?(?:lernend\w*|verbessernd\w*|optimier\w*)','自学习 / 自优化'),
  (r'skill[ -](?:learning|acquisition|discovery|evolution)|learn(?:ing)?\s+(?:new\s+)?skills','skill 学习'),
  (r'(?:agent\w*[ -](?:memory|memories)|(?:memory|memories)[ -](?:in|for|of)[ -]agents?)','Agent 记忆'),
  (r'tool[ -](?:learning|discovery)|continual(?:ly)?\s+learn\w*.{0,50}agent','工具学习 / 持续学习'),
 ],
 'post_training':[
  (r'post[ -]?training','后训练'),
  (r'fine[ -]?tun(?:e|ed|es|ing)|feintun\w*|feinabstimm\w*','模型微调'),
  (r'\b(?:sft|dpo|rlhf|rlaif|grpo|rlvr|ppo)\b','对齐 / 强化学习训练'),
  (r'reinforcement learning|preference optimi[sz]ation|distill(?:ation)?','强化学习 / 偏好优化 / 蒸馏'),
 ],
 'model_training':[
  (r'pre[ -]?train\w*|continued pre[ -]?training','预训练'),
  (r'(?:model|llm|multimodal|distributed)[ -]training|train(?:ing)?\s+(?:(?:small|large|foundation|language|neural|multimodal)\s+){0,3}models','模型训练'),
  (r'continual learning|continuous learning|lifelong learning|持续学习','持续学习'),
  (r'trainieren.{0,60}(?:modell|llm)|training.{0,35}(?:sprachmodell|neural network)','训练模型'),
 ],
}
def org_type(job):
 if job.get('organization_type'):return job['organization_type']
 company=job.get('company','');s=company+' '+job.get('url','')
 if re.search(r'fraunhofer|dfki|max.planck|helmholtz|leibniz',s,re.I):return '研究所'
 if re.search(r'universit|hochschule|tresp|\.tum\.de|\.uni-|uni-a\.de',s,re.I):return '高校'
 return '企业' if company and company not in ('公司待核实','待补充公司') else '机构待核实'
def classify(job):
 title=job.get('title','');desc=job.get('description','');body=title+'. '+desc
 sentences=re.split(r'(?<=[.!?。；;])\s+|\n+',body)
 evidence=[];tracks=[]
 for key,rules in RULES.items():
  for pattern,label in rules:
   for sentence in sentences:
    match=re.search(pattern,sentence,re.I)
    if not match:continue
    # DPO in finance, staff training and generic RAG integration are not model research.
    if not MODEL.search(sentence+' '+title):continue
    if re.search(r'(?:training courses?|employee training|staff training|days payables|data protection officer)',sentence,re.I) and not MODEL.search(title):continue
    start=max(0,match.start()-80);end=min(len(sentence),match.end()+130)
    quote=sentence[start:end].strip()
    if start:quote='…'+quote
    if end<len(sentence):quote+='…'
    evidence.append({'track':key,'label':label,'excerpt':quote[:240],'in_title':bool(re.search(pattern,title,re.I))})
    break
   if evidence and evidence[-1]['track']==key:break
  if evidence and evidence[-1]['track']==key:tracks.append(key)
 research=bool(re.search(r'literature|novel|ablation|hypothes|scientific|wissenschaft|research (?:methods|thesis|directions)|experiments?|benchmark|研究方法|对照实验',body,re.I))
 integration=bool(re.search(r'business process|integrat\w*|workflow|deployment|production|systems engineering|业务|集成|部署',body,re.I))
 focus='研究与应用并重' if research and integration else '偏研究' if research else '训练工程 / 研究程度待确认' if tracks else '需核实'
 confidence='标题明确' if any(e['in_title'] for e in evidence) else '职责关键词线索'
 return {'tracks':tracks,'labels':[TRACKS[t] for t in tracks],'evidence':evidence,'focus':focus,'confidence':confidence,'organization_type':org_type(job),'note':job.get('opportunity_note','')}


