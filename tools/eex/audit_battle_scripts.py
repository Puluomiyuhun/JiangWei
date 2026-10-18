"""Read-only structural inventory of original Jiangwei/Lukang battle scripts.

Does not execute scripts, infer gameplay correctness, or write into source roots.
Uses the repository's existing EEX decoder; Python standard library only.
"""
from pathlib import Path
import argparse
import collections
import hashlib
import json

from eex_strategy_refs import decode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jiangwei-rs', type=Path, required=True)
    parser.add_argument('--lukang-rs', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    roots = {'姜维原作': args.jiangwei_rs.resolve(), '陆抗原作': args.lukang_rs.resolve()}
    out = args.out.resolve()
    for root in roots.values():
        if not root.is_dir():
            parser.error(f'Not a directory: {root}')
        if out == root or root in out.parents:
            parser.error('Output must be outside both original RS directories.')
    selected_r = {
        '姜维原作': {'R_03', 'R_04', 'R_19', 'R_20', 'R_22', 'R_31', 'R_32', 'R_90'},
        '陆抗原作': {'R_04', 'R_37'},
    }
    audit, catalog = [], []
    for origin, root in roots.items():
        for path in sorted(root.iterdir()):
            if not path.is_file() or path.suffix.upper() != '.EEX':
                continue
            stem = path.stem.upper()
            if not (stem.startswith('S_') or stem in selected_r[origin]):
                continue
            raw = path.read_bytes()
            result = decode(raw)
            audit.append({'来源': origin, '文件': path.name,
                          'sha256': hashlib.sha256(raw).hexdigest(),
                          '完整': result['complete'], '错误': result['errors']})
            if not result['complete'] or not stem.startswith('S_'):
                continue
            instructions = result['instructions']
            def take(op):
                return [[a['value'] for a in i['args']] for i in instructions if i['opcode'] == op]
            catalog.append({'来源': origin, '文件': path.name,
                            '场所': take(0x17), '背景指令': take(0x27),
                            '全局': take(0x45), '胜利文字': take(0x19),
                            '块数': max(i['block'] for i in instructions) + 1,
                            '跳转': take(0x11),
                            '指令计数': dict(collections.Counter(f"{i['opcode']:02X}" for i in instructions))})
    if not audit:
        parser.error('No matching scripts found.')
    out.mkdir(parents=True, exist_ok=True)
    for name, data in [('audit.json', audit), ('catalog.json', catalog)]:
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    complete = sum(row['完整'] for row in audit)
    print(f'Structurally decoded: {complete}/{len(audit)}; S inventory: {len(catalog)}')
    return 0 if complete == len(audit) else 1


if __name__ == '__main__':
    raise SystemExit(main())
