"""
Pure field-mapping helpers: SP404 pad/event values -> MPC XPJ values.
See convert/xpj/DESIGN.md section 5.4 for the field mapping tables this
implements, and section 11 for which of these are best-effort/unverified.
"""

from enum import IntEnum

from sp404.padconf import PlayMode, TrigMode

MPC_NOTE_BASE = 36

SP404_TICKS_PER_BAR = 1920
MPC_PULSES_PER_QUARTER = 960
MPC_BEATS_PER_BAR = 4
MPC_PULSES_PER_BAR = MPC_PULSES_PER_QUARTER * MPC_BEATS_PER_BAR
TICK_SCALE = MPC_PULSES_PER_BAR // SP404_TICKS_PER_BAR  # 2

COARSE_TUNE_RANGE = (-24, 24)
FINE_TUNE_RANGE = (-90, 90)

# Byte 3 of a pattern event: 0x00 is a plain, unpitched note; a byte with
# bit 7 set is a chromatic note with the pitch in bits 0-6, of which 0x8D
# (value 0x0D) is the common/default encoding seen so far. Both are
# "no pitch shift" baselines - see sp404/ptn.py and testing/SP404mk2/PTN.txt.
BASELINE_CHROMATIC_PITCH = 0x8D
UNPITCHED_CHROMATIC_PITCH = 0x00


def is_baseline_chromatic_pitch(byte):
    return byte == UNPITCHED_CHROMATIC_PITCH or byte == BASELINE_CHROMATIC_PITCH


class TriggerMode(IntEnum):
    ONE_SHOT = 0
    NOTE_OFF = 1
    NOTE_ON = 2


def clamp(value, bounds):
    lo, hi = bounds
    return max(lo, min(hi, value))


def pad_note(local_pad_nr):
    """local_pad_nr is 1..16; returns the MPC note assigned to that slot."""
    return MPC_NOTE_BASE + local_pad_nr


def instrument_volume(pad):
    return pad.vol / 127.0


def note_velocity(byte_velocity):
    return byte_velocity / 127.0


def trigger_mode(pad):
    """0=One Shot, 1=Note Off (gated), 2=Note On is never used - SP404 has
    no equivalent to MPC's polyphonic re-trigger mode."""
    if TrigMode.ONE_SHOT in pad.trig_mode:
        return int(TriggerMode.ONE_SHOT)
    if pad.gate:
        return int(TriggerMode.NOTE_OFF)
    return int(TriggerMode.ONE_SHOT)


def is_looping(pad):
    return TrigMode.LOOP in pad.trig_mode


def is_fixed_velocity(pad):
    return TrigMode.FIXED_VELOCITY in pad.trig_mode


def layer_direction(pad):
    """0=forward, 1=reverse; ping-pong modes have no MPC layer equivalent
    and degrade to plain reverse/forward - see DESIGN.md section 11."""
    if pad.play_mode in (PlayMode.REVERSE, PlayMode.REV_PINGPONG):
        return 1
    return 0


def is_pingpong(pad):
    return pad.play_mode in (PlayMode.FWD_PINGPONG, PlayMode.REV_PINGPONG)


def mute_group_index(pad):
    """Bank.NONE -> 0, Bank.A..Bank.J -> 1..10 (Bank is already numbered
    this way, see sp404/padconf.py)."""
    return int(pad.mute_group)


def note_length_pulses(pad, gate_ticks):
    """One-shots always play to completion; the recorded gate length is
    meaningless for them, so fall back to a full-bar default instead
    (DESIGN.md section 5.3)."""
    if TrigMode.ONE_SHOT in pad.trig_mode:
        return MPC_PULSES_PER_BAR
    return gate_ticks * TICK_SCALE
