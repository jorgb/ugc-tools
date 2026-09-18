"""
Synthetic MPC XPJ template pieces.

DESIGN.md section 7 calls for capturing these from a real MPC Sample / MPC
Live III save (an empty project plus one hand-placed note event). No such
hardware or software was available while writing this converter, so these
are hand-built from the documented schema (DESIGN.md section 4.3) instead
of a hardware capture. They cover every field that section documents and
nothing more - real hardware likely expects some of the ~120 additional
undocumented fields DESIGN.md section 4.0 mentions exist in the wild.

Treat every project this converter writes as unverified until it has
actually been loaded on real MPC Sample / MPC Live III hardware or
software (DESIGN.md section 10). If loading fails, the fields most likely
to need filling in are exactly the ones this module invents defaults for.
"""

from . import mapping

HEADER_LINES = ["ACVS", "3.7.0.56", "SerialisableProjectData", "json", "Linux"]


def empty_layer():
    return {
        "active": False,
        "volume": {"gainCoefficient": 1.0, "controlValue": 1.0, "law": 1},
        "pan": 0.5,
        "pitch": 0.0,
        "coarseTune": 0,
        "fineTune": 0,
        "velocityStart": 0,
        "velocityEnd": 127,
        "sampleStart": 0,
        "sampleEnd": 0,
        "loop": False,
        "loopStart": 0,
        "loopEnd": 0,
        "loopCrossfadeLength": 0,
        "loopFineTune": 0,
        "loopMode": 0,
        "mute": False,
        "rootNote": 60,
        "keyTrackEnable": False,
        "sampleName": "",
        "sampleFile": "",
        "sliceIndex": 128,  # sentinel: whole layer region, not a slice
        "direction": 0,
        "offset": 0,
        "playbackOffset": 0.0,
        "sliceInfo": {
            "Start": 0, "End": 0, "LoopStart": 0, "LoopMode": 0,
            "PulsePosition": 0, "LoopCrossfadeLength": -1, "LoopCrossfadeType": 0,
            "TailLength": 0.0, "TailLoopPosition": 0.5, "NumLoopRepeats": 0,
        },
        "pitchRandom": 0.0, "VolumeRandom": 0.0, "PanRandom": 0.0, "OffsetRandom": 0.0,
        "sliceIncrement": 0,
        "sliceCycleLength": 128,
        "sliceIncrementRngSeed": 0,
        "layerLoopModeOverridesSliceLoopMode": False,
        "quadrantEnabled": {"value0": True, "value1": True, "value2": True, "value3": True},
    }


def _adsr(attack=0.0, decay=0.05, sustain=1.0, release=0.0):
    return {
        "Attack": {"value0": attack},
        "Decay": {"value0": decay},
        "Sustain": {"value0": sustain},
        "Release": {"value0": release},
    }


def empty_synth_section():
    filter_params = {
        "filterCutoff": 1.0, "filterResonance": 0.0, "filterType": 0,
        "filterEnvelopeAmount": 0.0, "filterKeytrack": 0.0,
        "filterVelocity": 0.0, "filterEnvelopeVelocity": 0.0,
        "outputLevel": 1.0, "afterTouchToFilter": 0.0, "cutoffRandom": 0.0,
    }
    return {
        "version": 1,
        "filterData": {"value0": dict(filter_params), "value1": dict(filter_params)},
        "filterBlend": 0.0,
        "filterSerialRouting": False,
        "ampEnvelope": _adsr(),
        "filterEnvelope": _adsr(),
        "pitchEnvelope": _adsr(),
        "auxEnvelope": _adsr(),
        "pitchEnvelopeAmount": 0.0,
        "auxEnvelopeAmount": 0.0,
        "lfoData": {"value0": {"rate": 0.5, "waveform": 0}, "value1": {"rate": 0.5, "waveform": 0}},
        "velocitySensitivity": 0.0,
        "velocityToPan": 0.0,
        "velocityToPitch": 0.0,
        "velocityToStart": 0.0,
        "attackRandom": 0.0,
        "decayRandom": 0.0,
        "randomisationScale": 0.0,
        "driftSpeed": 0.0,
        "rampData": {},
    }


