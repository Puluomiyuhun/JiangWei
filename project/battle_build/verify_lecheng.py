"""Build and independently check encoded Lecheng events. Does not run the game.

Checks binary conditions/actions, objective branches, data scope, dialogue,
terrain costs and deterministic rebuilding. Simulation is NOT native save QA.
"""
from pathlib import Path
import argparse
import copy
import heapq
import itertools
import json
import re
import tempfile
from collections import defaultdict

import build_lecheng as b

def values(i):return [a['value'] for a in i['args']]
def cmp(actual,value,op):return actual>=value if op==0 else actual<value if op==1 else actual==value

class Model:
    def __init__(self,records):
        self.records=records;self.flags=set();self.turn=1;self.side=0;self.state=None;self.loot=0;self.fired=[]
        self.units={}
        for side,rows in [(0,b.PLAYERS),(1,b.ALLIES),(2,b.ENEMIES)]:
            for idx,x,y,*extra in rows:self.units[idx]={'side':side,'pos':[x,y],'hp':300,'active':True,'policy':None}
    def condition(self,i):
        op=i['opcode'];a=values(i)
        if op in (0,2):return True
        if op==5:
            n=a[0];yes=a[1:1+n];k=a[1+n];no=a[2+n:2+n+k]
            return all(x in self.flags for x in yes) and all(x not in self.flags for x in no)
        if op==0x36:
            assert a[1]==7
            return cmp(self.units[a[0]]['hp'],a[2],a[3])
        if op==0x3f:return cmp(self.turn,*a)
        if op==0x40:return self.side==a[0]
        if op==0x26:
            unit=self.units[a[0]];x,y=unit['pos']
            return unit['active'] and a[1]<=x<=a[3] and a[2]<=y<=a[4]
        if op==0x2e:
            u,v=(self.units[x] for x in a[:2]);dist=max(abs(u['pos'][j]-v['pos'][j]) for j in [0,1])
            assert a[2]==1
            return u['active'] and v['active'] and dist==1
        if op==0x41:
            assert a[0]==5 and a[3]==0
            count=sum(u['active'] and u['hp']>0 and u['side'] in (2,3) for u in self.units.values())
            return cmp(count,a[1],a[2])
        raise AssertionError(('unsupported condition',op))
    def scan(self):
        newly=[]
        if self.state:return newly
        for row in self.records:
            if not all(self.condition(i) for i in row if i['condition']):continue
            key=values(row[0])[0];self.fired.append(key);newly.append(key)
            for i in row:
                if i['condition']:continue
                op=i['opcode'];a=values(i)
                if op==0x0b:
                    if a[1]:self.flags.add(a[0])
                    else:self.flags.discard(a[0])
                elif op==0x53:self.units[a[1]]['active']=False
                elif op==0x4e:self.units[a[1]]['policy']=a[7:]
                elif op==0x59:self.loot+=1
                elif op==0x49:self.state='win'
                elif op==0x0e:self.state='loss'
                elif op not in (0,8,0x74,0x14,0x4f,0x19,0x1a,0x0d):
                    raise AssertionError(('unmodeled action',op))
            if self.state:break
        return newly
    def contact(self):self.units[48]['pos']=[11,12];return self.scan()
    def clear_enemies(self):
        for u in self.units.values():
            if u['side']==2:u['hp']=0;u['active']=False
    def restored(self):
        data=json.loads(json.dumps({'flags':list(self.flags),'units':self.units,'turn':self.turn,'side':self.side,'state':self.state,'loot':self.loot,'fired':self.fired}))
        other=Model(self.records)
        other.flags=set(data['flags']);other.units={int(k):v for k,v in data['units'].items()}
        for key in ['turn','side','state','loot','fired']:setattr(other,key,data[key])
        return other

