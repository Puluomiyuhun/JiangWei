# -*- coding: utf-8 -*-
"""姜维传 6.5 EEX 剧本文本抽取器。

EEX 结构(见 1-工程源码/src/script_vm.c ScriptLoadResource):
  +0  "EEX\0"   +4 ver(1)  +5 sub(2) -> 从 +6 起解析 {short type, short len, data} 链, type0 结束
  链尾 = tableOff, 此处为块(Section)偏移表 DWORD[], 首项值即表尾, 块数 = (first-tableOff)/4
  指令 = opcode(WORD) + 若干参数; 参数 = tag(WORD) + 值(tag4=DWORD, tag5=GBK\0串, 其它=WORD)
  0x01(子事件) 后接条件指令, 再接 len(WORD) + 子体, 子体以 0x00 结束。
这里按"opcode + 期望 tag 序列"做模式匹配扫描, 只抽剧情相关指令。
"""
import struct, sys, os, re

W = lambda b, o: struct.unpack_from('<H', b, o)[0]
D = lambda b, o: struct.unpack_from('<I', b, o)[0]

# opcode -> (名称, 参数 tag 序列)
OPS = {
    0x02: ('注释', [5]),
    0x11: ('剧本跳转', [0x37]),
    0x12: ('选择框', [5, 2]),
    0x13: ('选项', [4]),
    0x14: ('对话', [5]),
    0x15: ('对话2', [2, 2, 5]),
    0x16: ('信息', [5]),
    0x17: ('场所', [5]),
    0x18: ('事件名', [5]),
    0x19: ('胜利条件', [5]),
    0x2c: ('地图文字', [5, 0x26, 0x26, 0x26]),
    0x63: ('单挑对话', [0x26, 5, 0x26]),
    0x67: ('章名', [4, 5]),
    0x69: ('旁白', [5]),
}


def gbk(bs):
    return bs.decode('gbk', errors='replace')


def try_parse(b, o, tags):
    vals = []
    for t in tags:
        if o + 2 > len(b) or W(b, o) != t:
            return None
        o += 2
        if t == 4:
            if o + 4 > len(b):
                return None
            vals.append(D(b, o)); o += 4
        elif t == 5:
            e = b.find(b'\0', o)
            if e < 0 or e - o > 4000:
                return None
            raw = b[o:e]
            try:
                s = raw.decode('gbk')
            except UnicodeDecodeError:
                return None
            vals.append(s); o = e + 1
        else:
            if o + 2 > len(b):
                return None
            vals.append(W(b, o)); o += 2
    return vals, o


def sections(b):
    assert b[:4] == b'EEX\0', 'bad magic'
    o = 6
    if b[5] == 0:
        to = 0x10
    else:
        while True:
            t, l = struct.unpack_from('<hH', b, o)
            o += 4 + l
            if t == 0:
                break
        to = o
    first = D(b, to)
    n = (first - to) // 4
    offs = [D(b, to + 4 * i) for i in range(n)] + [len(b)]
    return [(offs[i], offs[i + 1]) for i in range(n)]


def extract(path):
    b = open(path, 'rb').read()
    out = []
    for si, (s, e) in enumerate(sections(b)):
        out.append(('SECTION', si, None))
        o = s
        while o < e - 2:
            op = W(b, o)
            spec = OPS.get(op)
            if spec:
                r = try_parse(b, o + 2, spec[1])
                if r:
                    vals, no = r
                    out.append((spec[0], o, vals))
                    o = no
                    continue
            o += 1
    return out


def fmt_text(s):
    s = s.replace('\r', '')
    return s


def render(path, show_comment=False):
    lines = []
    for kind, off, vals in extract(path):
        if kind == 'SECTION':
            lines.append(f'\n---- Section {off} ----')
            continue
        if kind == '注释' and not show_comment:
            continue
        if kind in ('对话',):
            txt = fmt_text(vals[0])
            # 一条可含多段 "&姓名\n台词"，以 "\n&" 分隔
            for blk in re.split(r'\n(?=&)', txt):
                if blk.startswith('&'):
                    name, _, body = blk[1:].partition('\n')
                    lines.append(f'【{name}】{body.replace(chr(10), " ")}')
                else:
                    lines.append(f'【?】{blk.replace(chr(10), " ")}')
        elif kind == '对话2':
            lines.append(f'【#{vals[0]}→#{vals[1]}】{fmt_text(vals[2]).replace(chr(10), " ")}')
        elif kind == '单挑对话':
            lines.append(f'【单挑:{vals[0]}】{fmt_text(vals[1]).replace(chr(10), " ")}')
        elif kind == '章名':
            lines.append(f'==== 第{vals[0]}章 {vals[1]} ====')
        elif kind == '选项':
            lines.append(f'  <case {vals[0]}>')
        elif kind == '剧本跳转':
            lines.append(f'>> 剧本跳转 -> {vals[0]}')
        else:
            lines.append(f'[{kind}] ' + ' | '.join(fmt_text(str(v)).replace(chr(10), ' / ') for v in vals))
    return '\n'.join(lines)


if __name__ == '__main__':
    rs = sys.argv[1]
    dst = sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    names = sorted(f for f in os.listdir(rs) if f.lower().endswith('.eex'))
    for n in names:
        try:
            txt = render(os.path.join(rs, n), show_comment='-c' in sys.argv)
        except Exception as ex:
            txt = f'!! parse error {ex}'
        open(os.path.join(dst, os.path.splitext(n)[0] + '.txt'), 'w', encoding='utf-8').write(f'# {n}\n' + txt)
    print('done', len(names))
