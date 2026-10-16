# -*- coding: utf-8 -*-
"""
解压 DATA.E5 的 section 5(策略/技能表 g_Table5, 0x44项×70字节文件记录),
忠实复刻 e5loader.c 的哈夫曼+LZSS 解压算法, 打印全部 68 条策略。
用法: python dump_e5_skills.py <Data.e5路径>
"""
import sys, io

def load(path):
    with open(path, "rb") as f:
        return f.read()

class BitReader:
    """MSB-first 位流, 底层按需从字节序列读取 (对应 E5_FillByteBuffer)"""
    def __init__(self, data, off):
        self.data = data
        self.pos = off
        self.bitbuf = 0
        self.bitcount = 0
    def read_bit(self):
        if self.bitcount == 0:
            if self.pos >= len(self.data):
                return -1
            self.bitbuf = self.data[self.pos]
            self.pos += 1
            self.bitcount = 8
        self.bitcount -= 1
        bit = (self.bitbuf & 0x80) >> 7
        self.bitbuf = (self.bitbuf << 1) & 0xff
        return bit
    def read_bits(self, n):
        v = 0
        for _ in range(n):
            b = self.read_bit()
            if b < 0: return -1
            v = v * 2 + b
        return v
    def read_symbol(self):
        # 对应 E5_ReadSymbol: 读位直到出现 0 位, 再读同样长度的补充位
        val = 0
        length = 0
        while True:
            b = self.read_bit()
            if b < 0: return -1
            val = val * 2 + b
            length += 1
            if (val & 1) == 0:
                break
        extra = self.read_bits(length)
        if extra < 0: return -1
        return val + extra

def decompress(data, file_off, uncomp_size, huff):
    br = BitReader(data, file_off)
    out = bytearray()
    while len(out) < uncomp_size:
        sym = br.read_symbol()
        if sym < 0:
            break
        if sym < 0x100:
            out.append(huff[sym])
        else:
            length2 = br.read_symbol()
            dist = sym - 0x100
            start = len(out) - dist
            for i in range(length2 + 3):
                out.append(out[start + i])
    return bytes(out[:uncomp_size])

def read_section(data, idx):
    huff = data[0x10:0x110]                       # 256 字节哈夫曼码表
    dir_off = 0x110 + idx * 12
    hdr = data[dir_off:dir_off + 12]
    raw = int.from_bytes(hdr[0:4], "big")
    unc = int.from_bytes(hdr[4:8], "big")
    foff = int.from_bytes(hdr[8:12], "big")
    if unc == raw:
        return data[foff:foff + unc]
    return decompress(data, foff, unc, huff)

# 策略分类(依据 battle.c / battle_ai.c 硬编码 ID 段)
def category(sid):
    if sid == 0x00: return "普通攻击"
    if 0x01 <= sid <= 0x15: return "计策攻击"
    if sid == 0x16: return "吸取MP"
    if sid in (0x1f, 0x20): return "弱化(命中/机动↓)"
    if 0x21 <= sid <= 0x24: return "计策攻击/阵型"
    if sid == 0x25: return "特攻兵种"
    if sid == 0x26: return "全回复HP(攻击类)"
    if 0x27 <= sid <= 0x2b: return "回复HP/增益"
    if 0x2c <= sid <= 0x2d: return "回复MP"
    if sid in (0x2e, 0x2f): return "状态/解异常"
    if sid == 0x39: return "混乱/魅惑"
    if 0x40 <= sid <= 0x43: return "特殊"
    return "-(其它/无AI)"

# 攻击系数(battle.c Battle_GetSkillCoeff)
def coeff(sid):
    t = {0:7,3:7,5:7,8:7,0xb:7,0xf:7,0x11:7,0x14:7,0x21:7,0x40:7,
         1:9,4:9,6:9,0x10:9,0x12:9,
         2:5,7:5,0xa:5,0xd:5,0x16:5,0x23:5,
         0xc:4,0x22:4,
         0xe:2,0x24:2,
         0x13:12,0x26:12,
         0x41:10}
    return t.get(sid, 0)

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "Data.e5"
    data = load(path)
    sec = read_section(data, 5)
    STRIDE = 70   # 文件记录 = 10(名) +1(skip) +6 +53 = 70
    n = len(sec) // STRIDE
    print("section5 长度=%d, 记录数=%d (每条%d字节)" % (len(sec), n, STRIDE))
    print("=" * 78)
    for i in range(0x44):
        base = i * STRIDE
        if base + STRIDE > len(sec):
            break
        rec = sec[base:base + STRIDE]
        raw_name = rec[0:10]
        try:
            name = raw_name.split(b"\x00")[0].decode("gbk", errors="replace").strip()
        except Exception:
            name = raw_name.hex()
        b11, b12, b13, b14, b15, b16 = rec[11], rec[12], rec[13], rec[14], rec[15], rec[16]
        # b13=AoE范围形状(0xff=单体) b14=目标枚举形状 b15=MP消耗
        aoe = "单体" if b13 == 0xff else ("形状%#x" % b13)
        print("ID %#04x  %-8s | 类型:%-14s 系数:%-2d MP:%-3d %s 目标形状:%#x" % (
            i, name, category(i), coeff(i), b15, aoe, b14))

if __name__ == "__main__":
    main()
