import struct
from . import spread as spr
from enum import IntEnum

BANKS = "ABCDEFGHIJ"
EMPTY_MARKER = 0xffffffff

Bank = IntEnum(
    'Bank',
    'NONE A B C D E F G H I J',
    start = 0
)

class BusFX(IntEnum):
    DRY = 0
    BUS_1 = 1
    BUS_2 = 2


class Chromatic(IntEnum):
    MONO = 0
    LEGATO = 1
    POLY = 2

    @staticmethod
    def parse(value):
        if value & 0x10 != 0:
            return Chromatic.POLY
        if value & 0x08 != 0:
            return Chromatic.LEGATO
        return Chromatic.MONO


class TrigMode(IntEnum):
    NORMAL = 0
    ONE_SHOT = 1
    LOOP = 2
    FIXED_VELOCITY = 3

    @staticmethod
    def parse(loop_mode, trig_mode):
        values = []
        if loop_mode == 0x7FFFFFFF:
            values.append(TrigMode.LOOP)
        if trig_mode & 0x00000020 != 0:
            values.append(TrigMode.ONE_SHOT)
        if trig_mode & 0x00000001 != 0:
            values.append(TrigMode.FIXED_VELOCITY)
        if len(values) == 0:
            values.append(TrigMode.NORMAL)

        return values


class PlayMode(IntEnum):
    FORWARD = 0
    REVERSE = 1
    FWD_PINGPONG = 3
    REV_PINGPONG = 4

    @staticmethod
    def parse(play_mode):
        if play_mode == 0x00000001:
            return PlayMode.REVERSE
        if play_mode == 0x00000002:
            return PlayMode.FWD_PINGPONG
        if play_mode == 0x00000003:
            return PlayMode.REV_PINGPONG
        return PlayMode.FORWARD

class Pad:
    """ Pad information serialized from a 172 bytes buffer"""
    def __init__(self, pad_nr, buf):
        #print(pad_nr)
        #hexdump(buf)
        self.name = None
        self.markers = None
        self.pad_nr = pad_nr
        # verified in sp404 app, sample start and end match
        self.sample_start = int((spr.read_long_b(buf[4:8]) - 0x200) / 4)
        self.sample_end = int((spr.read_long_b(buf[8:12]) - 0x200) / 4)
        self.vol = spr.read_long_b(buf[12:16]) & 0xFF
        self.gate = spr.read_long_b(buf[16:20]) == 0x0001
        self.mute_group = Bank(spr.read_long_b(buf[28:32]) & 0x0F)
        self.pad_link = Bank(spr.read_long_b(buf[76:80]) & 0x0F)
        self.bpm_sync = spr.read_long_b(buf[32:36]) == 0x0001
        self.bpm = spr.read_long_b(buf[36:40]) / 100
        self.loop_start = int((spr.read_long_b(buf[44:48]) - 0x200) / 4)
        self.play_mode = PlayMode.parse(spr.read_long_b(buf[60:64]))
        self.trig_mode = TrigMode.parse(spr.read_long_b(buf[20:24]), spr.read_long_b(buf[40:44]))
        self.bus_fx = BusFX(spr.read_long_b(buf[80:84]) & 0x0F)
        # TODO: Roll not yet implemented
        self.chromatic = Chromatic.parse(spr.read_long_b(buf[40:44]))
        self.pitch_perc = spr.read_long_b(buf[64:68]) / 100


class Project:
    def __init__(self, file_path):
        # these are filled in later
        self.project_name = None
        self.pads = None
        self.bank_bpms = None
        self._read(file_path)

    def _read(self, file_path):
        with open(file_path, 'rb') as f:
            if struct.unpack('4s', f.read(4))[0] != b"RFPD":
                raise ValueError('Invalid PADCONF file')

            f.seek(0x40)
            self.bank_bpms = {}
            for bank in BANKS:
                self.bank_bpms[bank] = spr.read_long(f) / 200

            f.seek(0x80)
            self.project_name = spr.read_string(f, 31).rstrip()

            f.seek(0xa0)
            # pads are 16 pads times 10 banks [A/F .. E/J]
            self.pads = []
            for pad_idx in range(160):
                self.pads.append(Pad(pad_idx + 1, f.read(172)))

            # read sample names and assign them to the pad
            # all whitespace fields will turn in an empty string
            f.seek(0x6c20)
            for pad in self.pads:
                pad.name = spr.read_string(f, 24).strip()

            # read slice points if present and assign them to the pad
            f.seek(0x7b20)
            for pad in self.pads:
                slices = list(struct.unpack('>16I', f.read(0x80)[0:64]))
                # if slice points are not set, just use an empty list
                if slices[1] != EMPTY_MARKER:
                    pad.markers = [marker for marker in slices if marker != EMPTY_MARKER]
                else:
                    pad.markers = []
        return
