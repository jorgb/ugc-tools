"""
Internal utility module for reading primitives from binary structures.
This module is intended for internal use within the sp404 package.
"""

import struct

def read_long(f):
    return read_long_b(f.read(4))


def read_long_b(buf):
    return struct.unpack(">L", buf)[0]


def read_slong_b(buf):
    return struct.unpack(">l", buf)[0]


def read_string(f, size):
    buf = f.read(size)
    # only the bytes up to the first NUL terminator are meaningful; bytes
    # after that can be stale leftover data rather than more padding (seen
    # in real pad name fields, e.g. b"Backing Sample\x00\x00\x00      \x00")
    return buf.split(b'\x00', 1)[0].decode('ascii')
