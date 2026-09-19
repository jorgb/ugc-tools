"""
Pure field-mapping helpers: SP404 pad/event values -> MPC XPJ values.
See convert/xpj/DESIGN.md section 5.4 for the field mapping tables this
implements, and section 11 for which of these are best-effort/unverified.
"""

import math
from enum import IntEnum

from sp404.padconf import PlayMode, TrigMode

MPC_NOTE_BASE = 36

# 0 dB on every MPC volume control (track, mixer, pad); 1.0 is +3 dB. Read
# from the reference project's untouched pads (convert/xpj/template.py).
MPC_UNITY_VOLUME = 0.7079457640647888

SP404_TICKS_PER_BAR = 1920
MPC_PULSES_PER_QUARTER = 960
MPC_BEATS_PER_BAR = 4
MPC_PULSES_PER_BAR = MPC_PULSES_PER_QUARTER * MPC_BEATS_PER_BAR
TICK_SCALE = MPC_PULSES_PER_BAR // SP404_TICKS_PER_BAR  # 2

COARSE_TUNE_RANGE = (-24, 24)
FINE_TUNE_RANGE = (-90, 90)

# SP404 ENVELOPE page: attack and release are 0-127 (127 = 3 s), hold is the
# percentage of the sample that plays
SP404_ENVELOPE_MAX = 127
SP404_HOLD_RANGE = (1, 100)

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


def slot_note(slot):
    """MPC note played by drum program pad `slot` (0..127).

    Read from the reference project's padNoteMap: note = (36 + slot) % 128,
    so pad A01 plays 36, pad 13 plays 48, and the map wraps past slot 91
    (slot 92 plays note 0). All 128 notes are distinct. The map is never
    edited (DESIGN.md section 5.2)."""
    return (MPC_NOTE_BASE + slot) % 128


def instrument_volume(pad):
    """SP404 volume 127 is unity gain, which is MPC_UNITY_VOLUME (not 1.0)."""
    return MPC_UNITY_VOLUME * (pad.vol / 127.0)


def sample_region(pad):
    """Inclusive (first, last) frame of the pad's playback region. The SP404's
    sample_end is one past the last frame; MPC's sliceInfo End is the last
    frame itself (an untouched sample of N frames has End N-1).

    The SP404's envelope HOLD is the percentage of the region that plays (at
    50 the sample stops at its middle), so the region ends there."""
    first, last = pad.sample_start, max(pad.sample_end - 1, 0)
    hold = clamp(pad.hold, SP404_HOLD_RANGE)
    if hold < SP404_HOLD_RANGE[1]:
        frames = max(last - first + 1, 0)
        last = first + max(round(frames * hold / 100), 1) - 1
    return first, last


def sample_tempo(pad):
    """MPC leaves a sample's tempo at 0.0 unless it has a known one."""
    return pad.bpm if pad.bpm_sync else 0.0


def note_velocity(byte_velocity):
    return byte_velocity / 127.0


def trigger_mode(pad):
    """SP404 GATE on (sample plays while the pad is held) is MPC's Note On;
    GATE off, or the pad's One Shot flag, plays the sample through: One Shot.
    Note Off is never used."""
    if TrigMode.ONE_SHOT in pad.trig_mode:
        return int(TriggerMode.ONE_SHOT)
    if pad.gate:
        return int(TriggerMode.NOTE_ON)
    return int(TriggerMode.ONE_SHOT)


def pitch_cents(pad):
    """The pad's total pitch offset in cents.

    With BPM sync off the SP404 stores pad pitch as a varispeed ratio in its
    Speed field (2^(semitones/12), so -5 semitones is 74.91%), and its Pitch
    Coarse/Fine fields stay 0. With BPM sync on the Speed field is a real time
    stretch and does not change pitch. Coarse/Fine are added in either case."""
    cents = pad.pitch_coarse * 100 + pad.pitch_fine
    if not pad.bpm_sync and pad.speed_perc > 0:
        cents += 1200 * math.log2(pad.speed_perc / 100)
    return cents


def tuning(pad):
    """(coarseTune, fineTune) for the pad: whole semitones, then the
    remaining cents (-50..50), each clamped to MPC's limits."""
    cents = pitch_cents(pad)
    coarse = round(cents / 100)
    fine = round(cents - coarse * 100)
    return clamp(coarse, COARSE_TUNE_RANGE), clamp(fine, FINE_TUNE_RANGE)


def stretch_percentage(pad):
    """MPC's time stretch. Only a BPM-synced pad has one; for the rest the
    Speed field was already applied as pitch (see pitch_cents)."""
    return pad.speed_perc if pad.bpm_sync else 100.0


def amp_envelope(pad):
    """The MPC amp envelope fields (synthSection.ampEnvelope.<name>.value0) to
    change so the pad fades like the SP404's ENVELOPE page; empty when the pad
    has no attack or release, so it keeps MPC's own defaults.

    Attack and release are carried over at the same position on the 0-127 dial
    (MPC stores its own as k/127); the SP404's 3 seconds at 127 is not
    converted to MPC's seconds, which are unverified.

    - Attack is the fade-in.
    - GATE off: the SP404 plays to the end of the hold range and fades out
      there, which is MPC's Decay (its envelope decays from the end).
    - GATE on: the fade-out starts when the pad is released, which is MPC's
      Release, on an ADSR envelope that responds to note-off rather than the
      default AD one-shot.
    """
    fields = {}
    if pad.attack > 0:
        fields["Attack"] = clamp(pad.attack, (0, SP404_ENVELOPE_MAX)) / SP404_ENVELOPE_MAX
    if pad.release > 0:
        release = clamp(pad.release, (0, SP404_ENVELOPE_MAX)) / SP404_ENVELOPE_MAX
        if trigger_mode(pad) == TriggerMode.NOTE_ON:
            fields["Release"] = release
            fields["AD"] = False
            fields["OneShot"] = False
        else:
            fields["Decay"] = release
    return fields


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
