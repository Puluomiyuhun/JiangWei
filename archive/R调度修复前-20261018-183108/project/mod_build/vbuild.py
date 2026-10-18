import sys,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/eex'))
from eex_strategy_refs import decode
from dump_e5_skills import read_section
from pathlib import Path
B=Path(__file__).resolve().parent/'build'
d=B.joinpath('Data.e5').read_bytes();t0=read_section(d,0)
known={t0[i*32:i*32+12].split(b'\0')[0].decode('gbk','replace') for i in range(len(t0)//32)}
for f in sorted(B.joinpath('RS').glob('R_*.EEX')):
 x=decode(f.read_bytes());miss=set();over=0;mx=0;boxes=0;chars=0;maps=0;ev=0;bad=[]
 ins=x['instructions']
 for k,i in enumerate(ins):
  if i['opcode']==0x14:
   v=i['args'][0]['value'];boxes+=1
   for m in re.findall(r'&([^\n]+)\n',v):
    if m not in known:miss.add(m)
   body=v.split('\n',1)[1] if v.startswith('&') else v
   ls=body.split('\n');chars+=len(body.replace('\n',''))
   if '\ufffd' in v:bad.append(v[:40])
   if len(ls)>3:over+=1
   mx=max(mx,*(len(l.encode('gbk','replace')) for l in ls))
  elif i['opcode']==0x2c:maps+=1
  elif i['opcode']==0x18:ev+=1
 print(f.name,x['complete'],'boxes',boxes,'chars',chars,'events',ev,'maptexts',maps,'>3lines',over,'maxbytes',mx,'unknown',miss,'bad',bad)

