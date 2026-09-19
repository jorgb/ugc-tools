import unittest

from convert.xpj import banking, mapping
from convert.xpj.model import PadSlot


class _FakePad:
    name = "sample"


def _pad(letter, number):
    return PadSlot(_FakePad(), letter, number, f"{letter}{number:02d}.wav", "unused.SMP", None)


def _bank(letter, count=16):
    return [_pad(letter, number) for number in range(1, count + 1)]


def _by_name(pads):
    return {p.sp404_name: p for p in pads}


class TestXPJBanking(unittest.TestCase):

    def test_banks_a_to_e_keep_their_position(self):
        """Verify SP404 banks A-E map straight onto MPC banks A-E, with the pad rows flipped."""
        pads = [p for letter in "ACE" for p in _bank(letter, 3)]
        banking.allocate(pads, set())

        slots = {p.sp404_name: p.slot for p in pads}
        self.assertEqual(slots["A01"], 12)
        self.assertEqual(slots["A03"], 14)
        self.assertEqual(slots["C01"], 44)
        self.assertEqual(slots["E03"], 78)

    def test_bank_slot_flips_the_rows_and_keeps_the_columns(self):
        """Verify SP404 pad 1 (top-left) becomes MPC pad 13 (top-left), and so on for the grid."""
        self.assertEqual([banking.bank_slot(n) for n in range(1, 17)],
                         [12, 13, 14, 15, 8, 9, 10, 11, 4, 5, 6, 7, 0, 1, 2, 3])
        self.assertEqual(sorted(banking.bank_slot(n) for n in range(1, 17)), list(range(16)))

    def test_every_pad_sits_in_the_same_grid_spot_as_on_the_sp404(self):
        """Verify a whole bank lands on the MPC pad in the same row from the top and column."""
        pads = _bank("B")
        banking.allocate(pads, set())

        for pad in pads:
            sp_row, sp_column = divmod(pad.local_number - 1, 4)  # row 0 is the top row
            bank, index = divmod(pad.slot, banking.PADS_PER_BANK)
            mpc_row_from_bottom, mpc_column = divmod(index, 4)
            self.assertEqual(bank, 1)
            self.assertEqual((3 - mpc_row_from_bottom, mpc_column), (sp_row, sp_column), pad.sp404_name)

    def test_played_alternate_bank_takes_the_next_free_mpc_bank(self):
        """Verify a played bank F moves whole into MPC bank F when A-E are all in use."""
        pads = [p for letter in "ABCDE" for p in _bank(letter, 2)] + _bank("F")
        named = _by_name(pads)
        allocation = banking.allocate(pads, {named["F04"]})

        self.assertEqual(allocation.bank_map, {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5})
        self.assertEqual([named[f"F{n:02d}"].slot for n in (1, 4, 16)], [92, 95, 83])

    def test_played_alternate_bank_fills_a_gap_left_by_an_empty_bank(self):
        """Verify with bank C empty, a played bank F takes MPC bank C, not F."""
        pads = [p for letter in "ABDE" for p in _bank(letter, 1)] + _bank("F")
        named = _by_name(pads)
        allocation = banking.allocate(pads, {named["F02"]})

        self.assertEqual(allocation.bank_map["F"], 2)
        self.assertEqual(named["F02"].slot, 2 * 16 + 13)

    def test_alternate_banks_relocate_in_order(self):
        """Verify banks F, G, H, I, J take the free MPC banks in that order."""
        pads = [p for letter in "AB" for p in _bank(letter, 1)]
        played = set()
        for letter in "FGHIJ":
            bank = _bank(letter, 1)
            pads += bank
            played.update(bank)
        allocation = banking.allocate(pads, played)

        self.assertEqual([allocation.bank_map[l] for l in "FGHIJ"], [2, 3, 4, 5, 6])

    def test_sequenced_pad_takes_lowest_free_slot_when_no_bank_is_free(self):
        """Verify with no free MPC bank, a played pad from bank I goes to the first free slot."""
        pads = [p for letter in "ABCDEFGH" for p in _bank(letter, 1)] + _bank("I")
        named = _by_name(pads)
        # F, G and H are played too, so they take MPC banks F-H before bank I is placed
        allocation = banking.allocate(pads, {named["F01"], named["G01"], named["H01"], named["I03"]})

        self.assertEqual(named["I03"].slot, 0)  # MPC pad A01, the first hole (A01 sits at slot 12)
        self.assertEqual(allocation.moved, [named["I03"]])
        self.assertEqual(allocation.evicted, [])

    def test_unplayed_pads_fill_free_slots_and_only_overflow_goes_unmapped(self):
        """Verify pads nothing plays still get any free slot, and are unmapped only once the MPC is full."""
        # 80 pads in A-E (in place) + F, G, H played (48) = 128: the MPC is full, I and J don't fit
        full = [p for letter in "ABCDEFGH" for p in _bank(letter)] + _bank("I", 2) + _bank("J", 2)
        named = _by_name(full)
        banking.allocate(full, {named["F01"], named["G01"], named["H01"]})
        self.assertTrue(all(p.slot is None for p in full if p.bank_letter in "IJ"))

        # bank C has only 3 pads, so 13 slots are free: unplayed bank J's 13 pads land in them, in SP404 order
        roomy = [p for letter in "ABDEFGH" for p in _bank(letter)] + _bank("C", 3) + _bank("J", 13)
        named = _by_name(roomy)
        banking.allocate(roomy, {named["F01"], named["G01"], named["H01"]})
        # C01-C03 sit at slots 44-46, so the first free slots are 32, 33, 34, 35
        self.assertEqual([named[f"J{n:02d}"].slot for n in (1, 2, 3, 4)], [32, 33, 34, 35])
        self.assertTrue(all(p.slot is not None for p in roomy))

    def test_moved_pad_notes_follow_the_new_slot(self):
        """Verify a moved pad's note is the note of the slot it landed on."""
        pads = [p for letter in "ABCDEFGH" for p in _bank(letter, 1)] + _bank("I")
        named = _by_name(pads)
        banking.allocate(pads, {named["F01"], named["G01"], named["H01"], named["I03"]})

        self.assertEqual(named["I03"].note, mapping.slot_note(0))
        self.assertEqual(named["I03"].note, 36)

    def test_full_program_evicts_the_highest_unplayed_pad(self):
        """Verify with all 128 slots taken, a played pad displaces the highest pad no pattern plays."""
        pads = [p for letter in "ABCDEFGH" for p in _bank(letter)] + _bank("I")
        named = _by_name(pads)
        played = {named["F01"], named["G01"], named["H01"], named["H04"], named["I05"]}
        allocation = banking.allocate(pads, played)

        # H04 holds slot 127 but is played, so it stays; H03 (slot 126) is the highest unplayed pad
        self.assertEqual(named["I05"].slot, 126)
        self.assertEqual(allocation.evicted, [named["H03"]])
        self.assertIsNone(named["H03"].slot)
        self.assertEqual(named["H04"].slot, 127)

    def test_eviction_never_touches_a_played_pad(self):
        """Verify pads that patterns play are never evicted, however high their slot."""
        pads = [p for letter in "ABCDEFGH" for p in _bank(letter)] + _bank("I")
        named = _by_name(pads)
        played = {named[f"H{n:02d}"] for n in range(1, 17)} | {named["F01"], named["G01"], named["I01"]}
        allocation = banking.allocate(pads, played)

        self.assertTrue(all(p.slot is not None for p in played))
        self.assertEqual(allocation.evicted, [named["G04"]])
        self.assertEqual(named["I01"].slot, 111)

    def test_error_when_every_pad_is_played_and_nothing_fits(self):
        """Verify a ValueError when 128 played pads fill the MPC and another one needs a slot."""
        pads = [p for letter in "ABCDEFGH" for p in _bank(letter)] + _bank("I", 1)

        with self.assertRaises(ValueError) as context:
            banking.allocate(pads, set(pads))
        self.assertIn("I01", str(context.exception))

    def test_unplayed_banks_only_get_whole_free_banks(self):
        """Verify unplayed banks fill leftover free banks whole and the rest stay unmapped."""
        pads = [p for letter in "ABCDE" for p in _bank(letter)]
        for letter in "FGHIJ":
            pads += _bank(letter)
        named = _by_name(pads)
        allocation = banking.allocate(pads, {named["F01"]})

        self.assertEqual(allocation.bank_map, {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4,
                                               "F": 5, "G": 6, "H": 7})
        self.assertTrue(all(p.slot is None for p in pads if p.bank_letter in "IJ"))
        self.assertTrue(all(p.slot is not None for p in pads if p.bank_letter in "ABCDEFGH"))

    def test_played_banks_are_placed_before_unplayed_banks(self):
        """Verify a played bank J gets a free MPC bank ahead of an unplayed bank F."""
        pads = [p for letter in "ABCDE" for p in _bank(letter)] + _bank("F") + _bank("J")
        named = _by_name(pads)
        allocation = banking.allocate(pads, {named["J01"]})

        self.assertEqual(allocation.bank_map["J"], 5)
        self.assertEqual(allocation.bank_map["F"], 6)

    def test_every_assigned_slot_is_unique_and_in_range(self):
        """Verify no two pads share a slot, whatever the mix of banks."""
        pads = [p for letter in "ABCDEFGHIJ" for p in _bank(letter)]
        banking.allocate(pads, {p for p in pads if p.local_number == 1})

        slots = [p.slot for p in pads if p.slot is not None]
        self.assertEqual(len(slots), len(set(slots)))
        self.assertTrue(all(0 <= s < banking.MPC_PAD_COUNT for s in slots))
        self.assertEqual(len(slots), banking.MPC_PAD_COUNT)


if __name__ == '__main__':
    unittest.main()
