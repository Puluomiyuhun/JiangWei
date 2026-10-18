"""R 演出回归：按引擎光标、移动合批/忙态语义检查实际 EEX。"""
import json, struct


def motion_model(instructions):
    busy=set();rejected=[];positions={}
    for k,i in enumerate(instructions):
        op=i['opcode'];a=[v['value'] for v in i['args']]
        if op==0x30:positions[a[0]]=tuple(a[1:3])
        elif op==0x32:
            actor=a[1]
            if actor in busy:rejected.append(actor)
            else:busy.add(actor);positions[actor]=tuple(a[3:5])
            # Cmd_CharMove: 下一条仍为32则在同次VM执行中合批；否则yield。
            # ScriptDriver_StepBattle: 等所有精灵回到待机态才继续。
            if k+1==len(instructions) or instructions[k+1]['opcode']!=0x32:busy.clear()
        elif op==0x31:
            assert a[1] not in busy,'移动中被直接移除'
            positions.pop(a[1],None)
    return rejected,positions


def map_model(commands,initial_y=368):
    y=initial_y;result=[]
    for text,dx,dy,style in commands:
        if dy:y+=24
        if dx==0 or (dy and y>439):y=368
        result.append(y)
    return result


def verify_staging(b):
    counts={'地图段':0,'地图行':0,'移动段':0,'退场':0,'场景站位段':0,'边缘进退':0,'门口进退':0}
    for n in range(len(b.chapters)):
        instructions=[i for i in b.decode((b.OUT/f'RS/R_{n:02d}.EEX').read_bytes())['instructions']
                      if not(n==0 and 1<=i['block']<=17)]
        rejected,_=motion_model(instructions)
        assert not rejected,(n,'移动尚未结束就重发',rejected)
        actual_text=''.join(i['args'][0]['value'] for i in instructions if i['opcode']==0x2c)
        source_text=(''.join(t for t,_ in b.PROLOGUE) if n==0 else '')+''.join(it[1] for it in b.chapters[n]['items'] if it[0]=='map')
        assert actual_text==source_text,(n,'地图分页漏字或重字')
        fresh=True;page=[]
        for k,i in enumerate(instructions):
            op=i['opcode'];a=[v['value'] for v in i['args']]
            if op==0x27:fresh=True;page=[]
            if op==0x2c:
                if fresh:
                    assert a[1:3]==[0,0],(n,'地图首句没有回首行',a)
                    counts['地图段']+=1;fresh=False
                page.append(a);ys=map_model(page)
                assert ys[-1] in (368,392,416),(n,'地图超出三行字幕区',a,ys)
                counts['地图行']+=1
            if op==0x32:
                assert instructions[k+1]['opcode']==0x1e,(n,'分段移动缺少等待边界',i)
                counts['移动段']+=1
            if op==0x31:
                assert instructions[k-1]['opcode']==0x1e and instructions[k-2]['opcode']==0x32,(n,'退场未先走完',i)
                counts['退场']+=1

    for scene in b.report:
        if '背景' not in scene:continue
        counts['场景站位段']+=1
        key=tuple(scene[k] for k in ('回','事件','场所'))
        plan=b.STAGE_PLAN[key];bg=scene['背景']
        if plan['主位']:
            assert scene['开场坐标'][0]['人物']==plan['主位'],('主位反了',key)
        for movement in scene['调度']:
            if movement['动作'] not in ('登场','退场'):continue
            point=movement['路径'][0 if movement['动作']=='登场' else -1]
            gate=movement.get('出入口') or b.DOOR.get(bg,('x',))
            if gate[0]=='pt':
                door=gate[1:]
                assert max(abs(a-c) for a,c in zip(point,door))<=3,(key,'偏离门口',point)
                counts['门口进退']+=1
            else:
                # 独立按 Project32 + SpriteBlit 的48×64矩形核验。
                meta,_,_=b.pmeta(bg);x,y=point
                left=(x-y)*8+struct.unpack_from('<H',meta,8)[0]*4-488
                bottom=(x+y)*4-192
                assert left+48<=0 or left>=640 or bottom<=0 or bottom-64>=400,(key,'仍在画面内就出现/消失',point,left,bottom)
                counts['边缘进退']+=1
    assert counts['场景站位段']==len(b.STAGE_PLAN)
    assert b.bg_of('建业 宫门')==26 and b.bg_of('建业以南 郊外')==23
    palace=next(s for s in b.report if s.get('回')=='第一回' and s.get('事件')=='宫门' and '背景'in s)
    assert all(m['出入口']==['x',96] for m in palace['调度'] if m['动作']=='退场'),'出宫者不能反向走进宫门消失'

    # 负对照：旧参数必定从第二行开始；旧连续路径会拒绝同一人的第二段。
    assert map_model([['旧首句',1,1,1]])==[392]
    assert map_model([['新首句',0,0,1]],416)==[368]
    def decode_body(body):
        block=b.block([b.rec(b.ins(2,''),body)])
        return b.decode(b'EEX\0\1\2'+b.w(0)+b.w(0)+struct.pack('<I',14)+block)['instructions']
    actor=b.names['姜维']
    bad=decode_body(b.ins(0x30,actor,35,54,1,0)+b.ins(0x32,0,actor,0,40,54,1)+b.ins(0x32,0,actor,0,40,60,2))
    assert motion_model(bad)[0]==[actor]
    good=decode_body(b.ins(0x30,actor,35,54,1,0)+b.walk('姜维',[(35,54),(40,54),(40,60)],2))
    rejected,positions=motion_model(good)
    assert not rejected and positions[actor]==(40,60)

    # 移动者退场后，新人必须回到原槽的home，不能继承移动终点。
    key=('测试回','站位复用','涪县 魏军营帐');start=len(b.report)
    b.STAGE_PLAN[key]={'主位':None,'原开场':['姜维'],'依据':'回归用例'}
    try:
        b.scene_body({'event':key[1],'segs':[{'place':key[2],'lines':[
            ('say','姜维','测试。'),('move','姜维',41,54,1),('exit','姜维'),
            ('enter','魏兵'),('say','魏兵','测试。')]}]}, {'no':key[0]},16)
        assert b.report[-1]['调度'][-1]['路径'][-1]==b.layout(18,2)[0][:2]
    finally:
        del b.STAGE_PLAN[key];del b.report[start:]
    payload={'状态':'通过','检查计数':counts,'负对照':['旧地图首句落第二行被复现','旧同人连续转弯拒绝第二段被复现'],
             '回归':['任意旧光标位置下首句回首行','同一人分段移动全部完成','移位退场后槽位复用回原位','按场景主位表核对','边缘出场检查完整48×64贴图越界','实体门口进出位置核对','宫门及郊外不误配宫殿'],
             '限制':'引擎指令语义模型与资源坐标静态核验，未运行游戏。'}
    (b.HERE.parent/'R演出回归核验.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return payload
