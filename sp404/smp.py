import struct
from enum import IntEnum

from . import spread as spr

ChannelMode = IntEnum(
    'ChannelMode',
    'MONO STEREO',
    start = 1
)

class Sample:
    def __init__(self, file_path):
        with open(file_path, 'rb') as f:
            if struct.unpack('4s', f.read(4))[0] != b"RFWV":
                raise ValueError('Invalid SMPL file')

            raw_samplesize = spr.read_long(f)
            self.samplerate = spr.read_long(f)
            if self.samplerate != 48000:
                raise ValueError(f"Invalid samplerate: Expected 48000 but got {self.samplerate}")

            self.mode = ChannelMode(spr.read_long(f))
            # sample starts at 0x200; raw_samplesize is (file size - 8), so payload
            # bytes = raw_samplesize - 0x200 + 8, and each frame is 2 bytes per channel
            self.size = int((raw_samplesize - 0x200 + 8) / (2 * self.mode.value))
