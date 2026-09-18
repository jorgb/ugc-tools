import struct

_PADS = "ABCDEFGHIJ"

CONTROL_CHANGE = 0x8E


class PadID:
    def __init__(self, pad_nr, pad_toggle):
        self.pad = None

        if pad_nr < 0x2f or pad_nr > 0x7e:
            raise ValueError("Pad number should be between 0x2f and 0x7e")

        # only the low nibble selects the bank group (0=A-E, 1=F-J); other
        # bits (0x40 seen in real captures) are ignored by the app itself -
        # see testing/SP404mk2/PTN.txt's 2026-09-18 section
        group = pad_toggle & 0x0F
        if group == 0x00 or group == 0x01:
            pad_idx = (pad_nr - 0x2f)
            self.pad = _PADS[(pad_idx // 16) + (5 if group == 0x01 else 0)] + "{:02d}".format(pad_idx % 16 + 1)
        else:
            raise ValueError("Pad toggle should be 0x00 or 0x01")

    @property
    def name(self):
        return self.pad


class PatternEvent:
    """
    Represents a single event within an SP404mk2 pattern
    """
    def __init__(self, buf):
        if len(buf) != 8:
            raise ValueError(f"PatternEvent buffer must be 8 bytes, got {len(buf)}")

        self.note_offset = buf[0]
        # tick position of this event within the pattern; note_offset is only
        # a delta to the *next* record, so this is filled in by Pattern._read
        # as a running sum over every earlier record (filler or not)
        self.absolute_tick = 0
        self.midi_channel = None
        self.controller = None
        self.controller_value = None

        if buf[1] == CONTROL_CHANGE:
            # no pad, this is a control change event (e.g. EXT-IN automation)
            self.pad_id = None
            self.midi_channel = buf[2]
            self.controller = buf[5]
            self.controller_value = buf[6]
        elif buf[1] & 0x80:
            # no pad information
            self.pad_id = None
        else:
            self.pad_id = PadID(buf[1], buf[2])

        # chromatic pitch: bit 7 is a flag, bits 0-6 a value; 0x8D is the
        # common/baseline value seen on every unpitched note so far
        self.chromatic_pitch = buf[3]
        self.velocity = buf[4]
        # stored reversed (little-endian) and off-by-one
        self.gate_ticks = struct.unpack("<H", buf[6:8])[0] + 1


    def __repr__(self):
        if self.controller is not None:
            return (f"PatternEvent(time={self.absolute_tick:4d}, "
                    f"cc=channel {self.midi_channel} controller {self.controller} "
                    f"value {self.controller_value})")

        pad_name = self.pad_id.name if self.pad_id else "<none>"
        return f"PatternEvent(time={self.absolute_tick:4d}, velocity={self.velocity}, pad={pad_name})"


# trailer byte 4 -> (beats per bar, beat unit)
_TIME_SIGNATURES = {
    0: (4, 4),
    1: (1, 4),
    2: (2, 4),
    3: (3, 4),
    4: (5, 4),
    5: (6, 4),
    6: (7, 4),
}


class Pattern:
    """
    Parses an SP404mk2 pattern file.
    """
    def __init__(self, file_path):
        self.events = []
        self.footer = None
        self.bars = None
        self.time_signature = None
        self.loop_start_bar = None
        self.loop_end_bar = None
        self._read(file_path)

    def _read(self, file_path):
        # TODO: Group pads per same tick offset (e.g. A01, B01 on offset 0x00 should be pattern.events[0] and pattern.events[1])

        with open(file_path, 'rb') as f:
            data = f.read()

            if len(data) < 16:
                raise ValueError("Pattern file is too short.")

            event_data_len = len(data) - 16
            if event_data_len % 8 != 0:
                raise ValueError(f"Pattern event data length ({event_data_len}) is not a multiple of 8 bytes.")

            tick = 0
            for i in range(0, event_data_len, 8):
                event = PatternEvent(data[i:i+8])
                event.absolute_tick = tick
                tick += event.note_offset

                # pure filler records carry no information once their tick
                # has been folded into the running counter; real notes and
                # control change events are kept
                if event.pad_id is None and event.controller is None:
                    continue
                self.events.append(event)

            self.footer = data[-16:]

            # footer = 8-byte end-of-events marker (0x8C) + 8-byte trailer
            trailer = self.footer[8:16]
            self.bars = trailer[0]
            self.time_signature = _TIME_SIGNATURES.get(trailer[4], (4, 4))
            # NOTE: loop start/end bar bytes are based on this repo's own
            # empirical findings (testing/SP404mk2/PTN.txt), which disagree
            # with an independent RE project that called these two bytes
            # unused constants - see that file's 2026-09-18 section
            self.loop_start_bar = trailer[5]
            self.loop_end_bar = trailer[6]


    def __repr__(self):
        events_str = "\n  ".join(str(e) for e in self.events)
        footer_hex = " ".join(f"{b:02X}" for b in self.footer) if self.footer else "None"
        return (f"Pattern(\n  events=[\n  {events_str}\n  ],\n"
                f"  bars={self.bars}, time_signature={self.time_signature},\n"
                f"  footer={footer_hex}\n)")
