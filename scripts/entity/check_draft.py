# 草稿（T 小总管 10-09 手写的一次性核对脚本，路径写死在 /home/user/scratch/chk/）。
# 派给 Haiku 整理成可复用脚本 scripts/t_entity_check.py 的参照，见台账。不要直接用。
import json,re,sys,collections
try:
    import jsonschema
except ImportError:
    jsonschema=None
S=json.load(open('/home/user/guji-format/schemas/guji_entity_v0.2.schema.json'))
issues=collections.Counter();ex={}
def bad(k,m):
    issues[k]+=1; ex.setdefault(k,m)
for v in('002','003'):
    d=json.load(open(f'/home/user/scratch/chk/{v}.entity.json'))
    c=json.load(open(f'/home/user/scratch/chk/{v}.char.json'))
    seq=[x for p in c['pages'] for col in p['columns'] for x in col['cells']]
    pos={x['a']:i for i,x in enumerate(seq)}
    if d['$schema']!='https://open-guji.org/schema/entity/v0.2.json': bad('schema_url',d['$schema'])
    if jsonschema:
        for err in jsonschema.Draft202012Validator(S).iter_errors(d): bad('jsonschema:'+err.message[:60],str(list(err.path)[:3]))
    es=d['entities'];ids=[e['id'] for e in es]
    if len(ids)!=len(set(ids)): bad('dup_id',v)
    prev=-1;groups=collections.defaultdict(list)
    for e in sorted(es,key=lambda e:e['span']['start_offset']):
        s,t=e['span']['start_offset'],e['span']['end_offset']
        if s<prev: bad('overlap',e['id'])
        prev=max(prev,t)
    for e in es:
        s,t=e['span']['start_offset'],e['span']['end_offset']
        if pos.get(e['anchor']['start'])!=s or pos.get(e['anchor']['end'])!=t-1: bad('span_anchor',e['id'])
        if ''.join(x['c'] for x in seq[s:t])!=e['text']: bad('text',e['id'])
        tg=e['target'];st=tg['status']
        if st=='matched':
            if not all(k in tg for k in('entity_id','canonical_name','href')) or 'candidates' in tg: bad('matched_fields',e['id'])
            elif tg['href'].rsplit('/',1)[1]!=tg['entity_id']: bad('href_tail',e['id'])
        elif st=='ambiguous':
            if len(tg.get('candidates',[]))<2: bad('ambiguous_lt2',e['id']+' '+e['text'])
            if 'entity_id' in tg or 'href' in tg: bad('ambiguous_extra',e['id'])
        elif st=='new_candidate':
            if any(k in tg for k in('entity_id','href','candidates')): bad('nc_extra',e['id'])
        for k in tg:
            if k in('coarse','reclass','route_to','entity_type'): bad('legacy_'+k,e['id'])
        if e['type'] not in('work','people','place','office','dynasty','reign','other'): bad('type',e['type'])
        if 'group' in e: groups[e['group']['id']].append(e)
    for gid,g in groups.items():
        g.sort(key=lambda e:e['span']['start_offset'])
        if len(g)<2: bad('group_lt2',gid)
        if gid!='g'+g[0]['id']: bad('group_id',gid)
        if ''.join(e['text'] for e in g)!=g[0]['group']['text']: bad('group_text',gid)
        for a,b in zip(g,g[1:]):
            if a['span']['end_offset']!=b['span']['start_offset']: bad('group_adjacent',gid)
        if any(e['group']!=g[0]['group'] for e in g): bad('group_mixed',gid)
    # 书名号
    pj=json.load(open(f'/home/user/scratch/chk/{v}.punct.json'))
    pl=pj.get('punctuations',[])
    opens={p['anchor'] for p in pl if p.get('mark')=='《'};closes={p['anchor'] for p in pl if p.get('mark')=='》'}
    for e in es:
        if e['type']=='work':
            if e['anchor']['start'] not in opens: bad('work_open_missing',e['id']+' '+e['text'])
            if e['anchor']['end'] not in closes: bad('work_close_missing',e['id']+' '+e['text'])
    ix=json.load(open('/home/user/scratch/chk/index.json'))
    ch=[x for x in ix['chapters'] if x['file']==v][0]
    if ch['entity_version']!=d['version']: bad('version_mirror',v)
    old=sum(1 for e in es if e['target'].get('status')=='matched')
print(dict(issues)); print(ex)
