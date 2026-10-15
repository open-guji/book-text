# 整理本卷 JSON → text/*.md 自动配对（文本总管 09-30 干跑：1,735 卷配上 1,635，余 100 卷在 14 部）。用法：在 book-text 根目录运行 python3 <本脚本> [输出json]
import glob,os,json,re,sys
CN='〇一二三四五六七八九'
def cn(n):
    if n>=100: return None
    if n<10: return '一二三四五六七八九'[n-1] if n else '〇'
    t,o=divmod(n,10); s=('' if t==1 else CN[t])+'十'+(CN[o] if o else '')
    return s if n<100 else None
def norm(s): return re.sub(r'[\s·_\-－—・]','',s)
tot=ok=0; bad=[]; maps={}
for d in sorted(glob.glob('Work/*/*/*/*/collated_edition')):
    ij=json.load(open(d+'/index.json')); jf=ij.get('juan_files') or sorted(os.path.relpath(f,d) for f in glob.glob(d+'/juan/*.json'))
    texts=[os.path.relpath(f,d) for f in glob.glob(d+'/text/*.md')]
    if not texts: continue
    stems={norm(os.path.splitext(os.path.basename(t))[0]):t for t in texts}
    m={}
    for i,j in enumerate(jf,1):
        try: jj=json.load(open(os.path.join(d,j)))
        except Exception: continue
        cands=[jj.get('title',''),jj.get('source_juan','')]
        n=int(re.search(r'(\d+)',os.path.basename(j)).group(1)) if re.search(r'\d+',os.path.basename(j)) else i
        cands+=[f'juan_{n:02d}',f'juan_{n:03d}',f'juan{n}',f'卷{n:02d}',f'卷{n:03d}',f'卷{n}']
        if cn(n): cands+=['卷'+cn(n),'卷之'+cn(n)]
        hit=None
        for c in cands:
            c=norm(c)
            if c and c in stems: hit=stems[c]; break
        if not hit:
            for c in cands[:2]:
                c=norm(c)
                if c:
                    hs=[t for s,t in stems.items() if s.endswith(c) or c.endswith(s) and len(s)>1]
                    if len(hs)==1: hit=hs[0]; break
        tot+=1
        if hit: ok+=1; m[j]=hit
        else: bad.append((d,j,cands[:2]))
    maps[d]=m
print('juan',tot,'matched',ok)
for b in bad[:15]: print(b)
print('works with misses',len(set(b[0] for b in bad)))
if len(sys.argv)>1: json.dump(maps,open(sys.argv[1],'w'),ensure_ascii=False)