def empty_instrument():
    return {
        "version": 27,
        "coarseTune": 0,
        "fineTune": 0,
        "monophonic": False,
        "polyphony": 1,
        "lowNote": 0,
        "highNote": 127,  # dispatch is by padNoteMap, not by key range - see DESIGN.md section 5.2
        "ignoreBaseNote": False,
        "zonePlayTime": 0,
        "whichMuteGroup": 0,
        "muteTargets": [],
        "simultPlayTargets": [],
        "synthSection": empty_synth_section(),
        "triggerMode": 0,
        "tempo": 120.0,
        "bpmLock": False,
        "warpEnable": False,
        "stretchPercentage": 100.0,
        "layersv": [empty_layer() for _ in range(8)],
        "editAllLayers": False,
        "articulationUseXY": False,
        "articulations": {"value0": 0, "value1": 0, "value2": 0, "value3": 0},
        "userSelectableWarpPoolIndex": 0,
        "velocityScale": 100,
        "chopProperties": {
            "version": 1, "chopMode": 0, "chopThreshold": 65, "chopMinSliceTime": 0,
            "chopRegions": 16, "chopBars": 1, "chopBeats": 4, "chopTimeSignature": 4,
        },
        "layerCrossfade": 0,
        "layerCrossfadeX": 0.0,
        "layerCrossfadeY": 0.0,
        "mixable": {
            "version": 1,
            "audioRoute": {"destination": 0, "audioRouteSubIndex": 0, "channelBitmap": {"type": 0, "data": 3}},
            "volume": 1.0, "mute": False, "solo": False, "pan": 0.5,
            "automationFilter": 1, "sends": [0.0, 0.0, 0.0, 0.0],
            "inserts": {"insertsEnabled": True, "effects": []},
        },
        "padEffects": [],  # bus FX not carried over - see DESIGN.md section 2
        "noteCounters": 0,
        "modLinks": [{} for _ in range(32)],
        "randomPlaySeed": 0,
        "midiOutChannel": 0,
        "midiOutNote": 0,
        "midiOutBehaviour": 0,
        "partialPresetName": "",
    }


def empty_drum_program(name):
    return {
        "version": 4,
        "name": name,
        "type": 0,
        "programPads": {},
        "transpose": 0,
        "mixable": {"version": 1, "volume": 1.0, "pan": 0.5, "mute": False, "solo": False},
        "midiEventsFilter": {},
        "midiKillGroup": -1,
        "chainID": 0,
        "renderable": {"sendToCueBus": False},
        "xfaderRoute": 0,
        "customQLinks": [],
        "fxRackQLinks": [],
        "customMacroSceneData": {},
        "fxRackMacroSceneData": {},
        "customisable": {},
        "padNoteMap": {"noteForPad": {f"value{i}": 0 for i in range(128)}},
        "drum": {
            "version": 2,
            "drumVersion": 12,
            "instruments": [empty_instrument() for _ in range(128)],
            "padGroup": {f"value{i}": 0 for i in range(128)},
            "coarseTune": 0, "fineTune": 0, "pitch": 0,
            "monophonic": False, "poliphony": 32,  # NB: typo is intentional, see DESIGN.md section 4.0
            "portamentoTime": 0, "portamentoLegato": False,
            "portamentoQuantised": False, "monoRetrigger": False,
            "driftSpeed": 0.0, "freeRunningLfoData": [],
        },
    }


