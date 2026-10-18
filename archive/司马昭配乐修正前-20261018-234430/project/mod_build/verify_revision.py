"""编译并独立逐指令校验全部回目；不启动游戏，不部署。"""
from pathlib import Path
import importlib.util,contextlib,io,json,hashlib,struct,re

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('build_revision',HERE/'build_fanpan.py')
b=importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()):spec.loader.exec_module(b)
out=HERE.parent
stats={};trace=[];max_on=0;all_steps=0
inv={v:k for k,v in b.names.items()}
for n in range(len(b.chapters)):
 p=b.OUT/'RS'/f'R_{n:02d}.EEX';raw=p.read_bytes();d=b.decode(raw)
 assert d['complete'],(p.name,d['errors'])
 boxes=chars=events=maps=moves=0;music=[];on={};bg=None;event=''
 for i in d['instructions']:
  if n==0 and 1<=i['block']<=17:continue # 原作原字节接入段独立验证，不套新稿排版标准
  op=i['opcode'];a=[v['value'] for v in i['args']]
  if op==0x14:
   t=a[0];assert '\ufffd' not in t,(p.name,i['offset'])
   if t.startswith('&'):
    name,t=t[1:].split('\n',1)
    assert name in b.names,(p.name,event,name)
    assert b.names[name] in on,(p.name,event,'说话人不在场',name)
   assert len(t.splitlines())<=3 and all(len(l.encode('gbk'))<=38 for l in t.splitlines()),(p.name,event,t)
   boxes+=1;chars+=len(t.replace('\n',''))
  if op==0x18:event=a[0];events+=1
  if op==0x2c:
   maps+=1
   assert len(a[0])<=37,(p.name,'地图文字过长',a[0])
   assert '\ufffd' not in a[0]
  if op==0x24:music.append(a[0])
  if op==0x2f:on={}
  if op==0x27 and a[0]==2:bg=a[3];on={}
  if op==0x31:
   assert a[1] in on,(p.name,event,'退场者不在场',a)
   on.pop(a[1])
  if op in (0x30,0x32):
   if op==0x30:
    actor,x,y,f,_=a;points=[(x,y)]
    assert actor not in on,(p.name,event,'重复登场',actor)
   else:
    _,actor,_,x,y,f=a
    assert actor in on,(p.name,event,'移动者不在场',actor)
    sx,sy=on[actor]
    assert sx==x or sy==y,(p.name,event,'非单轴移动',actor)
    steps=max(abs(x-sx),abs(y-sy))
    points=[(sx+(0 if x==sx else (1 if x>sx else -1)*k),sy+(0 if y==sy else (1 if y>sy else -1)*k)) for k in range(steps+1)]
    moves+=1;all_steps+=steps
   assert f in range(4)
   for xx,yy in points:
    assert not b.blocked(*b.pmeta(bg),xx,yy),(p.name,event,'Pmap阻挡',bg,actor,xx,yy)
    assert not any(abs(xx-px)<=2 and abs(yy-py)<=2 for other,(px,py) in on.items() if other!=actor),(p.name,event,'人物占位冲突',bg,inv.get(actor),xx,yy,on)
   on[actor]=(x,y);max_on=max(max_on,len(on));assert len(on)<=8
   trace.append({'文件':p.name,'事件':event,'背景':bg,'人物':inv[actor],'动作':hex(op),'终点':[x,y],'朝向':f})
 jumps=[i['args'][0]['value'] for i in d['instructions'] if i['opcode']==0x11]
 assert jumps==([2*n+1] if n<len(b.chapters)-1 else []),(p.name,jumps)
 assert events==sum(it[0]=='event' for it in b.chapters[n]['items']),(p.name,events)
 assert 0x77 not in [i['opcode'] for i in d['instructions'] if not(n==0 and i['block']<=17)],(p.name,'新稿意外写入战斗变量')
 stats[p.name]={'完整解码':True,'事件':events,'对话框':boxes,'对白字数':chars,'地图文字':maps,'分段移动指令':moves,'音乐序列':music,'跳转':jumps,'字节':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

# 接入的十七块精确保持原作；新游戏初始化必须有清除旧线标志。
raw=(b.OUT/'RS/R_00.EEX').read_bytes();first=struct.unpack_from('<I',raw,10)[0]
offsets=list(struct.unpack_from(f'<{(first-10)//4}I',raw,10))+[len(raw)]
assert [raw[offsets[k]:offsets[k+1]] for k in range(1,18)]==b.FORMER
last=b.decode((b.OUT/f'RS/R_{len(b.chapters)-1:02d}.EEX').read_bytes())
flags=[[v['value'] for v in i['args']] for i in last['instructions'] if i['opcode']==0x0b]
assert [919,0] in flags and [919,1] in flags
assert any(i['opcode']==0x74 for i in last['instructions'])
assert (b.OUT/'Data.e5').read_bytes()==(b.GAME/'Data.e5').read_bytes(),'Data与构建输入不同，需审查后包装'

payload={'状态':'通过','范围':'新增及修订正文；R00原作接入17块按原字节验证','结果':stats,'最大同屏人数':max_on,'逐格核验移动步数':all_steps,'原作接入块原字节一致':True,'Data与构建输入一致':True,'音轨检查方式':'文件名清单（未含音频）' if b.USE_AUDIO_MANIFEST else '指定游戏目录的实际音频文件','末回919待续守护':True,'限制':'静态校验；未运行游戏，未实测镜头遮挡、动作动画、存档恢复或战斗衔接。S战斗仍为占位。'}
from verify_dialogue import verify_dialogue
verify_dialogue(b)
from verify_staging import verify_staging
staging=verify_staging(b)
payload['演出回归']=staging['检查计数']
(out/'静态校验.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
(b.OUT/'position-trace.json').write_text(json.dumps(trace,ensure_ascii=False,indent=1),encoding='utf-8')
print(json.dumps(payload,ensure_ascii=False,indent=2))
