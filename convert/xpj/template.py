"""
MPC XPJ template pieces, cut from a project saved by a real MPC.

template/mpc_project.xpj is an unmodified project saved by MPC firmware
1.3.0.12 (product AC50): one drum track, three samples on pads 13-15 and a
2-bar sequence. Everything the converter doesn't map from the SP404 - the
mixer, Q-Links, locators, ~60 top-level keys, every instrument/layer field -
comes straight from it, so the output has exactly the shape MPC itself
writes. The earlier hand-built template (DESIGN.md section 7) was missing or
mis-typing dozens of fields and the MPC refused to load the result.

The reference is blanked at load time: its samples, sequence content and the
three sample-bearing pads are removed, and the pieces the writer clones are
cut out of it.
"""

import functools
import json
import os

from . import mapping
from . import reader

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "template", "mpc_project.xpj")

DRUM_PROGRAM_TYPE = 0

# MPC never writes an empty sample key; it detects one per sample. The
# SP404 has no equivalent, so use the project's own default key.
DEFAULT_SAMPLE_KEY = "C Major"


def _clone(value):
    return json.loads(json.dumps(value))


def _is_blank(instrument):
    return all(not layer["sampleFile"] for layer in instrument["layersv"])


@functools.lru_cache(maxsize=None)
def _reference():
    """Parses the reference project once and cuts it into blanked pieces."""
    header_lines, project = reader.read_project(TEMPLATE_PATH)
    data = project["data"]

    drum_track = next(t for t in data["tracks"] if t["program"]["type"] == DRUM_PROGRAM_TYPE)
    system_tracks = [t for t in data["tracks"] if t is not drum_track]

    instruments = drum_track["program"]["drum"]["instruments"]
    blank = next(i for i in instruments if _is_blank(i))
    loaded = _clone(next(i for i in instruments if not _is_blank(i)))
    # what MPC itself changed when it loaded a sample into a blank pad
    loaded["layersv"][0]["sampleName"] = ""
    loaded["layersv"][0]["sampleFile"] = ""
    loaded["layersv"][0]["sliceInfo"]["End"] = 0
    drum_track["program"]["drum"]["instruments"] = [_clone(blank) for _ in instruments]
    drum_track["samples"] = []

    sequence = data["sequences"][0]["value"]
    clips = {entry["key"]: entry["value"] for entry in sequence["trackClipMaps"][0]}
    note_event = _clone(clips[drum_track["name"]]["eventList"]["events"][0])
    sample = _clone(data["samples"][0])

    # the drum clip carries this reference's own quantise settings, so build
    # every clip from a system track's untouched one instead
    clip = _clone(clips[system_tracks[0]["name"]])
    for track_clip in clips.values():
        track_clip["eventList"]["events"] = []
    sequence["trackClipMaps"] = [[
        {"key": name, "value": clips[name]} for name in sorted(t["name"] for t in system_tracks)
    ]]
    sequence["name"] = ""

    data["tracks"] = system_tracks
    data["samples"] = []
    data["sequences"] = []
    data["clipPlayerData"]["trackClipTransportMap"] = []

    return {
        "header_lines": header_lines,
        "project": project,
        "drum_track": drum_track,
        "loaded_instrument": loaded,
        "sequence": sequence,
        "clip": clip,
        "note_event": note_event,
        "sample": sample,
    }


def assign(container, key, value):
    """Sets container[key], which must already exist, to value converted to
    the JSON type the template holds there. MPC parses these files with
    strict types (`100` and `100.0` are not interchangeable), so a field is
    never added or retyped, only given a new value."""
    current = container[key]
    if isinstance(current, bool):
        container[key] = bool(value)
    elif isinstance(current, int):
        container[key] = int(round(value))
    elif isinstance(current, float):
        container[key] = float(value)
    else:
        container[key] = value


def header_lines():
    return list(_reference()["header_lines"])


def empty_project():
    """The project with only MPC's own fixed tracks (submix and outputs); the
    writer adds the drum tracks, samples and sequences."""
    return _clone(_reference()["project"])


def empty_track(name):
    """One drum track with 128 blank pads."""
    track = _clone(_reference()["drum_track"])
    assign(track, "name", name)
    assign(track["program"], "name", name)
    return track


def sampled_instrument():
    """A blank pad in the state MPC leaves it in after loading a sample."""
    return _clone(_reference()["loaded_instrument"])


def sample_pool_entry(name, path, tempo):
    entry = _clone(_reference()["sample"])
    assign(entry, "name", name)
    assign(entry, "path", path)
    assign(entry["metadata"], "tempo", tempo)
    assign(entry["metadata"], "key", DEFAULT_SAMPLE_KEY)
    return entry


def empty_note_event():
    return _clone(_reference()["note_event"])


def empty_clip(name, length_pulses):
    clip = _clone(_reference()["clip"])
    assign(clip, "name", name)
    assign(clip, "endPulses", length_pulses)
    assign(clip, "loopEndPulses", length_pulses)
    return clip


def empty_sequence(name, bpm, bars, loop_end_bar):
    """A sequence holding one empty clip per fixed MPC track; the writer adds
    the drum tracks' clips to trackClipMaps[0]."""
    length_pulses = bars * mapping.MPC_PULSES_PER_BAR
    sequence = _clone(_reference()["sequence"])
    assign(sequence, "name", name)
    assign(sequence, "bpm", bpm)
    assign(sequence, "lengthBars", bars)
    assign(sequence, "lengthPulses", length_pulses)
    assign(sequence, "loopEndBar", loop_end_bar)
    assign(sequence, "loopEndPulses", length_pulses)
    for entry in sequence["trackClipMaps"][0]:
        assign(entry["value"], "endPulses", length_pulses)
        assign(entry["value"], "loopEndPulses", length_pulses)
    return sequence
