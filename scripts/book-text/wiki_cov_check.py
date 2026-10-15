import json,glob,re,sys,os,collections
from opencc import OpenCC
t2s=OpenCC('t2s')
R='/home/user/book-text'
CJK=re.compile(r'[㐀-鿿\U00020000-\U0002fa1f]')
def vers(w):
    d=glob.glob(f'{R}/Work/*/*/*/{w}')[0]; m=json.load(open(f'{d}/manifest.json',encoding='utf-8'))
    return d,m
def chap(d,key):
    idx=json.load(open(f'{d}/{key}/index.json',encoding='utf-8')); out=[]
    for c in idx['chapters']:
        f=f"{d}/{key}/{c['file']}" if c['file'].endswith('.md') else f"{d}/{key}/{c['file']}.md"
        try: t=open(f,encoding='utf-8').read()
        except Exception: t=''
        t=re.sub(r'<[^>]*>','',t); t=''.join(CJK.findall(t)); out.append((c['n'],c.get('title',''),t))
    return out
def grams(s,n=6): return {s[i:i+n] for i in range(len(s)-n+1)}
def run(w,wkey,ckey):
    d,m=vers(w); W=chap(d,wkey); C=chap(d,ckey)
    wt=''.join(x[2] for x in W); ws=grams(wt); ws2=grams(t2s.convert(wt))
    res=[]
    tot=sum(len(x[2]) for x in C); miss=0; miss2=0
    for n,ti,t in C:
        g=grams(t)
        if not g: res.append((n,ti,len(t),None,None)); continue
        cov=sum(1 for x in g if x in ws)/len(g); g2=grams(t2s.convert(t)); cov2=sum(1 for x in g2 if x in ws2)/max(1,len(g2))
        res.append((n,ti,len(t),round(cov,2),round(cov2,2)))
    return dict(w=w,wch=len(W),wlen=len(wt),cch=len(C),clen=tot,res=res)
if __name__=='__main__':
    w,wk,ck=sys.argv[1:4]; r=run(w,wk,ck)
    print(w,'wiki',r['wch'],'章',r['wlen'],'字 | 对照',r['cch'],'章',r['clen'],'字')
    low=[x for x in r['res'] if x[3] is not None and x[4]<0.3]
    print(' 对照章中 t2s 后覆盖<.3 的章数',len(low),'字数占比',round(sum(x[2] for x in low)/max(1,r['clen']),3),'| 原样<.3',sum(1 for x in r['res'] if x[3] is not None and x[3]<0.3))
    print(' 低覆盖章:',[(x[1][:10],x[2],x[3],x[4]) for x in low][:12])
