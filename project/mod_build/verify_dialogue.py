"""独立从分回源稿取台词，逐框核对EEX真正写入的文本与分页无损性。"""
from pathlib import Path
import re, json, collections
from dialogue_layout import paginate, is_thought, recover


def verify_dialogue(b):
    chapter_stats=[];details=[];breaks=collections.Counter();force=[]
    for n in range(1,len(b.chapters)+1):
        entries=[];event='回首'
        source=(b.HERE/f'draft/ch{n}.md').read_text(encoding='utf-8')
        for line in source.splitlines():
            if line.startswith('[事件名]'):
                event=line.split(']',1)[1].strip()
            elif m:=re.match(r'^【([^】]+)】(.+)$',line):
                entries.append((event,m[1],m[2]))
            elif line.startswith('[旁白]'):
                entries.append((event,'',line.split(']',1)[1].strip()))
        if n==len(b.chapters):
            c=b.chapters[-1]
            entries.append(('待续提示','',f"{c['no']}「{c['title']}」至此。\n后续剧情尚在撰写，可在此保存进度。"))
        d=b.decode((b.OUT/f'RS/R_{n-1:02d}.EEX').read_bytes())
        actual=[i['args'][0]['value'] for i in d['instructions']
                if i['opcode']==0x14 and not(n==1 and 1<=i['block']<=17)]
        k=0;multi=thoughts=0
        for event,name,text in entries:
            pages=paginate(text,19 if name else 18)
            assert recover(pages)==text,(n,event,name,'分页原文丢失')
            shown=[]
            for p in pages:
                want=('&'+name+'\n' if name else '')+'\n'.join(p.lines)
                assert k<len(actual) and actual[k]==want,(n,event,name,k,'二进制对白不一致')
                encoded=actual[k];k+=1
                body=encoded.split('\n',1)[1] if name else encoded
                lines=body.splitlines()
                assert len(lines)<=3 and all(len(s.encode('gbk'))<=(38 if name else 36) for s in lines)
                flat=''.join(lines)
                if is_thought(text):
                    assert flat.startswith('（') and flat.endswith('）'),(n,event,name,'心声跨框括号缺失')
                    flat=flat[1:-1]
                shown.append(flat)
                breaks[p.break_kind]+=1
                if p.break_kind=='forced':
                    force.append({'回':n,'事件':event,'人物':name,'分框':p.raw})
            joined=''.join(shown)
            if is_thought(text):joined='（'+joined+'）'
            assert joined==text.replace('\n',''),(n,event,name,'显示文本漏字或重复')
            if len(pages)>1:
                multi+=1;thoughts+=is_thought(text)
                details.append({'回':n,'事件':event,'人物':name,'原文':text,
                                '分框':[{'正文':'\n'.join(p.lines),'断点':p.break_kind} for p in pages]})
        assert k==len(actual),(n,'存在源稿没有对应的对白框',k,len(actual))
        chapter_stats.append({'回':n,'源对白条数':len(entries)-(n==len(b.chapters)),'对白框':len(actual),'需分页条数':multi,'分页心理活动':thoughts})
    payload={'状态':'通过','范围':'第一至十三回新增正文及末回提示；原作接入17块不改',
             '分回':chapter_stats,'分框边界计数':dict(breaks),'无标点硬拆':force,
             '核验':['源稿与EEX逐框相符','显示正文逆向拼接无漏字、无重字','每框不超过三行','人物行宽不超38 GBK字节、旁白36','心理活动每框有完整外括号'],
             '全部分页对白':details}
    (b.HERE.parent/'对白分框核验.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    assert not force,('仍有无标点硬拆，须人工分句',force)
    return payload
