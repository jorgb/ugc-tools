"""
Assigns SP404mk2 pads to the 128 pads (8 banks of 16) of one MPC drum
program. The SP404 has 10 banks, 160 pads; the MPC has room for 128, so
not every pad fits. Pads played by a pattern always come first.
See convert/xpj/DESIGN.md section 5.6.
"""

from sp404.padconf import BANKS

MPC_BANK_COUNT = 8
PADS_PER_BANK = 16
MPC_PAD_COUNT = MPC_BANK_COUNT * PADS_PER_BANK

# SP404 banks A-E are the five bank buttons; F-J are the same buttons
# pressed a second time
PRIMARY_BANK_COUNT = 5


class Allocation:
    """What banking.allocate() did, for logging."""
    def __init__(self):
        # SP404 bank letter -> MPC bank index (0-7), for banks placed whole
        self.bank_map = {}
        # pads placed one by one because no whole bank was free
        self.moved = []
        # pads that lost their slot to a pad played by a pattern
        self.evicted = []


def bank_letter(mpc_bank_index):
    return BANKS[mpc_bank_index]


def allocate(pads, sequenced):
    """Sets pad.slot (0..127, or None) on every pad in `pads`.

    `sequenced` is the set of pads that any pattern plays. In order:

    1. Banks A-E keep their position (A -> MPC bank A ... E -> MPC bank E).
    2. Each of banks F-J that has a sequenced pad moves whole into the
       lowest MPC bank that is still completely free.
    3. When no whole bank is free, each remaining sequenced pad takes the
       lowest free slot (its notes in the sequence follow it). With no free
       slot, it takes the highest slot held by a pad no pattern plays; that
       pad ends up unmapped. If every pad is played, that is an error.
    4. Banks F-J that no pattern plays move whole into any bank still free.
    5. Every pad still without a slot fills the lowest remaining free slot,
       in SP404 order (nothing is evicted for these).

    Pads that still have no slot - the MPC is full - keep slot None.
    Returns an Allocation.
    """
    owner = [None] * MPC_PAD_COUNT
    allocation = Allocation()

    def place(pad, slot):
        owner[slot] = pad
        pad.slot = slot

    def free_bank():
        for bank in range(MPC_BANK_COUNT):
            if all(owner[bank * PADS_PER_BANK + i] is None for i in range(PADS_PER_BANK)):
                return bank
        return None

    def place_whole_bank(letter, bank_pads, mpc_bank):
        for pad in bank_pads:
            place(pad, mpc_bank * PADS_PER_BANK + pad.local_number - 1)
        allocation.bank_map[letter] = mpc_bank

    def take_slot(pad):
        for slot in range(MPC_PAD_COUNT):
            if owner[slot] is None:
                place(pad, slot)
                return
        for slot in reversed(range(MPC_PAD_COUNT)):
            if owner[slot] not in sequenced:
                evicted = owner[slot]
                evicted.slot = None
                allocation.evicted.append(evicted)
                place(pad, slot)
                return
        raise ValueError(
            f"No room for pad {pad.sp404_name} ('{pad.pad.name}'): all {MPC_PAD_COUNT} MPC pads "
            f"are taken by samples that patterns play. Remove or merge some patterns' pads.")

    banks = {}
    for pad in pads:
        banks.setdefault(pad.bank_letter, []).append(pad)
    letters = sorted(banks, key=BANKS.index)

    for letter in letters:
        if BANKS.index(letter) < PRIMARY_BANK_COUNT:
            place_whole_bank(letter, banks[letter], BANKS.index(letter))

    alternates = [l for l in letters if BANKS.index(l) >= PRIMARY_BANK_COUNT]
    played = [l for l in alternates if any(p in sequenced for p in banks[l])]
    unplayed = [l for l in alternates if l not in played]

    leftover = []
    for letter in played:
        target = free_bank()
        if target is None:
            leftover.extend(p for p in banks[letter] if p in sequenced)
        else:
            place_whole_bank(letter, banks[letter], target)

    for pad in leftover:
        take_slot(pad)
        allocation.moved.append(pad)

    for letter in unplayed:
        target = free_bank()
        if target is not None:
            place_whole_bank(letter, banks[letter], target)

    for letter in letters:
        for pad in banks[letter]:
            if pad.slot is None and pad not in allocation.evicted:
                free = next((slot for slot in range(MPC_PAD_COUNT) if owner[slot] is None), None)
                if free is None:
                    return allocation
                place(pad, free)

    return allocation
