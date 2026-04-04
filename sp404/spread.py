"""
Internal utility module for reading primitives from binary structures.
This module is intended for internal use within the sp404 package.
"""

import struct

def read_long(f):
    return read_long_b(f.read(4))


def read_long_b(buf):
    return struct.unpack(">L", buf)[0]


def read_string(f, size):
    buf = f.read(size)
    return struct.unpack("%ds" % size, buf)[0].decode('ascii').rstrip('\x00')