def empty_track(name):
    return {
        "name": name,
        "version": 5,
        "volume": 1.0, "volumeKnown": True,
        "pan": 0.5, "panKnown": True,
        "mute": False,
        "cvPort": 0, "gatePort": 1,
        "velocityScale": 1.0, "muteGroup": 0, "transposition": 0,
        "colour": 0, "padsFollowTrackColour": False, "skipFromRowLaunch": False,
        "samples": [],
        "program": empty_drum_program(name),
        "outputPort": {"type": 1, "deviceName": "<none>"},
        "outputChannel": 0,
        "midiMonitorable": {"state": 2},
        "length": 0, "lengthFollowsSequenceLength": True,
        "recordArm": False,
        "arrangementClipMap": [], "sharedClipMap": [],
    }


def sample_pool_entry(name, path, tempo):
    return {
        "version": 1,
        "name": name,
        "path": path,
        "loadImpl": 0,
        "metadata": {"tempo": tempo, "rootNote": 60, "tune": 0.0, "key": ""},
    }


def empty_note_event():
    note = {
        "version": 1,
        "note": 60,
        "velocity": 1.0,
        "length": mapping.MPC_PULSES_PER_QUARTER,
        "probability": 100,
        "ratchet": 1,
        "articulation": 197,
    }
    for i in range(16):
        note[f"modifierValue{i}"] = 0.0
        note[f"modifierActiveState{i}"] = False
    note["EnumCerealisationWrapper(selectedModifierType)"] = "Tuning (coarse)"
    return {
        "version": 2, "time": 0, "type": 3, "channel": 0,
        "selected": False, "muted": False, "invented": False,
        "note": note,
    }


def empty_clip(name, length_pulses):
    return {
        "version": 2,
        "launchQuantisation": 1,
        "startPulses": 0, "endPulses": length_pulses,
        "loopStartPulses": 0, "loopEndPulses": length_pulses,
        "loop": True, "legato": True, "launch": 0,
        "name": name, "colour": 0,
        "eventList": {
            "length": 9223372036854775807,  # int64-max sentinel, left untouched
            "events": [],
            "version": 2,
            "quantisation": {"version": 1, "pulses": 0, "swing": 0.0, "strength": 1.0},
            "numFilterTypes": 30,
        },
        "perClipParameterValues": {},
    }


def empty_sequence(name, bpm, bars, loop_end_bar):
    length_pulses = bars * mapping.MPC_PULSES_PER_BAR
    return {
        "version": 5,
        "name": name,
        "bpm": bpm,
        "tempoEnable": True,
        "lengthBars": bars,
        "lengthPulses": length_pulses,
        "loopStartBar": 0,
        "loopEndBar": loop_end_bar,
        "loop": True,
        "transposition": 0,
        "timeSignatureTrack": {
            "timeSignatures": [
                {"beatsPerBar": mapping.MPC_BEATS_PER_BAR,
                 "beatLength": mapping.MPC_PULSES_PER_QUARTER,
                 "barStart": 0},
            ],
        },
        "trackClipMaps": [[]],
        "seqEventList": {},
        "locators": {
            "version": 1,
            "names": [str(i) for i in range(1, 7)],
            "positions": [{"bar": 0, "beat": 0, "pulse": 0} for _ in range(6)],
            "colours": [0] * 6,
        },
        "loopStartPulses": 0,
        "loopEndPulses": length_pulses,
        "autoSelectTrackIndex": -1,
    }


def empty_project():
    return {
        "formatVersion": 2,
        "data": {
            "version": 28,
            "key": "C Major",
            "masterTempoEnabled": False,
            "masterTempo": 120.0,
            "engineMode": 5,
            "currentSequence": 0,
            "currentTrackIndex": 0,
            "emulation": 0,
            "lastSavedProductIdentifier": "ACVB",
            "originalCreatorProductIdentifier": "ACVB",
            "tracks": [],
            "sequences": [],
            "songs": [{"items": [], "name": f"Song {i + 1}"} for i in range(32)],
            "samples": [],
            "mixer": {},
            "qlinkMode": "Screen",
            "value0": "1 Bar",
            "trackMutePerSequence": True,
            "quantiser": {"enabled": False, "timeDivision": 0, "swingLevel": 0.0},
        },
    }