def verify(out):
    report=b.build(out);out=Path(out)
    decoded={p.name:b.decode(p.read_bytes()) for p in (out/'RS').glob('*.EEX')}
    raw=(out/'Data.e5').read_bytes();table=b.read_section(raw,0)
    names={table[i*32:i*32+12].split(b'\0')[0].decode('gbk') for i in range(1024)}
    boxes=0
    for name,d in decoded.items():
        assert d['complete'] and not d['errors'],name
        for i in d['instructions']:
            a=values(i)
            if i['opcode']==0x14:
                text=a[0];boxes+=1;assert '\ufffd' not in text
                if text.startswith('&'):
                    who,text=text[1:].split('\n',1);assert who in names,(name,who)
                assert len(text.splitlines())<=3
                assert all(len(line.encode('gbk'))<=38 for line in text.splitlines()),text
            if i['opcode']==0x19:assert len(a[0].encode('gbk'))<256
            if i['opcode']==0x11:raise AssertionError('Isolated chain must advance naturally, no R-to-R skip.')
    s=decoded['S_00.EEX']['instructions']
    assert all(i['opcode']!=0x24 or values(i)[0]!=21 for i in s),'CD21 is menu-only'
    assert not any(i['opcode'] in [0x3b,0x52,0x55,0x78] for i in s),'No fake revival or team change'
    rows=defaultdict(list)
    for i in s:
        if i['block']==1:rows[i['record']].append(i)
    records=[rows[k] for k in sorted(rows)]
    assert len(records)==25
    # EEX deploy arrays are fixed-width, unused slots must be fully padded.
    for op,width,count,expected in [(0x46,11,20,b.ALLIES),(0x47,12,80,b.ENEMIES)]:
        arr=next(values(i) for i in s if i['opcode']==op)
        assert len(arr)==width*count
        assert [arr[k*width] for k in range(len(expected))]==[r[0] for r in expected]
        assert set(arr[len(expected)*width:])=={b.F}
    assert [r for r in b.ENEMIES if r[0]==b.JIA]==[(100,20,11,0,2,b.F,0,0)]
    assert table[b.JIA*32:b.JIA*32+12].split(b'\0')[0].decode('gbk')=='贾充'
    grouped=[idx for group in b.ENEMY_GROUPS.values() for idx in group]
    assert len(set(grouped))==len(grouped)==len(b.ENEMIES)==31
    assert set(grouped)=={r[0] for r in b.ENEMIES}
    assert len(b.ENEMIES)>=3*(len(b.PLAYERS)+len(b.ALLIES))
    assert all(r[0]==b.JIA or 260<=r[0]<=545 for r in b.ENEMIES),'Commander plus existing combat soldiers'
    assert all(r[4]==2 for r in b.ENEMIES),'Reserve holds until its phase'
    # Data changes only four explicit empty actor records; every other section is identical.
    base=b.BASE.read_bytes();n=(int.from_bytes(base[0x118:0x11c],'big')-0x110)//12
    allowed=set(range(874,878));changed=[]
    original=b.read_section(base,0)
    for idx in range(1024):
        if table[idx*32:idx*32+32]!=original[idx*32:idx*32+32]:changed.append(idx)
    assert set(changed)==allowed
    assert all(b.read_section(base,j)==b.read_section(raw,j) for j in range(1,n))
    oldblocks=b.split_blocks((b.ROOT/'project/RS/R_06.EEX').read_bytes())
    assert b.split_blocks((out/'RS/R_00.EEX').read_bytes())[1]==oldblocks[7]
    assert b.split_blocks((out/'RS/R_01.EEX').read_bytes())[1:4]==[oldblocks[k] for k in [9,10,11]]

    cases=[]
    def passed(name):cases.append(name)
    jia_event=next(row for row in records if values(row[0])[0]=='jia_defeated')
    assert [values(i) for i in jia_event if i['opcode']==0x53]==[[0,100,0,0,0,0,b.F,0]]
    flag_index=next(j for j,i in enumerate(jia_event) if i['opcode']==0x0b)
    retreat_index=next(j for j,i in enumerate(jia_event) if i['opcode']==0x53)
    assert flag_index<retreat_index
    passed('贾充为主城真实敌将，撤退事件先置单次旗标再普通撤退，不用死亡动画')
    m=Model(records);m.contact();m.turn=6;m.scan()
    for idx in b.OLD:m.units[idx]['pos']=[9,17]
    m.scan()
    assert m.units[b.JIA]['active'] and 11 not in m.flags and m.state is None
    assert m.units[b.JIA]['policy'] is None
    passed('交涉、第六回合及全员接回均不让活着的贾充消失或离开主城')
    m.units[b.JIA]['hp']=0
    assert 'jia_defeated' in m.scan() and not m.units[b.JIA]['active'] and 11 in m.flags
    m=m.restored();assert 'jia_defeated' not in m.scan()
    passed('击退贾充后离场，模型恢复不重复撤退剧情')
    m=Model(records);m.units[b.JIA]['hp']=0;m.scan()
    assert 11 in m.flags and 10 not in m.flags and m.state is None
    m.contact();assert m.fired.count('jia_defeated')==1
    passed('先击退贾充仍须交涉和接应，后交涉不重复撤退')
    m=Model(records);m.contact()
    for idx,u in m.units.items():
        if u['side']==2 and idx!=b.JIA:u.update(hp=0,active=False)
    for idx in b.OLD:m.units[idx]['pos']=[9,17]
    m.scan();assert m.state is None and m.units[b.JIA]['active']
    m.units[b.JIA]['hp']=0;m.scan()
    assert m.state=='win' and m.loot==1 and m.fired.index('jia_defeated')<m.fired.index('victory')
    passed('贾充为最后敌人时必须击退；撤退剧情先于胜利结算')
    m=Model(records);m.contact();m.units[b.JIA]['hp']=0;m.units[0]['hp']=0;m.scan()
    assert m.state=='loss' and 'jia_defeated' not in m.fired and m.loot==0
    passed('贾充与我方关键人物同时兵力归零时失败优先')
    m=Model(records);m.contact()
    assert all(m.units[idx]['policy'][0]==1 for idx in b.WEST_GUARD+b.NORTH_SCREEN)
    assert all(m.units[idx]['policy'] is None for idx in b.INNER_GUARD+b.NORTH_RESERVE)
    assert [m.units[idx]['policy'][1] for idx in b.ESCORT_ARCHERS]==[874,876]
    passed('交涉只发动西门与北门前队，两队督战弓兵追射旧卒')
    m.turn=3;assert 'turn3' in m.scan()
    assert all(m.units[idx]['policy'][0]==1 for idx in b.INNER_GUARD)
    assert all(m.units[idx]['policy'] is None for idx in b.NORTH_RESERVE)
    m=m.restored();assert 'turn3' not in m.scan()
    passed('第三回合城内主阵出动，北门后队仍待命，恢复不重播')
    m.turn=6;assert 'turn6' in m.scan()
    assert all(m.units[idx]['policy'][0]==1 for idx in b.NORTH_RESERVE)
    assert not m.scan();passed('第六回合北门后队出动且仅一次')
    m=Model(records);m.turn=6;m.scan()
    assert all(m.units[idx]['policy'] is None for idx in b.INNER_GUARD+b.NORTH_RESERVE)
    m.contact();assert {'turn3','turn6'}<=set(m.fired)
    passed('晚交涉不会漏掉已经满足回合数的调兵事件')
    m=Model(records);m.contact();m.clear_enemies()
    m.units[369].update(hp=100,active=True)
    for idx in b.OLD:m.units[idx]['pos']=[9,17]
    m.scan();assert m.state is None
    m.units[369].update(hp=0,active=False);m.scan();assert m.state=='win'
    passed('扩军后的最后一名补给士仍计入胜利条件')
    m=Model(records);assert not m.scan();assert 10 not in m.flags
    m.units[0]['pos']=[11,12];m.scan();assert 10 not in m.flags;passed('仅王含接触有效')
    m.units[875]['hp']=210
    assert 'contact' in m.contact();assert 10 in m.flags and 11 not in m.flags
    assert m.units[875]['hp']==210 and m.units[875]['side']==1
    assert m.units[875]['policy'][0]==6
    assert not m.scan();passed('交涉单次且旧卒同一实体/血量保留')
    m=m.restored();assert not m.scan();passed('交涉后模型序列化恢复不重复')
    m.side=2;assert any(x.startswith('volley_') for x in m.scan());assert not m.scan();passed('敌军阶段放箭对白仅一次')
    m=Model(records);m.clear_enemies();m.scan();assert m.state is None
    assert 'contact_secured' in m.contact() and 'contact' not in m.fired
    m.side=2;assert not any(x.startswith('volley_') for x in m.scan());passed('先清敌军不能跳过接应；弓阵已灭使用专用对白')
    for order in itertools.permutations(b.OLD):
        m=Model(records);m.contact();m.clear_enemies()
        for idx in order:
            m.units[idx]['pos']=[9,17];m.scan()
            m=m.restored()
        assert m.state=='win' and m.loot==1
        assert {'rescue_0','rescue_1','rescue_2','all_rescued','victory'}<=set(m.fired)
        m.scan();assert m.loot==1
        passed('三队任意顺序接回 '+str(order))
    for idx in [0,48,140,1,5,9]+b.OLD:
        m=Model(records);m.contact();m.clear_enemies()
        for old in b.OLD:m.units[old]['pos']=[9,17]
        m.units[idx]['hp']=0;m.scan()
        assert m.state=='loss' and m.loot==0,idx
        passed('失败优先于同次胜利 '+str(idx))
    m=Model(records);m.contact();m.units[874]['pos']=[9,17];m.scan();m.units[874]['hp']=0;m.scan()
    assert m.state is None and m.units[282]['policy'][0]==1;passed('已接回离图不误触失败，弓手解除离场追击目标')
    m=Model(records);m.contact()
    for idx in b.OLD:m.units[idx]['pos']=[9,17]
    m.scan();m.side=2
    assert not any(x.startswith('volley_') for x in m.scan());passed('旧卒全撤离后不再播放追射他们的对白')
    m=Model(records);m.contact();m.clear_enemies()
    for idx in b.OLD:m.units[idx]['pos']=[9,15]
    m.scan();assert m.state is None;passed('接应区外一格不能结算')
    for turn,outcome in [(20,'win'),(21,'loss')]:
        m=Model(records);m.contact();m.clear_enemies();m.turn=turn
        for idx in b.OLD:m.units[idx]['pos']=[9,17]
        m.scan();assert m.state==outcome
        passed(f'回合边界{turn}：{outcome}')
    for idx in b.OLD:
        m=Model(records);m.contact();m.units[idx]['hp']=0;m=m.restored();m.scan();assert m.state=='loss'
        passed('模型读档后识别旧卒损失 '+str(idx))

    grid=json.loads((b.SOURCE/'地图网格.json').read_text(encoding='utf-8'))
    terrain=grid['terrain'];troops=b.read_section(raw,4);classes=b.read_section(raw,3)
    assert grid['width']==grid['height']==24 and len(terrain)==576
    allrows=b.PLAYERS+b.ALLIES+b.ENEMIES
    assert len({r[0] for r in allrows})==len(allrows)
    assert len({tuple(r[1:3]) for r in allrows})==len(allrows)
    def movement(idx):
        cls=table[idx*32+26];typ=cls//3 if cls<60 else cls-40
        assert typ<40
        return troops[typ*60+30:typ*60+60]
    for idx,x,y,*extra in allrows:
        assert 0<=x<24 and 0<=y<24
        assert movement(idx)[terrain[y*24+x]]!=255,(idx,x,y)
    def cost(idx,start,end):
        costs=movement(idx);q=[(0,start)];dist={start:0}
        while q:
            c,(x,y)=heapq.heappop(q)
            if (x,y)==end:return c
            if c!=dist[(x,y)]:continue
            for nx,ny in [(x+1,y),(x-1,y),(x,y+1),(x,y-1)]:
                if not (0<=nx<24 and 0<=ny<24):continue
                step=costs[terrain[ny*24+nx]]
                if step==255:continue
                nc=c+step
                if nc<dist.get((nx,ny),10**9):dist[(nx,ny)]=nc;heapq.heappush(q,(nc,(nx,ny)))
        raise AssertionError(('unreachable',idx,start,end))
    paths=[{'人物':48,'用途':'接触旧卒','基础地形耗点':cost(48,(10,12),(11,12))}]
    for idx,row,dest in zip(b.OLD,b.ALLIES[:3],b.DEST):paths.append({'人物':idx,'用途':'撤到接应区','基础地形耗点':cost(idx,tuple(row[1:3]),dest)})
    for idx,x,y,*extra in b.ENEMIES:
        assert cost(idx,(x,y),(14,12))<100,'Every enemy can reach the west gate'
    assert not any(b.RESCUE[0]<=r[1]<=b.RESCUE[2] and b.RESCUE[1]<=r[2]<=b.RESCUE[3] for r in b.ENEMIES)
    assert (11,12) not in {tuple(r[1:3]) for r in allrows}
    passed('贾充及30队守军地形可站立且可抵西门，不占接应区与首次交涉格')
    # Archer base class 6 promotes to 7 at level 20; shape 3 reaches straight distance 3.
    assert classes[7*35+1]==3
    paths.append({'人物':282,'用途':'移动到(15,11)可用默认形状3覆盖(12,11)','基础地形耗点':cost(282,(15,10),(15,11))})
    paths.append({'人物':283,'用途':'(15,13)默认形状3覆盖(12,13)','基础地形耗点':0})
    with tempfile.TemporaryDirectory(prefix='lecheng-rebuild-') as temp:
        b.build(Path(temp))
        assert all((out/name).read_bytes()==(Path(temp)/name).read_bytes() for name in report['文件'])
    result={'结果':'静态检查通过','事件记录':len(records),'对白框（含前后R）':boxes,'模型用例':cases,
            'Data仅修改空人物槽':changed,'前后R选段逐字节保持':True,'独立目录重建一致':True,
            '布阵点数':len(allrows),'敌军数':len(b.ENEMIES),'敌军分队':b.ENEMY_GROUPS,
            '敌我比例（含待救旧卒）':len(b.ENEMIES)/(len(b.PLAYERS)+len(b.ALLIES)),
            '基础地形检查':paths,
            '边界':'事件模型解释编译后指令，非引擎执行；JSON恢复非原生存档测试。地形检查不模拟占位、特技或战斗伤害；弓兵仅核默认形状，装备覆盖须实机核。',
            '尚未验证':['游戏启动与编成界面','AI实际护送路线及战斗平衡','战中原生存读档','动画镜头及BGM实际播放']}
    (out/'验证报告.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['模型用例']},ensure_ascii=False,indent=2))
    print('Event-model cases:',len(cases))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=b.ROOT/'project/mod_build/build/lecheng')
    verify(parser.parse_args().out)
