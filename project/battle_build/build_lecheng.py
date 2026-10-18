"""Build an isolated R00 -> S00 -> R01 Lecheng prototype. Never deploys.

The long-form sixteen R scripts and its Data input remain unchanged.
Run from any directory; Python 3.10+, standard library only.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools/eex'), str(ROOT/'project/mod_build')]
from eex_strategy_refs import decode, SCHEMA
from dump_e5_skills import read_section
from dialogue_layout import paginate

SOURCE = ROOT/'project/战场设计/乐城S'
BASE = ROOT/'resources/build-inputs/game/Data.e5'
F = 65535
JIA = 100
PLAYERS = [(0,9,13),(48,10,12),(140,8,13),(1,8,14),(5,7,14)]
OLD = [874,875,876]
# id, x, y, level adjustment, policy, target, target x, target y
ALLIES = [(874,12,11,103,2,F,0,0), (875,12,12,103,2,F,0,0),
          (876,12,13,103,2,F,0,0), (9,17,3,0,0,F,0,0),
          (877,18,3,0,0,F,0,0)]
# Existing combat actors only. Explicit groups prevent later roster additions
# from silently inheriting another group's activation or escort-targeting rules.
ESCORT_ARCHERS = [282,283]
WEST_GUARD = [260,261,266,267,284,285,274,275]
INNER_GUARD = [262,263,268,269,270,271,286,287,362,368,306,307]
NORTH_SCREEN = [264,265]
NORTH_RESERVE = [272,273,454,455,363,369]
ENEMY_GROUPS = {'主城贾充':[JIA],'西门督战队':ESCORT_ARCHERS+WEST_GUARD,
                '城内主阵':INNER_GUARD,'北门守队':NORTH_SCREEN+NORTH_RESERVE}
ENEMIES = [(JIA,20,11,0,2,F,0,0),
           (282,15,10,0,2,F,0,0), (283,15,13,0,2,F,0,0),
           (260,17,10,0,2,F,0,0), (261,17,14,0,2,F,0,0),
           (266,16,11,0,2,F,0,0), (267,16,12,0,2,F,0,0),
           (284,17,11,0,2,F,0,0), (285,17,12,0,2,F,0,0),
           (274,18,10,0,2,F,0,0), (275,18,14,0,2,F,0,0),
           (262,20,13,0,2,F,0,0), (263,18,9,0,2,F,0,0),
           (268,19,10,0,2,F,0,0), (269,20,10,0,2,F,0,0),
           (270,20,12,0,2,F,0,0), (271,20,14,0,2,F,0,0),
           (286,21,10,0,2,F,0,0), (287,21,14,0,2,F,0,0),
           (362,21,11,0,2,F,0,0), (368,21,12,0,2,F,0,0),
           (306,19,15,0,2,F,0,0), (307,20,15,0,2,F,0,0),
           (264,19,5,0,2,F,0,0), (265,20,4,0,2,F,0,0),
           (272,18,6,0,2,F,0,0), (273,19,6,0,2,F,0,0),
           (454,18,7,0,2,F,0,0), (455,19,7,0,2,F,0,0),
           (363,18,8,0,2,F,0,0), (369,19,8,0,2,F,0,0)]
DEST = [(9,17),(10,18),(11,17)]
RESCUE = (8,16,12,19)
FLAGS = {'contact':10,'jia_left':11,'rescued_a':20,'rescued_b':21,'rescued_c':22,
         'all_rescued':23,'volley':30,'hurt':31,'turn3':32,'turn6':33,
         'reminder':34,'deadline':35,'finished':90,'ending_hold':91}

def w(v): return struct.pack('<H',v)

def ins(op,*args):
    tags=SCHEMA[f'{op:02X}']['args']
    if op in (6,0x4a): tags=tags+[0x38]*5+[0x39]*5
    if op in (0x46,0x47): tags=tags*(20 if op==0x46 else 80)
    assert len(tags)==len(args),(hex(op),len(tags),len(args))
    data=w(op)
    for tag,value in zip(tags,args):
        if tag!=1: data+=w(tag)
        data+=str(value).encode('gbk')+b'\0' if tag==5 else struct.pack('<I' if tag==4 else '<H',value)
    return data

def test(yes=(),no=()):
    return w(5)+w(0x35)+w(len(yes))+b''.join(w(n) for n in yes)+w(0x35)+w(len(no))+b''.join(w(n) for n in no)

def rec(cond,body):
    body+=w(0); data=cond+w(0)+w(len(body))+body
    assert len(data)<65536
    return w(len(data))+data

def block(records): return w(len(records))+b''.join(records)
def flag(n): return ins(0x0b,n,1)
def var(n,v): return ins(0x77,2,n,2,0,v)

def write_eex(path,blocks):
    offset=10+len(blocks)*4; head=b'EEX\0\1\2'+w(0)+w(0)
    for b in blocks: head+=struct.pack('<I',offset); offset+=len(b)
    raw=head+b''.join(blocks)
    result=decode(raw)
    assert result['complete'],result['errors']
    path.write_bytes(raw)
    return result

def split_blocks(raw):
    first=struct.unpack_from('<I',raw,10)[0]
    offsets=list(struct.unpack_from(f'<{(first-10)//4}I',raw,10))+[len(raw)]
    return [raw[a:b] for a,b in zip(offsets,offsets[1:])]

def write_e5(path,sections):
    offset=0x110+12*len(sections);head=b'Ls12'+bytes(12)+bytes(range(256));body=b''
    for data in sections:
        head+=struct.pack('>III',len(data),len(data),offset);body+=data;offset+=len(data)
    path.write_bytes(head+body)

def make_data(path):
    raw=BASE.read_bytes(); count=(int.from_bytes(raw[0x118:0x11c],'big')-0x110)//12
    sections=[bytearray(read_section(raw,i)) for i in range(count)]
    table=sections[0]
    additions=[(874,'乐城旧卒甲'),(875,'乐城旧卒乙'),(876,'乐城旧卒丙'),(877,'北门蜀兵')]
    for idx,name in additions:
        assert table[idx*32:idx*32+12].split(b'\0')[0].decode('gbk')=='空'
        table[idx*32:idx*32+32]=table[260*32:260*32+32]
        table[idx*32:idx*32+12]=name.encode('gbk').ljust(12,b'\0')
    write_e5(path,sections)
    return additions

def load_dialogue():
    result={};key=None
    for line in (SOURCE/'对白.txt').read_text(encoding='utf-8').splitlines():
        if re.fullmatch(r'\[[a-z0-9_]+\]',line):key=line[1:-1];result[key]=[]
        elif line.startswith('【'):
            who,text=line[1:].split('】',1);result[key].append(('' if who=='旁白' else who,text))
    return result

def say(who,text):
    return b''.join(ins(0x14,('&'+who+'\n' if who else '')+'\n'.join(p.lines))
                    for p in paginate(text,19 if who else 18))

def policy(idx,value,target=F,x=0,y=0): return ins(0x4e,0,idx,0,0,0,0,F,value,target,x,y)
def hp(idx,value,cmp=1): return ins(0x36,idx,7,value,cmp)
def deploy(op,rows):
    width=11 if op==0x46 else 12;count=20 if op==0x46 else 80;args=[]
    for idx,x,y,lv,ai,target,tx,ty in rows:
        args.extend([idx,0,x,y,3,lv,2,ai,target,tx,ty] if op==0x46 else [idx,0,0,x,y,3,lv,2,ai,target,tx,ty])
    args.extend([F]*(width*(count-len(rows))))
    return ins(op,*args)

def build(out):
    out=Path(out); (out/'RS').mkdir(parents=True,exist_ok=True)
    additions=make_data(out/'Data.e5')
    dialogue=load_dialogue()
    speech=lambda key: b''.join(say(*line) for line in dialogue[key])
    events=[]
    def event(key,cond,body,description):
        events.append({'key':key,'说明':description,'条件字节':cond.hex(),'动作字节':body.hex()})
        return rec(ins(2,key)+cond,body)

    # Minimal deterministic new-game setup. Fresh join applies growth and default equipment.
    init=ins(0x0a)+ins(8,0)+ins(0x2f)
    for idx,value in [(4051,0),(4057,F),(4031,0),(4076,0),(4033,100),(4034,0),(4035,1),
                      (4039,1),(4073,1),(4078,1),(4079,1),(4065,1),(4066,1),
                      (3990,1),(4023,2),(4046,1)]:init+=var(idx,value)
    # Fresh prototype must not inherit a historical party from a save.
    init+=var(900,255)
    for idx in range(1024):init+=ins(0x78,900,1,idx,16) # general team, NOT battle-side manipulation
    for pos,(idx,_,_) in enumerate(PLAYERS):init+=ins(0x3b,idx,2,19 if pos==0 else 0)
    init+=ins(0x3a,0,0,3000)
    chapter=split_blocks((ROOT/'project/RS/R_06.EEX').read_bytes())
    pre=chapter[7] # exact existing 马后头 scene, including staging
    prep=ins(8,0)+speech('prepare')+ins(0x24,21)+var(4057,5)
    for slot,(_,x,y) in enumerate(PLAYERS):prep+=ins(0x4b,slot,x,y,1,0)
    prep+=ins(6,1,5,48,140,1,5,F,F,F,F,F,F)+ins(8,1)
    confirm=ins(8,0)+ins(6,0,0,*([F]*10))+var(4057,F)+ins(0x24,255)+ins(0x1d)+ins(0x0d)
    r0=write_eex(out/'RS/R_00.EEX',[block([rec(ins(2,'乐城样关初始化'),init)]),pre,
        block([rec(ins(2,'编成与地图预览'),prep)]),block([rec(ins(7),confirm)])])

    begin=ins(8,0)+ins(0x74,0)+ins(0x44)+var(4031,0)+var(4051,0)
    # 21 in the engine limit leaves 20 complete playable turns; scripted turn 21 fails first.
    begin+=ins(0x45,0,0,21,0,0,F,1,0,1,1)+deploy(0x46,ALLIES)+deploy(0x47,ENEMIES)
    for slot,(_,x,y) in enumerate(PLAYERS):begin+=ins(0x4b,slot,x,y,1,0)
    begin+=ins(0x27,3,F,F,F,5)+ins(0x1c)+ins(0x24,101)+ins(0x17,'乐城')+ins(0x18,'放下刀的人')
    begin+=speech('opening')
    goal1='胜利：王含接触旧卒，接回三队旧卒，击退贾充及守军。\n失败：任一出战武将、袁綝或未接回旧卒撤退。\n期限：20回合。\n接应区：西南(8,16)至(12,19)。'
    goal2='胜利：三队旧卒抵达西南接应区，并击退贾充及全部守军。\n失败：任一出战武将、袁綝或未接回旧卒撤退。\n期限：20回合。'
    begin+=ins(0x19,goal1)+ins(0x1a,'护王含接近旧卒，接人后再占城。')+ins(0x5a)+ins(0x74,1)+ins(8,1)
    records=[]
    # All failure guards precede rescue/victory; finished protects mutually exclusive outcomes.
    for idx,key in [(0,'fail_hero'),(48,'fail_wang'),(140,'fail_guan'),(9,'fail_yuan')]:
        body=ins(8,0)+ins(0x74,0)+flag(90)+speech(key)+ins(0x0e)+ins(0x0d)
        records.append(event(key,test(no=[90])+hp(idx,1),body,f'{idx}的HP小于1，失败优先'))
    for idx in [1,5]:
        records.append(event(f'fail_support_{idx}',test(no=[90])+hp(idx,1),ins(8,0)+ins(0x74,0)+flag(90)+speech('fail_support')+ins(0x0e)+ins(0x0d),'全部出战武将须保全'))
    for i,idx in enumerate(OLD):
        body=ins(8,0)+ins(0x74,0)+flag(90)+speech('fail_old')+ins(0x0e)+ins(0x0d)
        records.append(event(f'fail_old_{i}',test(no=[90,20+i])+hp(idx,1),body,'未接回的旧卒被击溃'))
    records.append(event('timeout',test(no=[90])+ins(0x3f,21,0),ins(8,0)+ins(0x74,0)+flag(90)+speech('fail_timeout')+ins(0x0e)+ins(0x0d),'第21回合起失败'))

    # Like original S46, the commander gets his own HP-zero event. Ordinary
    # retreat (last arg 0) preserves the escape story; no revival or invulnerability.
    retreat=ins(8,0)+ins(0x74,0)+flag(11)+speech('jia_escape')
    retreat+=ins(0x53,0,JIA,0,0,0,0,F,0)+speech('jia_escape_after')
    retreat+=ins(0x74,1)+ins(8,1)
    records.append(event('jia_defeated',test(no=[11,90])+hp(JIA,1),retreat,
                         '主城贾充兵力归零后单次撤退；与交涉、接应顺序无关，失败判定优先'))

    contact=b''
    for idx,(x,y) in zip(OLD,DEST):
        contact+=ins(0x4f,idx,F,3,1,1,0)+policy(idx,6,x=x,y=y)
    # The battle-side and live unit record never change: HP, status, equipment are retained.
    for idx,target in zip(ESCORT_ARCHERS,[874,876]):contact+=policy(idx,3,target=target)
    for idx in WEST_GUARD:contact+=policy(idx,1)
    contact+=flag(10)
    # Contact activates the screens, not the commander's retreat.
    contact+=policy(9,1)+policy(877,1)
    for idx in NORTH_SCREEN:contact+=policy(idx,1)
    contact+=ins(0x19,goal2)+ins(0x1a,'接回三队旧卒，击退城内守军。')+ins(0x74,1)+ins(8,1)
    records.append(event('contact_secured',test(no=[10,90])+ins(0x2e,48,875,1)+hp(282,1)+hp(283,1),ins(8,0)+ins(0x74,0)+speech('contact_secured')+contact,'先压掉两队弓手再接触：不再指着已死弓手说话'))
    records.append(event('contact',test(no=[10,90])+ins(0x2e,48,875,1),ins(8,0)+ins(0x74,0)+speech('contact')+contact,'王含邻接中队旧卒；只发生一次'))

    for i,idx in enumerate(OLD):
        body=ins(8,0)+ins(0x74,0)+speech(['rescue_a','rescue_b','rescue_c'][i])+flag(20+i)
        body+=ins(0x53,0,idx,0,0,0,0,F,0)
        if i in (0,2):body+=policy(282 if i==0 else 283,1)
        body+=ins(0x74,1)+ins(8,1)
        records.append(event(f'rescue_{i}',test(yes=[10],no=[20+i,90])+hp(idx,1,0)+ins(0x26,idx,*RESCUE),body,'旧卒活着抵达接应区后离图，旗标在离图前保存'))
    records.append(event('all_rescued',test(yes=[20,21,22],no=[23,90]),ins(8,0)+ins(0x74,0)+speech('all_rescued')+flag(23)+ins(0x19,'胜利：击退全部守军。\n旧卒三队已接回。\n失败：任一出战武将或袁綝撤退。\n期限：20回合。')+ins(0x74,1)+ins(8,1),'接应完成后刷新目标'))

    # The first enemy phase after defection; independent from turn number.
    for idx in [282,283]:
        records.append(event(f'volley_{idx}',test(yes=[10],no=[23,30,90])+ins(0x40,2)+hp(idx,1,0),ins(8,0)+speech('first_volley')+flag(30)+ins(8,1),'旧卒未全接回时的敌军阶段，至少一队弓手活着；共用单次旗标'))
    records.append(event('old_hurt',test(yes=[10],no=[21,31,90])+hp(875,100),ins(8,0)+speech('old_hurt')+flag(31)+ins(8,1),'中队旧卒HP低于100，仍未接回'))
    for turn,key,marker,yes,no in [(2,'contact_reminder',34,[],[10]),(3,'turn3',32,[10],[]),
                                   (6,'turn6',33,[10],[]),(18,'near_deadline',35,[],[])]:
        body=ins(8,0)+speech(key)+flag(marker)
        if key=='turn3':
            for idx in INNER_GUARD:body+=policy(idx,1)
        if key=='turn6':
            for idx in NORTH_RESERVE:body+=policy(idx,1)
        body+=ins(8,1)
        cond=test(yes=yes,no=[marker,90]+no)+ins(0x3f,turn,0)+ins(0x40,0)
        if key in ['turn3','turn6','near_deadline']:cond+=ins(0x41,5,1,0,0,0,0,23,23)
        records.append(event(key,cond,body,f'第{turn}回合起我军阶段，单次'))

    alive_enemies=ins(0x41,5,0,2,0,0,0,23,23)
    finish=ins(8,0)+ins(0x74,0)+flag(90)+speech('victory')
    finish+=ins(0x59,0,F,0,F,0,F,0,0)+ins(0x49)+ins(0x0d)
    records.append(event('victory',test(yes=[10,11,20,21,22,23],no=[90])+alive_enemies,finish,'接应、贾充撤离及守军清零同时成立；只结算一次'))
    s0=write_eex(out/'RS/S_00.EEX',[block([rec(ins(2,'乐城布阵与开场'),begin)]),block(records),block([rec(ins(2,'战场收尾'),ins(0x24,255)+ins(8,0)+ins(0x1d))])])

    # Exact original chapter-seven aftermath. No replay of the old battle narrative.
    rpost=ins(0x0a)+ins(8,0)+ins(0x2f)+ins(0x74,1)
    end=ins(8,0)+ins(0x2f)+ins(0x27,2,F,F,39,F)+ins(0x1c)+speech('finish')+flag(91)+ins(8,1)
    r1=write_eex(out/'RS/R_01.EEX',[block([rec(ins(2,'乐城战后'),rpost)]),chapter[9],chapter[10],chapter[11],
         block([rec(test(no=[91]),end),rec(ins(4,1),b'')])])
    payload={'性质':'乐城扩军版样关；构建器不部署，实机状态另见部署记录；不是长篇正式编号',
             '流程':'R_00 马后头/编成 -> S_00 乐城 -> R_01 战果/骆谷/第一个/停留',
             '地图':5,'回合上限':20,'引擎保护上限':21,'玩家':PLAYERS,'友军':ALLIES,'敌军':ENEMIES,
             '敌军分队':ENEMY_GROUPS,'敌我比例（含待救旧卒）':len(ENEMIES)/(len(PLAYERS)+len(ALLIES)),
             '接应区':RESCUE,'撤离目的格':DEST,'局部旗标':FLAGS,'新增Data人物':additions,
             'Data基线sha256':hashlib.sha256(BASE.read_bytes()).hexdigest(),
             'R源sha256':hashlib.sha256((ROOT/'project/RS/R_06.EEX').read_bytes()).hexdigest(),
             '沿用R06块':[7,9,10,11],'事件':events,
             '文件':{n:{'sha256':hashlib.sha256((out/n).read_bytes()).hexdigest(),'bytes':(out/n).stat().st_size}
                     for n in ['Data.e5','RS/R_00.EEX','RS/S_00.EEX','RS/R_01.EEX']},
             '限制':['从新游戏或本版战前编成存档进入，不读取旧版战中存档','旧卒以待命友军转接应方针表示倒戈，不执行阵营颜色切换',
                    '贾充为主城真实敌将，兵力归零时普通撤退；未制作沿北门路线移动的逃跑动画','未实测AI、动画、战场读档与数值难度']}
    (out/'build-report.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    # Readable script includes real conditions in the same ordering as encoded events.
    lines=['乐城完整S样关·主将修正版（贾充及30队守军）','流程：战前R → 编成出兵 → S → 战后R','',
           '旧卒交涉后改变方针，保留血量和状态。贾充驻守主城，兵力归零触发对白及普通撤退，交涉不使他离场。','',
           '【S开场】']
    def prose(key):return ['【'+(who or '旁白')+'】'+text for who,text in dialogue[key]]
    lines+=prose('opening')
    mapping={'contact':['contact'],'contact_secured':['contact_secured'],'jia_defeated':['jia_escape','jia_escape_after'],'rescue_0':['rescue_a'],'rescue_1':['rescue_b'],'rescue_2':['rescue_c'],
             'all_rescued':['all_rescued'],'volley_282':['first_volley'],'volley_283':['first_volley'],'old_hurt':['old_hurt'],
             'contact_reminder':['contact_reminder'],'turn3':['turn3'],'turn6':['turn6'],
             'near_deadline':['near_deadline'],'victory':['victory'],'timeout':['fail_timeout']}
    order=['contact','contact_secured','volley_282','old_hurt','rescue_0','rescue_1','rescue_2','all_rescued','jia_defeated',
           'contact_reminder','turn3','turn6','near_deadline','victory','fail_hero','fail_wang','fail_guan',
           'fail_yuan','fail_support_1','fail_old_0','timeout']
    lines+=['','下文按游玩阅读顺序排列；二进制实际先检查失败，再检查接应与胜利。',
            '交涉有常规／弓阵已清两种互斥对白，不会连续演两遍。']
    for event_key in order:
        e=next(e for e in events if e['key']==event_key)
        lines+=['','【事件：'+e['key']+'】',e['说明']]
        fallback=['fail_old'] if e['key'].startswith('fail_old') else ['fail_support'] if e['key'].startswith('fail_support') else [e['key']]
        for key in mapping.get(e['key'],fallback):lines+=prose(key)
    lines+=['','【前后R全文】','战前原样接入第七回“马后头”。战后接战果地图文字、“骆谷”与“第一个”。']
    draft=(ROOT/'project/mod_build/draft/ch7.md').read_text(encoding='utf-8')
    for first,last in [('马后头','放下刀的人'),('骆谷','汉中是谁的')]:
        fragment=draft[draft.index('[事件名] '+first):draft.index('[事件名] '+last)]
        lines+=['',fragment.strip()]
    lines+=['','只在独立样关包中使用R00/S00/R01；原十六回R保持。尚未启动游戏验证。']
    (out/'完整S文案与事件.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return payload

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'project/mod_build/build/lecheng')
    args=parser.parse_args()
    result=build(args.out)
    print(json.dumps({'output':str(args.out),'events':len(result['事件']),'files':result['文件']},ensure_ascii=False,indent=2))
