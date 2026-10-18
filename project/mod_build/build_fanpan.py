"""翻盘线（钟会线）剧本构建：按正本全部回目 -> RS/R_nn.EEX + Data.e5(通用说话人)。
只输出到 mod_build/build，部署另行备份后进行。仅静态校验，不启动游戏。"""
from pathlib import Path
import sys,struct,re,json,hashlib,heapq
HERE=Path(__file__).resolve().parent
import os
REPO=HERE.parents[1]
GAME=Path(os.environ.get('JIANGWEI_GAME_DIR', str(REPO/'resources/build-inputs/game')))
ORIGINAL_RS=Path(os.environ.get('JIANGWEI_ORIGINAL_RS_DIR', str(REPO/'resources/build-inputs/original-RS')))
USE_AUDIO_MANIFEST='JIANGWEI_GAME_DIR' not in os.environ
AUDIO_FILES=set(json.loads((GAME/'audio-files.json').read_text(encoding='utf-8'))['files']) if USE_AUDIO_MANIFEST else set()
sys.path.insert(0,str(REPO/'tools/eex'))
# 避免只改分回稿却把旧整本编译出去。
source_text=(HERE.parent/'姜维传·钟会线·长篇.md').read_text(encoding='utf-8')
for chapter_file in sorted((HERE/'draft').glob('ch*.md')):
 assert source_text.count(chapter_file.read_text(encoding='utf-8').strip())==1,('分回稿与整本不同步',chapter_file.name)
from dump_e5_skills import read_section
from eex_strategy_refs import decode,SCHEMA
OUT=HERE/'build';(OUT/'RS').mkdir(parents=True,exist_ok=True)
F=65535
def w(x):return struct.pack('<H',x)
def ins(op,*args):
 tags=SCHEMA[f'{op:02X}']['args']
 assert len(args)==len(tags),(hex(op),len(args),tags)
 b=w(op)
 for t,v in zip(tags,args):
  if t!=1:b+=w(t)
  b+=str(v).encode('gbk')+b'\0' if t==5 else struct.pack('<I' if t==4 else '<H',v)
 return b
def var(n,v):return ins(0x77,2,n,2,0,v)
def flag(n,v=1):return ins(0x0b,n,v)
def test(yes=(),no=()):return w(5)+w(0x35)+w(len(yes))+b''.join(w(n) for n in yes)+w(0x35)+w(len(no))+b''.join(w(n) for n in no)
def rec(cond,body):
 body+=w(0);p=cond+w(0)+w(len(body))+body;return w(len(p))+p
def block(records):return w(len(records))+b''.join(records)
def write_eex(name,blocks):
 offset=10+4*len(blocks);head=b'EEX\0\1\2'+w(0)+w(0)
 for b in blocks:head+=struct.pack('<I',offset);offset+=len(b)
 blob=head+b''.join(blocks);d=decode(blob);assert d['complete'],(name,d['errors'])
 (OUT/'RS'/name).write_bytes(blob);return d
def sections(blob):
 count=(int.from_bytes(blob[0x118:0x11c],'big')-0x110)//12
 return [read_section(blob,i) for i in range(count)]
def write_e5(path,blocks):
 offset=0x110+12*len(blocks);head=b'Ls12'+bytes(12)+bytes(range(256));body=b''
 for b in blocks:head+=struct.pack('>III',len(b),len(b),offset);body+=b;offset+=len(b)
 path.write_bytes(head+body)
from dialogue_layout import paginate

def say(name,text):
 """先按完整句意分框，再排每框的三行；心声每框保留外括号。"""
 return b''.join(ins(0x14,('&'+name+'\n' if name else '')+'\n'.join(p.lines))
                 for p in paginate(text,19 if name else 18))

