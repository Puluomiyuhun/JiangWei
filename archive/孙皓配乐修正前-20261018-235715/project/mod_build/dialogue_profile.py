"""只读统计源稿语量；台词行不等于游戏对话框，数字不作质量评分。"""
from pathlib import Path
import argparse
import json
import re

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = [
    ('R_05', '回想 重责大任'),
    ('R_18', '才女辛宪英'),
    ('R_24', '冲突'),
    ('R_26', '半年前　仇国论'),
    ('R_27', '陆抗的考量'),
    ('R_28', '避祸之道'),
    ('R_28', '翁婿相见'),
    ('R_45', '预言落空'),
]


def scenes(text):
    return {m.group(1).strip(): m.group(0) for m in re.finditer(
        r'^\[事件名\] ([^\n]+)\n.*?(?=^\[事件名\]|\Z)', text, re.M | re.S)}


def metrics(text):
    lines = [re.sub(r'\s+', '', body) for name, body in re.findall(
        r'^【([^】]+)】(.*)$', text, re.M) if name != '?']
    thoughts = [s for s in lines if s.startswith('（') and s.endswith('）')]
    count = len(lines)
    chars = sum(map(len, lines))
    return {
        '台词行': count, '字符': chars,
        '均长': round(chars / max(count, 1), 1),
        '括号行': len(thoughts),
        '括号行占比': round(100 * len(thoughts) / max(count, 1), 1),
        '括号字量占比': round(100 * sum(map(len, thoughts)) / max(chars, 1), 1),
    }


def profile():
    original = {}
    for file, event in SAMPLES:
        path = ROOT / f'references/姜维传原文/{file}.txt'
        body = scenes(path.read_text(encoding='utf-8'))[event]
        original[f'{file} {event}'] = metrics(body)
    chapters = {}
    for path in sorted((ROOT / 'project/mod_build/draft').glob('ch*.md'),
                       key=lambda p: int(p.stem[2:])):
        text = path.read_text(encoding='utf-8')
        chapters[path.stem] = {'整回': metrics(text), '逐场': {
            name: metrics(body) for name, body in scenes(text).items()}}
    return {
        '口径': '每个有名角色的【角色】源稿行算一条；去姓名及空白，计正文含标点和括号的字符数。排除【?】、旁白、地图、指令。纯全角括号行单计；需人工区别心声和动作。不是自动分框数，也不是汉字数。',
        '限制': '定向选取八个已精读原作场景，不代表全作均值。原作文本与新稿源行切法可能不同，均长仅作描述；信息内容和人物知情范围须人工判断。不设合格比例。',
        '原作八场': original, '当前各回': chapters,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, help='可选JSON输出；不指定则打印')
    args = parser.parse_args()
    data = json.dumps(profile(), ensure_ascii=False, indent=2) + '\n'
    if args.out:
        args.out.write_text(data, encoding='utf-8')
    else:
        print(data, end='')
