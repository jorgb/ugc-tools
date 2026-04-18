_PADS = "ABCDEFGHIJ"


class PadID:
    def __init__(self, pad_nr, pad_toggle):
        self.pad = None

        if pad_nr < 0x2f or pad_nr > 0x7e:
            raise ValueError("Pad number should be between 0x2f and 0x7e")

        if pad_toggle == 0x00 or pad_toggle == 0x01:
            pad_idx = (pad_nr - 0x2f)
            self.pad = _PADS[(pad_idx // 16) + (5 if pad_toggle == 0x01 else 0)] + "{:02d}".format(pad_idx % 16 + 1)
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
        if buf[1] & 0x80:
            # no pad information
            self.pad_id = None
        else:
            self.pad_id = PadID(buf[1], buf[2])

        # velocity
        self.velocity = buf[4]


    def __repr__(self):
        pad_name = self.pad_id.name if self.pad_id else "<none>"
        return f"PatternEvent(time={self.note_offset:3d}, velocity={self.velocity}, pad={pad_name})"


class Pattern:
    """
    Parses an SP404mk2 pattern file.
    """
    def __init__(self, file_path):
        self.events = []
        self.footer = None
        self._read(file_path)

    def _read(self, file_path):
        # TODO: Group pads per same tick offset (e.g. A01, B01 on offset 0x00 should be pattern.events[0] and pattern.events[1])
        # TODO: Skip all filler events in the sequence list
        # TODO: Add tick offset to PatternEvent (max. 1920?)
        # TODO: Implement missing events

        with open(file_path, 'rb') as f:
            data = f.read()

            if len(data) < 16:
                raise ValueError("Pattern file is too short.")

            event_data_len = len(data) - 16
            if event_data_len % 8 != 0:
                raise ValueError(f"Pattern event data length ({event_data_len}) is not a multiple of 8 bytes.")

            for i in range(0, event_data_len, 8):
                event_buf = data[i:i+8]
                self.events.append(PatternEvent(event_buf))
                
            self.footer = data[-16:]


    def __repr__(self):
        events_str = "\n  ".join(str(e) for e in self.events)
        footer_hex = " ".join(f"{b:02X}" for b in self.footer) if self.footer else "None"
        return f"Pattern(\n  events=[\n  {events_str}\n  ],\n  footer={footer_hex}\n)"
