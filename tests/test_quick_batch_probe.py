"""Quick Batch probe: OCR guesses -> stocked batches (exact, OCR look-alike, one character off).

Uses an in-memory batch index (no database). Guesses are real OCR outputs from the phone scan log.
"""
import time
import unittest

import crud

STOCKED = ["G6445066", "NL2533", "1260070", "5L80836", "28027174", "6SA0133", "AC826005", "112025"]


class QuickBatchProbeTest(unittest.TestCase):
    def setUp(self):
        index = {"exact": {b: [i] for i, b in enumerate(STOCKED)}, "canon": {}}
        for b in STOCKED:
            index["canon"].setdefault(crud._canonical_batch(b), set()).add(b)
        crud._BATCH_INDEX_CACHE[999] = (time.time(), index)

    def tearDown(self):
        crud._BATCH_INDEX_CACHE.pop(999, None)

    def probe(self, *guesses):
        return crud.quick_batch_probe(None, 999, list(guesses))

    def test_exact(self):
        self.assertEqual(self.probe("NL2533")["exact"], ["NL2533"])

    def test_lookalike(self):
        self.assertEqual(self.probe("C6445066")["lookalike"], ["G6445066"])
        self.assertEqual(self.probe("126D070")["lookalike"], ["1260070"])

    def test_one_character_off(self):
        self.assertEqual(self.probe("2027174")["near"], ["28027174"])   # digit lost
        self.assertEqual(self.probe("G644506")["near"], ["G6445066"])   # last digit lost
        self.assertEqual(self.probe("ONL2533")["near"], ["NL2533"])     # extra leading letter
        self.assertEqual(self.probe("6SA033")["near"], ["6SA0133"])     # digit lost

    def test_near_not_used_when_exact_or_lookalike_found(self):
        self.assertEqual(self.probe("NL2533", "2027174")["near"], [])

    def test_leading_characters_lost_gives_a_tail_hit_only_when_nothing_closer_exists(self):
        self.assertEqual(self.probe("U27174")["tail"], ["28027174"])       # "28" lost and the next character misread
        self.assertEqual(self.probe("027174")["tail"], ["28027174"])
        self.assertEqual(self.probe("2027174")["tail"], [])                # a one-character-off read is "near", not "tail"
        self.assertEqual(self.probe("7174")["tail"], [])                   # too short to mean anything
        self.assertEqual(self.probe("U27174", "NL2533")["tail"], [])       # an exact hit wins

    def test_tail_never_returns_a_batch_the_read_does_not_end_like(self):
        self.assertEqual(self.probe("U27175")["tail"], [])

    def test_junk_does_not_match(self):
        r = self.probe("202873", "155.96", "XYZ999")
        self.assertEqual((r["exact"], r["lookalike"], r["near"]), ([], [], []))

    def test_batch_inside_glued_ocr_text(self):
        def contained(t):
            return crud.quick_batch_probe(None, 999, [], text=t)["contained"]
        # Real OCR lines from the phone log for the NL2533 strip, glued differently each time.
        self.assertEqual(contained("Bto. NL2533FD.11{20EXP.10. / MR R. RS, 8"), ["NL2533"])
        self.assertEqual(contained("325 RFL / Cals / g / ONL2533 FD.L1/2025EXP,10/zc"), ["NL2533"])
        self.assertEqual(contained("BNQ126 DO70 / MEDMAY.2026"), ["1260070"])

    def test_dates_and_prices_never_count_as_contained(self):
        # "112025" is stocked (6 digits) but must not match the date 11/2025.
        r = crud.quick_batch_probe(None, 999, [], text="MFG.DATE 11/2025 PER 10 TABS EXP 11/2027 Rs.155.96")
        self.assertEqual(r["contained"], [])

    def test_within_one_edit(self):
        self.assertTrue(crud._within_one_edit("ABC123", "ABC1234"))
        self.assertTrue(crud._within_one_edit("ABC123", "ABD123"))
        self.assertFalse(crud._within_one_edit("ABC123", "ABD124"))


if __name__ == "__main__":
    unittest.main()
