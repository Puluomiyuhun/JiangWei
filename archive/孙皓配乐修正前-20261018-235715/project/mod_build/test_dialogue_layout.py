"""分页回归：指定刘禅断点、超长单句、引号、心声、GBK混排及无字损失。"""
import unittest
from dialogue_layout import paginate, recover, is_thought, gbk_len

LIUSHAN = '歇不着。皇后，朕出降那天，邓艾给朕解了绑，烧了棺木，又承制拜朕做骠骑将军。朕那时候想，总算睡得着觉了。结果一个月不到，城外又点起火来。'


class DialogueLayoutTests(unittest.TestCase):
    def check_roundtrip(self, text, width=19):
        pages = paginate(text, width)
        self.assertEqual(recover(pages), text)
        shown = []
        for page in pages:
            self.assertLessEqual(len(page.lines), 3)
            self.assertTrue(all(gbk_len(line) <= width * 2 for line in page.lines))
            flat = ''.join(page.lines)
            if is_thought(text):
                self.assertTrue(flat.startswith('（') and flat.endswith('）'))
                shown.append(flat[1:-1])
            else:
                shown.append(flat)
        shown = ''.join(shown)
        self.assertEqual(('（'+shown+'）' if is_thought(text) else shown), text.replace('\n',''))
        return pages

    def test_requested_liushan_split(self):
        pages = self.check_roundtrip(LIUSHAN)
        self.assertEqual([p.raw for p in pages], [
            '歇不着。皇后，朕出降那天，邓艾给朕解了绑，烧了棺木，又承制拜朕做骠骑将军。',
            '朕那时候想，总算睡得着觉了。结果一个月不到，城外又点起火来。'])

    def test_short_reply_stays_single(self):
        self.assertEqual(len(self.check_roundtrip('……好。')),1)

    def test_long_sentence_uses_clause(self):
        text='亲兵已经回到城外报信，'+('各营还在等自己的将军回来，'*8)+'先不要攻门。'
        pages=self.check_roundtrip(text)
        self.assertTrue(any(p.break_kind=='clause' for p in pages))
        self.assertFalse(any(p.break_kind=='forced' for p in pages))

    def test_unpunctuated_text_exposes_forced_split(self):
        pages=self.check_roundtrip('军'*200)
        self.assertTrue(any(p.break_kind=='forced' for p in pages))

    def test_quotes_follow_preceding_sentence(self):
        text='他写道：「各营先留在原处。伤兵准许出营，交给沿途驻军接应。」我得等自己的亲兵回来。'+LIUSHAN
        pages=self.check_roundtrip(text)
        self.assertTrue(all(not p.raw.startswith('」') for p in pages))

    def test_thought_each_page_has_brackets(self):
        pages=self.check_roundtrip('（'+LIUSHAN+'）')
        self.assertGreater(len(pages),1)

    def test_parenthetical_action_is_not_full_thought(self):
        text='（转身）'+LIUSHAN
        self.assertFalse(is_thought(text))
        self.check_roundtrip(text)

    def test_mixed_gbk_and_explicit_linebreaks(self):
        self.check_roundtrip('这是CD 101，编号从0算起。'+LIUSHAN,18)
        self.check_roundtrip('第十二回至此。\n后续剧情尚在撰写，可在此保存进度。',18)

    def test_width_edges_and_nested_thought(self):
        for count in range(1,90):
            with self.subTest(count=count):
                self.check_roundtrip('（'+('兵'*count)+'。还要等「军报」。）')


if __name__=='__main__':
    unittest.main()