# ---------- Data.e5：为不在名册里的通用说话人启用空槽 ----------
data=bytearray((GAME/'Data.e5').read_bytes());tables=[bytearray(x) for x in sections(bytes(data))]
names={}
for id in range(len(tables[0])//32):
 n=tables[0][id*32:id*32+12].split(b'\0')[0].decode('gbk','replace')
 if n and n not in names:names[n]=id
GENERIC={'主簿':570,'参军':1014,'老兵':568,'新兵':566,'魏兵':567,'蜀兵':568,'魏将':569,'蜀降卒':566}
slot=866
for n,tpl in GENERIC.items():
 if n in names:continue
 while tables[0][slot*32:slot*32+12].split(b'\0')[0].decode('gbk','replace')!='空':slot+=1
 tables[0][slot*32:slot*32+32]=tables[0][tpl*32:tpl*32+32]
 tables[0][slot*32:slot*32+12]=n.encode('gbk').ljust(12,b'\0');names[n]=slot;slot+=1
write_e5(OUT/'Data.e5',tables)

# ---------- 解析小说 ----------
md=(HERE.parent/'姜维传·历史线续·钟会线.md').read_text(encoding='utf-8')
md=md[md.index('# 正文'):md.index('## 迭代记录')]
md=md.replace('二**###**年','二六四年').replace('樊建**###**','樊建联名上表')
assert '###**' not in md and '**###' not in md
chapters=[]  # [{vol,title,items}]
vol=None
for part in re.split(r'\n(?=## 卷|### 第)',md):
 m=re.match(r'## 卷.　(\S+)',part)
 if m:vol=m[1];continue
 m=re.match(r'### (第.回)　(\S+)',part)
 if not m:continue
 items=[]
 for code in re.findall(r'```\n(.*?)```',part,re.S):
  for line in code.splitlines():
   line=line.strip()
   if not line:continue
   if mm:=re.match(r'\[事件名\]\s*(.+)',line):items.append(('event',mm[1]))
   elif mm:=re.match(r'\[场所\]\s*(.+)',line):items.append(('place',mm[1]))
   elif mm:=re.match(r'\[旁白\]\s*(.+)',line):items.append(('say','',mm[1]))
   elif mm:=re.match(r'\[地图文字\]\s*(.+)',line):
    f=[x.strip() for x in mm[1].split('|')];a=[int(x) for x in f[1:] if x]
    items.append(('map',f[0],(a+[1,1,1])[:3]))
   elif mm:=re.match(r'【([^】]+)】(.+)',line):items.append(('say',mm[1],mm[2]))
   else:raise ValueError(line)
 chapters.append({'vol':vol,'no':m[1],'title':m[2],'items':items})
assert len(chapters)==7,[c['title'] for c in chapters]  # 旧稿短版只到第七回
# 长篇正本优先；尚未扩写的回沿用上面旧稿的短版，保证剧本链不断
lmd=(HERE.parent/'姜维传·钟会线·长篇.md').read_text(encoding='utf-8');lmd=lmd[lmd.index('\n# 正文'):]
long=[];vol=None
for part in re.split(r'\n(?=## 卷|### 第)',lmd):
 m=re.match(r'## 卷.　(\S+)',part)
 if m:vol=m[1];continue
 m=re.match(r'### (第.+?回)　(\S+)',part)
 if not m:continue
 items=[]
 for code in re.findall(r'```\n(.*?)```',part,re.S):
  for line in code.splitlines():
   line=line.strip()
   if not line:continue
   if mm:=re.match(r'\[事件名\]\s*(.+)',line):items.append(('event',mm[1]))
   elif mm:=re.match(r'\[场所\]\s*(.+)',line):items.append(('place',mm[1]))
   elif mm:=re.match(r'\[音乐\]\s*(\d+)',line):items.append(('music',int(mm[1])))
   elif mm:=re.match(r'\[地图音乐\]\s*(\d+)',line):items.append(('mapmusic',int(mm[1])))
   elif mm:=re.match(r'\[旁白\]\s*(.+)',line):items.append(('say','',mm[1]))
   elif mm:=re.match(r'\[地图文字\]\s*(.+)',line):
    f=[x.strip() for x in mm[1].split('|')];a=[int(x) for x in f[1:] if x]
    items.append(('map',f[0],(a+[1,1,1])[:3]))
   elif mm:=re.match(r'\[移动\]\s*(\S+)\s+(\d+)\s+(\d+)\s+([0-3])$',line):items.append(('move',mm[1],*[int(mm[j]) for j in (2,3,4)]))
   elif mm:=re.match(r'\[(登场|退场)\]\s*(.+)',line):
    for nm in re.split(r'[、，,\s]+',mm[2].strip()):items.append(('enter' if mm[1]=='登场' else 'exit',nm))
   elif mm:=re.match(r'【([^】]+)】(.+)',line):items.append(('say',mm[1],mm[2]))
   else:raise ValueError(line)
 long.append({'vol':vol,'no':m[1],'title':m[2],'items':items})
assert [c['title'] for c in long[:len(chapters)]]==[c['title'] for c in chapters[:len(long)]],[c['title'] for c in long]
chapters=long+chapters[len(long):]
print('长篇回数',len(long))

# ---------- 场景 -> 背景/音乐 ----------
BG=[('建业 病榻前',41),('建业 丞相府内室',0),('建业 新朝正殿',50),('五丈原 旧营址',59),('联军中军',18),('薛府',0),('秘府',0),('陆凯客舍',0),('丁奉营',18),('张布府',0),('死牢',70),('钟府',5),('建业 宫门',26),('建业以南 郊外',23),('建业',15),('永安城外',59),('永安',48),('西陵',45),('洛阳 司马',25),('陇西军',1),('绵竹附近',72),('长安 议事',44),
    ('宫门',26),('胡渊营',18),('姜维住处',39),('卫瓘住处',0),('刘禅住处',41),('相国府',11),('谯周府',0),('羊祜府',0),
    ('郊外',23),('剑门关',68),('官署',64),('大街',30),('诸将议事处',39),('魏将软禁处',39),('北门城楼',65),('北门',67),('城门',67),('皇宫外',26),('皇宫',50),('西山',72),('绵竹',68),
    ('姜维府邸',39),('庞会营',18),('句扶营',24),('胡烈营',18),('城外 魏营',1),('关府',41),('魏军营帐',18),
    ('王含营',24),('南郑',59),('阳安关',183),('乐城 城外',59),('乐城',3)]
# 本版音乐采用2026-10-16用户校准的脚本CD定义，见包根目录《当前音轨说明表》。
# 每个事件、地图转场均须显式指定音乐，不再按背景或人物自动猜曲。
def bg_of(place):
 for k,v in BG:
  if k in place:return v
 raise KeyError(place)
pmap=(GAME/'E5/Pmap.e5').read_bytes()
def blocked(meta,mw,mh,x,y):
 if not(0<=x and x+2<mw and 4<=y<mh):return True
 return any(struct.unpack_from('<H',meta,16+2*(yy*mw+xx))[0]&0xff00==0xf000 for yy in range(y-2,y+1) for xx in range(x,x+3))
# R 场景是斜角坐标（scenerender.c SceneRender_Project32）：sx=(x-y)*8+…，sy=(x+y)*4-z*8+…
#   同一 y、x 变化 = 屏幕右下/左上斜线；同一 x、y 变化 = 屏幕左下/右上斜线。朝向 f：1→+x，3→-x，2→+y，0→-y。
# 站位按原作同背景的阵型（probe_pos2_out.txt）：两列对站（f1 对 f3）或两排对站（f2 对 f0），间距 5 格。
# 前两个槽位总是面对面，供两人对话；后面依次补到两侧。
# DOOR：后到的人从哪里出现。('x',X)=从 x=X、同一 y 处走进；('y',Y)=从同一 x、y=Y 处走进；('pt',x,y)=固定门口。
LAYOUT={
 18:[(35,54,1),(46,54,3),(46,45,2),(46,66,0),(51,45,2),(51,66,0),(56,45,2),(56,66,0)],
 183:[(35,54,1),(46,54,3),(46,45,2),(46,66,0),(51,45,2),(51,66,0),(56,45,2),(56,66,0)],
 15:[(27,53,1),(45,53,3),(50,46,2),(50,63,0),(55,46,2),(55,63,0),(60,46,2),(60,63,0)],
 24:[(41,56,1),(47,56,3),(41,61,1),(47,61,3),(41,51,1),(47,51,3),(41,66,1),(47,66,3)],
 50:[(52,72,0),(52,61,2),(39,61,1),(65,61,3),(39,56,1),(65,56,3),(39,51,1),(65,51,3)],
 45:[(50,35,2),(51,49,0),(39,47,1),(66,47,3),(39,52,1),(66,52,3),(39,57,1),(66,57,3)],
 44:[(51,35,2),(52,48,0),(39,48,1),(64,48,3),(39,53,1),(64,53,3),(39,57,1),(64,57,3)],
 48:[(51,33,2),(52,48,0),(39,48,1),(66,48,3),(39,53,1),(66,53,3),(39,58,1),(66,58,3)],
 11:[(50,71,0),(50,57,2),(36,55,1),(63,55,3),(36,50,1),(63,50,3),(36,45,1),(63,45,3)],
 41:[(52,42,2),(52,49,0),(47,46,1),(57,46,3),(47,52,1),(57,52,3),(47,40,1),(57,40,3)],
 39:[(38,65,1),(52,58,3),(47,65,1),(56,65,3),(47,51,1),(56,51,3),(43,58,1),(61,58,3)],
 0:[(48,41,2),(48,47,0),(43,44,1),(53,44,3),(43,50,1),(53,50,3),(43,38,1),(53,38,3)],
 5:[(45,60,1),(50,60,3),(45,65,1),(50,65,3),(45,55,1),(50,55,3),(40,62,1),(55,62,3)],
 59:[(45,46,1),(55,46,3),(45,51,1),(55,51,3),(50,40,2),(50,56,0),(40,48,1),(60,48,3)],
 3:[(46,65,1),(57,65,3),(46,70,1),(57,70,3),(46,60,1),(57,60,3),(51,56,2),(51,75,0)],
 1:[(56,53,1),(61,53,3),(56,58,1),(61,58,3),(56,48,1),(61,48,3),(51,53,1),(66,53,3)],
 72:[(53,52,2),(53,58,0),(48,52,2),(48,58,0),(58,52,2),(58,58,0),(43,52,2),(43,58,0)],
 68:[(43,63,1),(51,63,3),(47,69,1),(55,69,3),(39,69,1),(59,63,3),(43,57,1),(51,57,3)],
 64:[(65,53,2),(65,63,0),(55,58,1),(73,58,3),(55,63,1),(73,63,3),(55,68,1),(73,68,3)],
 70:[(58,31,2),(68,60,0),(60,68,1),(71,67,3),(66,72,0),(60,74,1),(76,67,3),(71,77,0)],
 30:[(42,50,1),(52,50,3),(42,55,1),(52,55,3),(42,45,1),(52,45,3),(47,40,2),(47,60,0)],
 65:[(40,66,1),(50,66,3),(45,61,2),(45,71,0),(40,72,1),(50,72,3),(35,66,1),(55,66,3)],
 67:[(48,58,1),(56,58,3),(48,63,1),(56,63,3),(48,53,1),(56,53,3),(52,48,2),(52,68,0)],
 26:[(46,54,1),(53,54,3),(46,60,1),(53,60,3),(46,48,1),(53,48,3),(40,54,1),(59,54,3)],
 25:[(57,60,1),(70,60,3),(57,65,1),(70,65,3),(62,55,2),(64,70,0),(57,70,1),(70,70,3)],
 23:[(41,53,1),(54,53,3),(41,58,1),(54,58,3),(41,48,1),(54,48,3),(36,53,1),(59,53,3)],
}
DOOR={18:('x',96),183:('x',96),15:('x',96),24:('x',95),23:('x',92),67:('x',96),1:('x',86),
 50:('y',8),11:('y',7),30:('y',5),45:('y',97),44:('y',95),48:('y',98),0:('y',96),59:('y',98),72:('y',97),
 68:('y',98),64:('y',90),65:('y',94),25:('y',96),3:('x',90),
 39:('pt',57,32),41:('pt',58,32),26:('pt',42,54),5:('pt',31,58)}
DEFAULT=[(45,58,1),(52,58,3),(45,63,1),(52,63,3),(45,53,1),(52,53,3),(40,58,1),(57,58,3)]
_meta={}
def pmeta(bg):
 if bg not in _meta:
  meta=read_section(pmap,bg);_meta[bg]=(meta,*struct.unpack_from('<HH',meta,2))
 return _meta[bg]
def layout(bg,n):
 meta,mw,mh=pmeta(bg)
 got=[]
 for bx,by,f in LAYOUT.get(bg,DEFAULT)[:n]:
  for r in range(0,9):
   c=[(bx+dx,by+dy) for dx in range(-r,r+1) for dy in range(-r,r+1) if max(abs(dx),abs(dy))==r]
   c=[p for p in c if not blocked(meta,mw,mh,*p) and all(abs(p[0]-q[0])>=4 or abs(p[1]-q[1])>=4 for q in got)]
   if c:got.append((*c[0],f));break
  else:raise RuntimeError((bg,bx,by))
 return got
def door(bg,x,y,gate=None):
 """后到者的出现点：原作是从画面边缘或门口沿一条轴走进来，不是从正上方（斜角坐标里 y-14 是斜着飘下来）。"""
 meta,mw,mh=pmeta(bg)
 d=gate or DOOR.get(bg,('x',min(95,mw-3)))
 if d[0]=='pt':cand=[(d[1],d[2])]
 elif d[0]=='x':cand=[(min(d[1],mw-3),y+k) for k in (0,1,-1,2,-2,3,-3)]
 else:cand=[(x+k,min(d[1],mh-1)) for k in (0,1,-1,2,-2,3,-3)]
 for p in cand:
  if not blocked(meta,mw,mh,*p):return p
 return cand[0]
def face(sx,sy,x,y):
 dx,dy=x-sx,y-sy
 return (1 if dx>0 else 3) if abs(dx)>=abs(dy) else (2 if dy>0 else 0)

def route(bg,start,goal,occupied):
 """逻辑网格四向寻路；少转折，逐格避开 Pmap 阻挡与在场人物的 3×3 占位。"""
 meta,mw,mh=pmeta(bg);cache={}
 def clear(p):
  if p not in cache:cache[p]=not blocked(meta,mw,mh,*p) and all(abs(p[0]-q[0])>2 or abs(p[1]-q[1])>2 for q in occupied)
  return cache[p]
 if not clear(start) or not clear(goal):return None
 root=(*start,-1);dist={root:0};parent={};heap=[(0,0,root)];end=None
 while heap:
  _,cost,s=heapq.heappop(heap)
  if cost!=dist[s]:continue
  x,y,d=s
  if (x,y)==goal:end=s;break
  for nd,(dx,dy) in enumerate(((0,-1),(1,0),(0,1),(-1,0))):
   p=(x+dx,y+dy)
   if not clear(p):continue
   ns=(*p,nd);nc=cost+10+(2 if d not in (-1,nd) else 0)
   if nc>=dist.get(ns,10**9):continue
   dist[ns]=nc;parent[ns]=s
   heapq.heappush(heap,(nc+10*(abs(p[0]-goal[0])+abs(p[1]-goal[1])),nc,ns))
 if end is None:return None
 full=[]
 while end!=root:full.append(end[:2]);end=parent[end]
 full.reverse();points=[start]
 for j,p in enumerate(full):
  prev=start if j==0 else full[j-1]
  if j==len(full)-1 or (p[0]-prev[0],p[1]-prev[1])!=(full[j+1][0]-p[0],full[j+1][1]-p[1]):points.append(p)
 return points

def projected(bg,x,y):
 """R 背景图中的贴图左边缘/脚底锚点；Project 后的 +40 与背景顶边抵消。"""
 meta,_,_=pmeta(bg)
 return (x-y)*8+struct.unpack_from('<H',meta,8)[0]*4-488,(x+y)*4-192

def offscreen(bg,p):
 x,y=projected(bg,*p)
 # 给人物贴图留出边距，不能只让落脚点刚越过画面边线。
 return x<=-48 or x>=688 or y<=-16 or y>=464

_gate_candidates={}
def gate_route(bg,target,occupied,gate=None):
 """实体门口使用原作门位；边缘进退必须走到人物完整离开画面的位置。"""
 gx,gy=door(bg,*target,gate=gate)
 if (gate or DOOR.get(bg,('x',)))[0]=='pt':
  candidates=[(gx+dx,gy+dy) for dx in range(-3,4) for dy in range(-3,4)]
  candidates.sort(key=lambda p:(max(abs(p[0]-gx),abs(p[1]-gy)),abs(p[0]-target[0])+abs(p[1]-target[1])))
 else:
  if bg not in _gate_candidates:
   meta,mw,mh=pmeta(bg)
   _gate_candidates[bg]=[(x,y) for x in range(mw-2) for y in range(4,mh)
                         if offscreen(bg,(x,y)) and not blocked(meta,mw,mh,x,y)]
  candidates=sorted(_gate_candidates[bg],key=lambda p:(abs(p[0]-gx)+abs(p[1]-gy),abs(p[0]-target[0])+abs(p[1]-target[1])))
 for p in candidates:
  path=route(bg,p,target,occupied)
  if path is not None:return path
 raise ValueError(('门口没有可达路径',bg,target,occupied))

def walk(n,path,finalface):
 out=b''
 for j,p in enumerate(path[1:],1):
  f=finalface if j==len(path)-1 else face(*path[j-1],*p)
  out+=ins(0x32,0,names[n],0,*p,f)+ins(0x1e)  # 切断连续移动批次，待本段走完再发下一段
 if len(path)==1:out+=ins(0x32,0,names[n],0,*path[0],finalface)+ins(0x1e)
 return out

STAGE_PLAN=json.loads((HERE/'stage-plan.json').read_text(encoding='utf-8'))
STAGE_PLAN={(p['回'],p['事件'],p['场所']):p for p in STAGE_PLAN}

report=[]
def stage(bg,cast):
 body=b''
 for (x,y,f),id in zip(layout(bg,len(cast)),cast):body+=ins(0x30,id,x,y,f,0)
 return body
def segments(items):
 """开场[音乐]指定主调；台词间[音乐]在该处换曲；[地图音乐]控制紧随的转场。"""
 scenes=[];cur=None;pending_map_music=None
 for it in items:
  if pending_map_music is not None:assert it[0]=='map',('[地图音乐]后必须是地图文字',it)
  if it[0]=='event':cur={'event':it[1],'segs':[]};scenes.append(cur)
  elif it[0]=='music':
   assert cur is not None and cur.get('map') is None,('[音乐]须属于事件，地图转场使用[地图音乐]',it)
   if not any(s['lines'] for s in cur['segs']):cur['music']=it[1]
   else:cur['segs'][-1]['lines'].append(it)
  elif it[0]=='mapmusic':pending_map_music=it[1]
  elif it[0]=='place':
   if cur is None or (cur['segs'] and cur['segs'][-1]['lines']==[] and False):pass
   cur['segs'].append({'place':it[1],'lines':[]})
  elif it[0]=='map':
   if not scenes or scenes[-1].get('map') is None:
    cur={'map':[],'music':pending_map_music};scenes.append(cur)
   else:assert pending_map_music is None,'连续地图文字组只在组首指定音乐'
   pending_map_music=None
   cur['map'].append(it[1:])
  else:
   if cur.get('map') is not None:  # 地图文字之后的旁白：自成一场
    cur={'event':None,'segs':[{'place':None,'lines':[]}]};scenes.append(cur)
   cur['segs'][-1]['lines'].append(it)
 assert pending_map_music is None,'孤立的[地图音乐]'
 for sc in scenes:
  assert sc.get('music') is not None,('每个事件和转场都必须指定音乐',sc.get('event'))
 return scenes
def music_of(sc):
 return sc['music']
cur_music=[None]
def music_ins(m):
 """同曲不重发，免得每场都从头放。"""
 if m is not None:
  assert m!=21,'CD21是玩家操作界面专曲，不得在剧情使用'
  assert m!=62,'CD62暂不启用：未有合适野心家，不得为用曲硬套人物；司马昭、孙皓禁配'
  assert m==255 or ((f'{m+2:02d}-AudioTrack {m+2:02d}.mp3' in AUDIO_FILES) if USE_AUDIO_MANIFEST else (GAME/f'SoundTrk/{m+2:02d}-AudioTrack {m+2:02d}.mp3').is_file()),('缺少音频或清单记录',m)
 if m is None or m==cur_music[0]:return b''
 cur_music[0]=m;return ins(0x24,m)
def scene_body(sc,chap,mus=None):
 # 2026-10-18用户校准：CD62为司马师曲，可给其他野心家，禁止用于司马昭。
 if 'map' in sc:
  assert not(mus==62 and any('司马昭' in text for text,_ in sc['map'])),('司马昭转场误用司马师曲',chap['no'])
 else:
  cues=[mus]+[it[1] for seg in sc['segs'] for it in seg['lines'] if it[0]=='music']
  sima=any(it[0]=='say' and it[1]=='司马昭' for seg in sc['segs'] for it in seg['lines'])
  assert not(sima and 62 in cues),('司马昭场景误用司马师曲',chap['no'],sc['event'])
 if 'map' in sc:
  body=ins(0x2f)+music_ins(mus if mus is not None else (cur_music[0] if cur_music[0] is not None else 16))+ins(0x27,1,30,0,F,F)+ins(0x27,0,4,F,F,F)+ins(0x1c)
  row=0
  for text,args in sc['map']:
   if args[0]==0:row=0
   for p in split_map(text):
    # dx=0 清页并回首行；1,1 是接下一行，绝不能作为整段首句。
    a=[0,0,args[2]] if row==0 else [1,1,args[2]]
    body+=ins(0x2c,p,*a)+ins(0x09,5)
    row=(row+1)%3
  report.append({'回':chap['no'],'地图文字':len(sc['map']),'音乐':mus})
  return body+ins(0x1d)
 # 先确定开场曲，再按台词顺序生成场内换曲，避免后写的开场曲覆盖全局曲目状态。
 intro_music=music_ins(mus)
 body=b'';first=True
 for seg in sc['segs']:
  bg=bg_of(seg['place'] or prev_place[0]);prev_place[0]=seg['place'] or prev_place[0]
  # 开场在场者按台词与登场标签确定；进退均沿斜角轴路线经门口完成。
  initial=[];entered=set();seen=set()
  for it in seg['lines']:
   if it[0]=='enter':entered.add(it[1]);seen.add(it[1])
   elif it[0]=='say' and it[1] and it[1] not in seen:seen.add(it[1]);initial.append(it[1])
  plan=STAGE_PLAN[(chap['no'],sc['event'],seg['place'])]
  assert set(initial)==set(plan['原开场']),('场景演员变化，请更新stage-plan.json',chap['no'],sc['event'])
  if plan['主位']:
   j=initial.index(plan['主位']);initial[0],initial[j]=initial[j],initial[0]
  order=initial+[n for n in dict.fromkeys(it[1] for it in seg['lines'] if it[0]=='enter') if n not in initial]
  spots=layout(bg,min(8,len(order))) if order else []
  if chap['no']=='第九回' and sc['event']=='谁去搬':spots[2]=(57,70,3)
  if chap['no']=='第九回' and sc['event']=='绑腿':spots[2]=(47,65,0)
  if chap['no']=='第九回':
   if sc['event']=='关门以内':spots[2]=(47,69,0);spots[3]=(55,69,0)
   if sc['event']=='谁下的令':spots[2]=(47,69,0)
   if sc['event']=='不许少一个':spots[2]=(47,65,0)
  if chap['no']=='第十回' and sc['event']=='有人等不及':spots[0]=(55,46,3);spots[1]=(45,46,1)
  if chap['no']=='第十一回' and sc['event']=='谁的诏书':spots[1]=(46,70,1);spots[2]=(57,65,3)
  if chap['no']=='第十二回' and sc['event']=='一道真命':spots[2]=(46,70,1);spots[3]=(57,70,3)
  if chap['no']=='第十三回' and sc['event']=='没有说完的话':spots[0]=(52,51,0);spots[1]=(52,42,2)
  if plan.get('空主位'):
   # 主人未在场，阶下或帐中对坐；不让属员占用君主/主将的座位。
   alternatives={18:[(52,54,1),(59,54,3),(52,61,1),(59,61,3)],11:[(49,46,2),(49,54,0),(55,46,2),(55,54,0)]}
   spots=alternatives[bg][:len(order)]
  for actor,position in plan.get('坐标',{}).items():spots[order.index(actor)]=tuple(position)
  def gate_for(n,action):return plan.get('出入口',{}).get(action+':'+n)
  homes=list(spots)
  slot={};preferred={};free=list(range(len(spots)))
  def take(n):
   assert free,(chap['no'],sc['event'],'同时在场超过8人',n)
   k=preferred.get(n)
   if k not in free:k=free[0]
   free.remove(k);slot[n]=k;preferred[n]=k;spots[k]=homes[k]
   return spots[k]
  on=[];lines=b'';events=[];routes=[];initial_pos=[];music_cues=[]
  for n in initial:
   x,y,f=take(n);lines+=ins(0x30,names[n],x,y,f,0);on.append(n);initial_pos.append({'人物':n,'id':names[n],'x':x,'y':y,'朝向':f})
  stage_bytes=lines;lines=b''
  for it in seg['lines']:
   if it[0]=='enter':
    n=it[1];assert n not in on,(chap['no'],sc['event'],'重复登场',n)
    x,y,f=take(n);path=gate_route(bg,(x,y),[spots[slot[q]][:2] for q in on],gate_for(n,'登场'));sx,sy=path[0]
    lines+=ins(0x30,names[n],sx,sy,face(sx,sy,*path[min(1,len(path)-1)]),0)+walk(n,path,f);on.append(n);events.append('+'+n)
    routes.append({'人物':n,'动作':'登场','路径':path,'终向':f,'出入口':gate_for(n,'登场')})
   elif it[0]=='move':
    n,x,y,f=it[1:];assert n in on,(n,'移动者不在场')
    meta,mw,mh=pmeta(bg);assert not blocked(meta,mw,mh,x,y),(n,x,y,'移动终点阻挡')
    path=route(bg,spots[slot[n]][:2],(x,y),[spots[slot[q]][:2] for q in on if q!=n])
    assert path is not None,(chap['no'],sc['event'],n,'移动路径不通')
    lines+=walk(n,path,f);spots[slot[n]]=(x,y,f);events.append(f'{n}移至{x},{y},{f}');routes.append({'人物':n,'动作':'移动','路径':path,'终向':f})
   elif it[0]=='exit':
    n=it[1];assert n in on,(chap['no'],sc['event'],'未在场却退场',n)
    x,y,f=spots[slot[n]];path=gate_route(bg,(x,y),[spots[slot[q]][:2] for q in on if q!=n],gate_for(n,'退场'))[::-1];sx,sy=path[-1];ef=face(*path[max(0,len(path)-2)],sx,sy)
    lines+=walk(n,path,ef)+ins(0x31,0,names[n],0,0,0,0,6)+ins(0x1e)
    routes.append({'人物':n,'动作':'退场','路径':path,'终向':ef,'出入口':gate_for(n,'退场')})
    on.remove(n);free.append(slot.pop(n));free.sort();events.append('-'+n)
   elif it[0]=='music':
    lines+=music_ins(it[1]);music_cues.append(it[1])
   else:
    assert not it[1] or it[1] in on,(chap['no'],sc['event'],'说话人不在场',it[1])
    lines+=say(it[1],it[2])
  if not first:body+=ins(0x1d)
  body+=ins(8,0)+ins(0x2f)
  if first:body+=intro_music
  body+=ins(0x27,2,F,F,bg,F)+stage_bytes+ins(0x1c)
  if first and sc['event']:body+=ins(0x18,sc['event'])
  if seg['place']:body+=ins(0x17,seg['place'])
  body+=lines
  report.append({'回':chap['no'],'事件':sc['event'],'场所':seg['place'],'背景':bg,'开场在场':initial,'进出':events,
   '主位':plan['主位'],'站位依据':plan['依据'],'台词':sum(1 for it in seg['lines'] if it[0]=='say'),'音乐':mus,'场内换曲':music_cues,'开场坐标':initial_pos,'调度':routes})
  first=False
 return body+ins(0x1d)
prev_place=[None]
def split_map(text):
 """原作地图文字每条≤约37字，长句在标点处拆成数条。"""
 out=[]
 while len(text)>37:
  cut=max([k+1 for k in range(37) if text[k] in '，。；：、'] or [37])
  out.append(text[:cut]);text=text[cut:]
 return out+[text]

# ---------- 新游戏初始化：沿用原版 R_00 第0块的变量/套装/默认设定 ----------
orig=(ORIGINAL_RS/'R_00.EEX').read_bytes()  # 原版副本已随旧剧本删除，取备份
od=decode(orig);top=[i for i in od['instructions'] if i['block']==0]
def span(a,b):
 s=orig[a:b];assert any(i['offset']==a for i in top) and any(i['end']==b for i in top);return s
INIT=ins(0x0a)+ins(8,0)+ins(0x2f)+span(57,73)+span(79,3724)+span(5179,5425)+span(6132,7041)+var(4051,0)+var(4071,0)+flag(3500,0)
# 前情：原版姜维传历史线 R_33 第18～34块（密议 … 事机败露）原样照搬，每块自带 3119/3500 守卫、无跳转
r33=(ORIGINAL_RS/'R_33.EEX').read_bytes()
o33=struct.unpack_from('<I',r33,10)[0];o33=list(struct.unpack_from(f'<{(o33-10)//4}I',r33,10))+[len(r33)]
FORMER=[r33[o33[k]:o33[k+1]] for k in range(18,35)]
assert [i['opcode'] for i in decode(r33)['instructions'] if i['block'] in range(18,35) and i['opcode'] in (0x11,0x0b,0x77)]==[]
PROLOGUE=[('史载成都兵变，钟会、姜维死于乱兵之中。',[1,1,1]),
 ('这一次，夏侯和在乱兵攻入以前，先求见了钟会。',[1,1,1])]

files={}
 # 卷号由正文的卷标题确定，无须另维护RN长度。
for n,chap in enumerate(chapters):
 blocks=[]
 if n==0:
  blocks.append(block([rec(ins(2,'翻盘线 新游戏初始化'),INIT+ins(0x67,1,chap['vol']))]))
  blocks+=FORMER
  blocks.append(block([rec(ins(2,''),scene_body({'map':PROLOGUE},chap,31))]))
 elif chap['vol']!=chapters[n-1]['vol']:
  blocks.append(block([rec(ins(2,''),ins(0x0a)+ins(8,0)+ins(0x2f)+ins(0x67,list(dict.fromkeys(c['vol'] for c in chapters)).index(chap['vol'])+1,chap['vol']))]))
 else:blocks.append(block([rec(ins(2,''),ins(0x0a)+ins(8,0)+ins(0x2f))]))
 if n>=8:blocks.append(block([rec(ins(2,''),flag(919,0))]))
 prev_place[0]=None;cur_music[0]=None
 scs=segments(chap['items'])
 # 转场使用明确的[地图音乐]，不提前借用下一场，避免死讯误配随后的欢快或军议曲。
 want=[music_of(sc) for sc in scs]
 prev_place[0]=None
 for k,sc in enumerate(scs):
  body=ins(2,f"{chap['no']}　{chap['title']}") if k==0 else b''
  body+=scene_body(sc,chap,want[k])
  if want[k] is not None:report.append({'回':chap['no'],'事件':sc.get('event') or '〔地图文字〕','音乐':want[k]})
  if k<len(scs)-1:blocks.append(block([rec(ins(2,''),body)]));continue
  if n<len(chapters)-1:
   blocks.append(block([rec(ins(2,''),body+ins(0x11,2*(n+1)-1))]))
  else:
   end=body+ins(0x2f)+ins(0x27,2,F,F,39,F)+ins(0x1c)+say('',f"{chap['no']}「{chap['title']}」至此。\n后续剧情尚在撰写，可在此保存进度。")
   end+=ins(0x74,1)+ins(8,1)+flag(919)
   blocks.append(block([rec(test(no=[919]),end),rec(ins(4,1),b'')]))
 name=f'R_{n:02d}.EEX';d=write_eex(name,blocks)
 jumps=[i['args'][0]['value'] for i in d['instructions'] if i['opcode']==0x11]
 files[name]={'回':chap['no']+'　'+chap['title'],'blocks':len(blocks),'instructions':len(d['instructions']),'jump':jumps,
  'bytes':len((OUT/'RS'/name).read_bytes())}
(OUT/'build-report.json').write_text(json.dumps({'files':files,'generic_speakers':{k:names[k] for k in GENERIC},'scenes':report},ensure_ascii=False,indent=1),encoding='utf-8')
print(json.dumps(files,ensure_ascii=False,indent=1))
print({k:names[k] for k in GENERIC})
