"""对白先按句意分框，再排每框的行；不以三行截断下一句。

人物名不计入正文三行。人物框每行19个全角字，旁白18个。
一整句过长才在分句标点处分框；没有标点才强制断开并记入核验。
整条心理活动分页时，每框补齐外层括号，避免后框被误认成出口的话。
"""
from typing import NamedTuple
from functools import lru_cache

CLOSING = '，。！？；：、）】》〉」』”’…％'
OPENING = '（【《〈「『“‘'
QUOTE_END = '）】》〉」』”’'


class Page(NamedTuple):
    raw: str
    lines: tuple[str, ...]
    break_kind: str
    thought: bool


def gbk_len(text):
    return len(text.encode('gbk'))


def wrap(text, width):
    """保留既有行宽与禁则：行首避标点，行尾避开括号。"""
    limit = width * 2
    if limit < 8:
        raise ValueError('本排版器只用于游戏正文宽度')
    lines = []
    for paragraph in text.split('\n'):
        while paragraph:
            size = cut = 0
            for c in paragraph:
                cw = gbk_len(c)
                if size + cw > limit:
                    break
                size += cw
                cut += 1
            if cut < len(paragraph):
                candidates = [k + 1 for k in range(cut)
                              if paragraph[k] in '，。！？；、…'
                              and gbk_len(paragraph[:k + 1]) >= limit - 8]
                if candidates:
                    cut = candidates[-1]
                while cut > 1 and (paragraph[cut] in CLOSING or paragraph[cut - 1] in OPENING):
                    cut -= 1
            lines.append(paragraph[:cut])
            paragraph = paragraph[cut:]
    # 不让最后一行只剩一两个字；挪动仅发生在同一框内。
    if len(lines) >= 2 and gbk_len(lines[-1]) <= 8:
        a, b = lines[-2:]
        k = len(a) - 1
        while k > 1 and gbk_len(a[k:] + b) < 12:
            k -= 1
        while k > 1 and (a[k] in CLOSING or a[k - 1] in OPENING):
            k -= 1
        if k > 0 and gbk_len(a[k:] + b) <= limit:
            lines[-2:] = [a[:k], a[k:] + b]
    return lines


def is_thought(text):
    if not (text.startswith('（') and text.endswith('）')):
        return False
    depth = 0
    for i, c in enumerate(text):
        depth += (c == '（') - (c == '）')
        if depth < 0 or (depth == 0 and i != len(text) - 1):
            return False
    return depth == 0


def boundaries(text, marks):
    """标点后的引号、括号跟前句走，不单独掉到下一框。"""
    cuts = set()
    for i, c in enumerate(text):
        if c not in marks:
            continue
        k = i + 1
        while k < len(text) and text[k] in QUOTE_END + '。！？…':
            k += 1
        if k == len(text) or text[k] not in CLOSING:
            cuts.add(k)
    return sorted(cuts)


def paginate(text, width=19, rows=3):
    if not text:
        return []
    thought = is_thought(text)
    body = text[1:-1] if thought else text

    def display(piece):
        return tuple(wrap('（' + piece + '）' if thought else piece, width))

    def fits(piece):
        lines = display(piece)
        return len(lines) <= rows and all(gbk_len(s) <= width * 2 for s in lines)

    @lru_cache(maxsize=None)
    def solve(start):
        rest = body[start:]
        if fits(rest):
            return (Page(rest, display(rest), 'end', thought),)
        # 句号、问号、叹号优先，不为填满第三行而挪入下句开头。
        for marks, kind in [('。！？\n', 'sentence'), ('；，：', 'clause')]:
            candidates = [p for p in boundaries(rest, marks) if fits(rest[:p])]
            if candidates:
                break
        else:
            # 无可用标点的超长句，保留所有字；必须在专项报告中暴露。
            candidates = [p for p in range(1, min(len(rest), width * rows * 2) + 1)
                          if rest[p - 1] not in OPENING
                          and (p == len(rest) or rest[p] not in CLOSING)
                          and fits(rest[:p])]
            if not candidates:
                raise ValueError('无法在给定框宽内保留禁则：' + rest)
            kind = 'forced'
        alternatives = [(Page(rest[:cut], display(rest[:cut]), kind, thought),) + solve(start + cut)
                        for cut in candidates]
        # 在不增加框数、仍以句末为界的方案里，避免前框塞满、后框只剩很短一句。
        capacity = width * rows * 2 - (4 if thought else 0)
        return min(alternatives, key=lambda seq: (len(seq), sum((capacity-gbk_len(p.raw))**2 for p in seq)))

    return list(solve(0))


def recover(pages):
    """复核分页前后原文：仅撤销重复添加的心声外括号。"""
    if not pages:
        return ''
    body = ''.join(p.raw for p in pages)
    return '（' + body + '）' if pages[0].thought else body
