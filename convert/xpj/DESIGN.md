# SP404mk2 → MPC XPJ Converter — Design

Status: design only, no code yet. This document lays out how to convert an
exported SP404mk2 project (PADCONF.BIN + SMPL/*.SMP + PTN/*.BIN) into an
Akai MPC project (`.xpj` + `[Project Data]` folder) that loads on **MPC Live
III** and **MPC Sample**, including the pad samples and the sequencer data.

**Verification pass (this revision):** every XPJ claim below was re-checked
against raw example JSON files and independent open-source parser code —
not just prose documentation — because the prose documentation itself
turned out to contain errors and internal contradictions. See §4.0 for what
changed and why the JSON/code evidence is trusted over the docs when they
disagree.

## 1. Goal

Given a folder exported from an SP404mk2 (see
`testing/SP404mk2/pad-sequencer/2026-04-08/`), produce:

- One `.xpj` project file MPC Standalone can open directly.
- A sibling `<ProjectName> [Project Data]/Samples/` folder with one `.wav`
  per SP404 pad sample, decoded from the proprietary `.SMP` format.
- Every SP404 pattern converted into an MPC sequence with the same note
  timing, pad, and velocity data.

## 2. Scope & non-goals

In scope:

- PADCONF.BIN → pad/bank metadata (names, start/end, volume, gate, loop,
  play mode, trig mode, mute group, pad link, BPM, pitch/speed, per-bank
  BPM, project name).
- SMPL/*.SMP → decoded WAV audio, one file per pad.
- PTN/*.BIN → per-pattern note events (pad, timing, velocity, gate length),
  turned into MPC sequence events.

Explicitly out of scope (per requirements, and confirmed by
`testing/SP404mk2/mk2_notes.txt` / `PADCONF.txt`):

- Bus FX (`pad.bus_fx`) — SP404 bus effects are not carried over.
- SP404 pad "chops"/markers (`pad.markers`, see
  `testing/SP404mk2/pad-chops/`). The SP404 plays one continuous
  region per pad; we honor `sample_start`/`sample_end` but do **not**
  attempt to reproduce internal slice points as MPC "slices". Each pad
  becomes exactly one MPC instrument with one sample layer, per the
  "treat every pad as a [single] sample" instruction.
- EXT-IN automation, "motion" recording, screensaver/startup BMPs
  (`PICTURE/`) — none of these have a meaningful MPC equivalent and are
  dropped silently.
- Roll settings (roll on/off, ratio) — not yet decoded on the SP404 side
  (see `testing/SP404mk2/PADCONF.txt`, marked with `?` prefixes); treated
  as a follow-up once reverse-engineered.

## 3. Source format recap

### 3.1 On-disk layout (SP404mk2 export)

```
<export>/
  PADCONF.BIN            project + 160 pads (10 banks x 16 pads)
  SMPL/BANK<n>-<m>.SMP   raw sample data, one or more per bank
  PTN/PTN#####.BIN       one file per recorded pattern
  PICTURE/*.bmp          skipped
```

Already-working parsers live in `sp404/` and are reused as-is:

- `sp404.padconf.Project` — reads `PADCONF.BIN`: project name, per-bank BPM,
  and a `Pad` per pad-slot (172-byte record) with `sample_start`,
  `sample_end`, `vol`, `gate`, `mute_group`, `pad_link`, `bpm_sync`, `bpm`,
  `loop_start`, `play_mode`, `trig_mode` (list), `bus_fx`, `chromatic`,
  `time_stretch_perc`, `name`, `markers`.
- `sp404.smp.Sample` — reads a `.SMP` file header (`RFWV` magic,
  `samplerate`, `mode` mono/stereo, `size` in samples).
- `sp404.ptn.Pattern` / `PatternEvent` / `PadID` — reads a `.PTN` file into
  8-byte event records plus a 16-byte footer. `PadID` already knows how to
  turn `(pad_nr, pad_toggle)` into a pad name (`A01`..`J16`).

### 3.2 What still needs to be decoded in `sp404.ptn`

The current parser (see TODOs in `sp404/ptn.py`) reads each 8-byte record
but does not yet reconstruct the data the converter needs. Per
`testing/SP404mk2/PTN.txt`, confirmed empirically:

- **Byte 0 (`note_offset`) is a delta, not an absolute position.** Every
  record (real note *and* filler) contributes its `note_offset` to a
  running total that always sums to `1920` ticks for a 1-bar pattern
  (`1920 / 16 steps = 120 ticks/step`, matching the microscope nudge range
  of 0–119). The converter needs an **absolute tick** per event, computed
  as a running sum over *all* records in file order, filler or not.
- **Filler records** are any record whose pad byte has bit 0x80 set and
  isn't a control-change record (already exposed today as `pad_id is
  None`). They carry no note, only timing filler, and must be skipped once
  their offset has been folded into the running tick total. **Control
  change records (`0x8E`) are the one exception** — `sp404/ptn.py` now
  detects these separately (`PatternEvent.midi_channel`/`controller`/
  `controller_value`, non-`None` only for this record type) instead of
  lumping them in with plain fillers, since they carry real payload
  (channel/controller/value) that a generic "fold into tick total and
  discard" pass would otherwise silently drop. This is very likely the
  mechanism behind the "EXT-IN automation" question in
  `testing/SP404mk2/PTN.txt`. The XPJ converter doesn't map these to
  anything yet (no automation events are generated), so for now they
  should still be excluded from note events but not simply discarded
  the way pure fillers are — worth revisiting once there's a concrete
  XPJ automation-event target to map them to.
- **Byte 3** is chromatic pitch for that specific event (per-event pitch
  offset, independent of the pad's own base pitch).
- **Bytes 6–7** are the gate/tick length of the note, stored reversed
  (little-endian) and off-by-one (`length = value + 1`), e.g. `9F 05` →
  `0x059F` → `1439` → a 1440-tick gate.
- **The 16-byte footer** (`00 8C 00 00 00 00 00 00 | bars 00 00 00 00 loopEnd 00 00`)
  gives pattern length in bars (footer byte 8) and loop end bar (footer
  byte 14). This becomes the MPC sequence's `lengthBars`.

Design decision: extend `PatternEvent`/`Pattern` with an `absolute_tick`
field and a `gate_ticks` field, and have `Pattern._read` filter out filler
records after folding their ticks into the running counter, rather than
pushing that logic into the XPJ writer. This keeps `sp404.ptn` a complete,
reusable parser (consistent with how `sp404.padconf` and `sp404.smp` are
already complete), and the XPJ package only has to consume clean
`(absolute_tick, pad_id, velocity, gate_ticks, chromatic_pitch)` tuples.

### 3.3 SMP → PCM decoding

Per `testing/SP404mk2/SMPL.txt` and `sp404/smp.py`:

- Header: `RFWV` magic, then big-endian `u32` raw size, `u32` sample rate
  (48000), `u32` channel mode (1=mono, 2=stereo).
- Audio payload starts at file offset `0x200`.
- Samples are stored as **16-bit big-endian PCM**, interleaved for stereo.
- Sample count: `(raw_size - 0x200 + 8) / (2 * channels)` frames, where
  `raw_size` is the header's u32 size field (= file size − 8, confirmed
  against an independent RE project and empirically against this repo's
  own `.SMP` fixtures — see `testing/SP404mk2/SMPL.txt`'s 2026-09-18
  section). Now implemented as `Sample.size`; a previous version of this
  formula in `sp404/smp.py` computed a value 4× too large and has been
  fixed. Not yet re-verified against the physical SP404 app/hardware.

To turn this into a standard WAV: read the payload starting at `0x200`,
byte-swap every 16-bit sample from big-endian to little-endian, and write
a canonical PCM WAV (`RIFF`/`WAVE`, `fmt ` chunk with the SMP's own sample
rate/channel count, `data` chunk with the byte-swapped payload). This is
exactly what `testing/SP404mk2/mk2_notes.txt`'s Gemini-sourced snippet
does; `sp404.smp.Sample` already provides the size/rate/mode needed to
drive it, so this becomes a small `wav.py` helper (see §6) rather than a
new parser.

### 3.4 PADCONF pad fields not yet mapped by an enum

A few numeric fields in `sp404.padconf.Pad` are stored as raw
percent/semitone values rather than enums (`time_stretch_perc`, `bpm`,
`loop_start`). These pass straight through to the mapping tables in §5.4.

Note: `time_stretch_perc` was previously named `pitch_perc` in this parser;
it was renamed after cross-checking against an independent RE project
(see `testing/SP404mk2/mk2_notes.txt`'s 2026-09-18 section) which showed it
matches the SP404's "Time Stretch %" parameter (word 16 of the pad record),
not raw pitch. The pad's *actual* pitch controls — `pitch_coarse`
(semitones, word 13) and `pitch_fine` (cents, word 14) — are now also read
by `sp404.padconf.Pad`, using a new `spr.read_slong_b` (signed, big-endian)
helper, since unlike every other field on `Pad` these can be negative.
This has **not** been verified against the SP404 app — every pad in the
`testing/SP404mk2/pad-params/PADCONF.BIN` fixture reads `0` for both, which
is consistent with "untouched default" but doesn't exercise the signed
decoding on a real non-zero value. §5.4 below reflects this.

## 4. Target format recap: MPC XPJ

### 4.0 Sources used, and what verification against them changed

There is no first-party spec. The community-reverse-engineered
[`kurtjcu/MPC-project-file-definitions`](https://github.com/kurtjcu/MPC-project-file-definitions)
knowledge base (derived from 18 real projects + the MPC 3.7 manual) is the
most complete write-up available, but its own prose descriptions turned out
to be unreliable in places — sometimes contradicted by the very example
JSON files checked into the same repository. So this design treats three
kinds of evidence with decreasing trust when they disagree:

1. **Real example JSON** (`xpj-format/examples/*.json` in that repo) —
   ground truth, fetched and parsed directly with Python's `json` module,
   not summarized.
2. **Independent open-source parser code** —
   [`tarikcampos/MPC-Sample-Toolkit`](https://github.com/tarikcampos/MPC-Sample-Toolkit)
   (`src/mpctk/xpj/*.py`, `src/mpctk/generation/*.py`), a working WAV → MPC
   Sample project generator whose field access (`data.get("sampleFile")`,
   etc.) independently confirms or refutes a claim.
3. **The prose `.md` docs themselves** — used only where (1) and (2) don't
   cover a detail, and flagged as lower-confidence.

Concretely, the prose docs got these wrong (corrected throughout the rest
of §4 and reflected in §5):

| Claimed in prose docs | What the real JSON/code actually shows |
|---|---|
| Track's program object is keyed `"programme"` | It's `"program"` — confirmed in `track-drum.json`, `instrument-drum.json`, and literally spelled `"program"` in `02-track-types.md`'s own JSON snippet. The earlier "programme" reading was a bad paraphrase, not a real quirk. |
| `padNoteMap` lives inside `program.drum` | It's a **sibling** of `drum`, at `program.padNoteMap` — confirmed by loading `track-drum.json` and listing keys. |
| Note/automation/audio event fields sit flat on the event object (`{"type": 3, "note": 39, "velocity": ...}`) | Real events wrap the type-specific payload in a **nested sub-object** named after the type: `{"version": 2, "time": 0, "type": 3, "channel": 0, "selected": false, "muted": false, "invented": false, "note": {"note": 39, "velocity": ..., "length": ..., ...}}`. Confirmed in `examples/event-note.json`, `event-automation.json`, `event-audio.json`, and `10-event-types.md`'s own code samples (which contradict that same doc's earlier prose summary). |
| Layer's `sampleName` holds the filename with extension and matches the sample-pool `path` | The layer has **two separate fields**: `sampleName` (display name, no extension) and `sampleFile` (filename with extension). It's `sampleFile` that matches the sample pool's `path`. `12-samples.md`'s own prose gets this wrong even though it's one file that also links to the correct example. Independently confirmed in MPCTK's `model.py`: `name = data.get("sampleName"); file = data.get("sampleFile")`. |
| Layer `volume` is "a simple float, not an object" | It's the opposite: layer volume **is** an object, `{"gainCoefficient": 1.0, "controlValue": 1.0, "law": 1}`. Track-level and per-instrument `mixable.volume` **are** simple floats. `00-format-reference.md`'s own quirk table gets this right (`"Object volume: Layer/pad volumes are objects, NOT floats"`) even though a different summary pass got it backwards. Confirmed in `instrument-drum.json` and in MPCTK's `Layer.volume: dict[str, Any]`. |
| `trackClipMaps[row][col].key` is a numeric track index | It's the **track's `name` string** (e.g. `"HipHop Bass"`, `"Audio 001"`) — confirmed in `examples/sequence.json`. |
| `timeSignatureTrack` is a flat `{beatsPerBar, beatLength, barStart}` object | It's `{"timeSignatures": [{"beatsPerBar": 4, "beatLength": 960, "barStart": 0}]}` — an array of time-signature changes, confirmed in `examples/sequence.json` and `09-sequences-events.md`'s own JSON sample. |
| `poliphony` typo applies generally | It's specifically a **drum-program-level** field (`program.drum.poliphony`). The **per-instrument** field is spelled correctly: `instruments[i].polyphony`. Confirmed by loading `track-drum.json` and checking both locations directly. |

Both MPC Live III and MPC Sample run the same "MPC 3.x" standalone OS, so
they share this format. On-disk project layout is additionally
cross-checked against [MPC-Tutor's project-structure write-up](https://www.mpc-tutor.com/mpc-x-mpc-live-projects-lowdown/)
(§4.2).

### 4.1 Container format

An `.xpj` file (firmware 3.x, which covers MPC Live III / MPC Sample) is:

```
gzip(
  "ACVS\n"
  "<firmware-version>\n"       e.g. "3.7.0.56"
  "SerialisableProjectData\n"
  "json\n"
  "Linux\n"
  <JSON body>
)
```

This is now confirmed not just by the docs but by MPCTK's actual writer
(`src/mpctk/xpj/header.py` + `src/mpctk/xpj/writer.py`): it builds the 5
header lines, joins them with `"\n"`, appends another `"\n"`, then the raw
JSON text, encodes to UTF-8, and gzips the whole byte string. There is no
extra framing beyond that.

The JSON body is `{"formatVersion": 2, "data": {...}}`. Detection of 3.x
vs. the older XML-based 2.x format is by magic bytes only (`1F 8B` = gzip
= 3.x; `3C 3F 78 6D 6C` = `<?xml` = 2.x). We only need to *write* 3.x.

Known serialization quirks to preserve byte-for-byte on write (matters
for round-trip diffing / not breaking hardware parsers):

- The misspelling `"poliphony"` at `program.drum.poliphony` must be kept
  as-is; the per-instrument field is spelled correctly (`polyphony`) — see
  the table in §4.0.
- `"EnumCerealisationWrapper(<name>)"` keys wrap certain enum values (seen
  on note events as `"EnumCerealisationWrapper(selectedModifierType)"`,
  and on `midiNoteFilterPipe` as `"EnumCerealisationWrapper(behaviour)"`).
  These are literal key names, parentheses included — copy them from a
  template rather than trying to synthesize them (see §7).
- Numeric values that came from 32-bit floats on the device serialize with
  float32 rounding artifacts (e.g. `93.00003814697266`). Our own written
  values don't need to fake this, but template-derived constants should be
  passed through untouched, not renormalized.
- `"length": 9223372036854775807"` (int64 max) appears as a sentinel for
  "unbounded" on `eventList.length` — leave it untouched when cloning a
  template clip.

### 4.2 On-disk project layout

Per MPC-Tutor and the padbangers/convert.guru conversion tools, a project
is **two things that must travel together**:

```
<ProjectName>.xpj
<ProjectName> [Project Data]/
  Samples/
    <pad-sample-1>.wav
    ...
```

The `.xpj` JSON's sample-pool `path` field (see §4.3) is a filename (plus
extension), resolved relative to the project's `[Project Data]/Samples/`
folder. This matches the user's requested output shape: an `.xpj` file
with a `[Project Data]` folder of WAVs next to it. In 3.x, per
`00-format-reference.md`, "the companion folder contains only `.wav`
sample files" — all other metadata (programs, sequences) lives inside the
single gzipped `.xpj`, unlike the older 2.x format which spread programs
and sequences across separate `.xpm`/`.sxq` files.

**Unverified assumption, needs a hardware/software check (see §11):** the
exact folder-name spelling (`[Project Data]` vs `_[ProjectData]`) and
whether `Samples/` is required as a literal subfolder name or just "some
folder referenced by the sample pool". Treat the produced layout as the
default; make the subfolder name a single constant so it's a one-line fix
if real hardware disagrees.

### 4.3 Relevant JSON schema

Top level (field names and nesting confirmed against `01-project-structure.md`'s
own JSON sample, which matches real project shape):

```
{
  "formatVersion": 2,
  "data": {
    "version": 28,
    "key": "C Major",
    "masterTempoEnabled": false,
    "masterTempo": <float>,
    "engineMode": <int>,
    "currentSequence": 0,
    "currentTrackIndex": 0,
    "tracks": [ ... ],
    "sequences": [ {"key": <int>, "value": {...sequence...}}, ... ],
    "songs": [ ...32 empty {"items": [], "name": "Song N"} slots, plain array, NOT {key,value}-wrapped... ],
    "samples": [ ...project-wide sample pool, union of all track pools... ],
    "mixer": { ... },
    ...~50 more constant global/UI-state keys (quantiser, arpeggiator,
        Q-Link mappings, XY pad modes, locators, etc.) copied verbatim
        from a template — see §7
  }
}
```

Per-track (`data.tracks[n]`), only drum tracks (`program.type == 0`) are
relevant to us. Field names below are as loaded directly from
`examples/track-drum.json`:

```
track = {
  "name": <bank name, e.g. "A">,
  "version": 5,
  "volume": <0.0-1.0, plain float>, "pan": 0.5, "mute": false, "colour": <int>,
  "transposition": 0, "velocityScale": 1.0, "muteGroup": 0,
  "samples": [ ...per-track sample pool, see below... ],
  "program": {
    "version": 4,
    "name": <program/kit name>,
    "type": 0,
    "programPads": { ... },       # pad colour/UI assignment, not audio data
    "mixable": { ... },           # track-level mixer, see §4.3 mixable below
    "padNoteMap": {"noteForPad": {"value0": <note>, ..., "value127": <note>}},
    "drum": {
      "version": <int>, "drumVersion": <int>,
      "instruments": [ ...128 pad slots... ],
      "padGroup": {"value0": 0, ..., "value127": 0},
      "coarseTune": 0, "fineTune": 0, "pitch": 0,
      "monophonic": false, "poliphony": 32,          # NB: typo, see §4.0/§4.1
      "portamentoTime": 0, "portamentoLegato": false,
      "portamentoQuantised": false, "monoRetrigger": false,
      "driftSpeed": <float>, "freeRunningLfoData": [ ... ]
    }
    // ... "customQLinks", "chainID", "midiKillGroup", "base.*" controller
    // assignment fields — all copied verbatim from template, never touched
  }
}
```

Per-instrument (`instruments[i]`, one per pad we use) — field list is the
literal key set of `examples/instrument-drum.json`:

```
instrument = {
  "version": 27,
  "coarseTune": <int, -24..24>, "fineTune": <int, -90..90>,
  "monophonic": <bool>, "polyphony": <int>,          # correctly spelled here
  "lowNote": 0, "highNote": 127,                     # dispatch is by padNoteMap,
                                                      # not by key range — see §5.2
  "ignoreBaseNote": <bool>, "zonePlayTime": <?>,
  "whichMuteGroup": 0..32,
  "muteTargets": [], "simultPlayTargets": [],
  "synthSection": { ...left at template defaults, see §5.4... },
  "triggerMode": 0|1|2,       # One Shot / Note Off / Note On
  "tempo": <float>, "bpmLock": <bool>,
  "warpEnable": <bool>, "stretchPercentage": <float>,
  "layersv": [ <one active layer, 7 unused> ],
  "editAllLayers": false,
  "articulationUseXY": <bool>, "articulations": { ... },
  "userSelectableWarpPoolIndex": <int>,
  "velocityScale": 50..200,
  "chopProperties": { "chopMode": 0, ... },   # left at defaults; no chops
  "layerCrossfade": 0, "layerCrossfadeX": <float>, "layerCrossfadeY": <float>,
  "mixable": {"volume": <float>, "pan": 0.5, "mute": false, "solo": false, ...},
  "padEffects": [],   # explicitly left empty — bus FX not carried over
  "noteCounters": <?>, "modLinks": [ ...32 slots, inactive... ],
  "randomPlaySeed": <int>,
  "midiOutChannel": <int>, "midiOutNote": <int>, "midiOutBehaviour": <?>,
  "partialPresetName": <string>
}
```

Per-layer (`layersv[0]`) — field list is the literal key set of
`instrument-drum.json`'s `layersv[0]`:

```
layer = {
  "active": true,
  "volume": {"gainCoefficient": <float>, "controlValue": <float>, "law": <int>},  # OBJECT, not a float — see §4.0
  "pan": 0.5, "pitch": 0.0, "coarseTune": 0, "fineTune": 0,
  "velocityStart": 0, "velocityEnd": 127,
  "sampleStart": <frames>, "sampleEnd": <frames>,
  "loop": <bool>, "loopStart": <frames>, "loopEnd": <frames>,
  "loopCrossfadeLength": 0, "loopFineTune": 0, "loopMode": 0,
  "mute": false,
  "rootNote": <note>, "keyTrackEnable": false,
  "sampleName": "<display name, no extension>",
  "sampleFile": "<filename with extension>",   # matches sample-pool "path" — see §4.0
  "sliceIndex": 128,   # sentinel for "whole layer region, not a slice" per MPCTK's model.py
  "direction": 0|1,    # forward / reverse
  "offset": 0, "playbackOffset": 0.0,
  "sliceInfo": {                                # NB: PascalCase inner keys, unlike the rest of the schema
    "Start": 0, "End": 0, "LoopStart": 0, "LoopMode": 0,
    "PulsePosition": 0, "LoopCrossfadeLength": -1, "LoopCrossfadeType": 0,
    "TailLength": 0.0, "TailLoopPosition": 0.5, "NumLoopRepeats": 0
  },
  "pitchRandom": 0.0, "VolumeRandom": 0.0, "PanRandom": 0.0, "OffsetRandom": 0.0,  # camelCase/PascalCase mix, confirmed real
  "sliceIncrement": 0, "sliceCycleLength": 128, "sliceIncrementRngSeed": <int>,
  "layerLoopModeOverridesSliceLoopMode": false,
  "quadrantEnabled": {"value0": true, "value1": true, "value2": true, "value3": true}
}
```

Track-level sample pool entry (confirmed against `12-samples.md`'s example
and `track-drum.json`'s actual `samples[0]`):

```
{
  "version": 1, "name": "<pad name, no extension>",
  "path": "<pad-sample-file.wav>", "loadImpl": 0,
  "metadata": {"tempo": <bpm>, "rootNote": 60, "tune": 0.0, "key": ""}
}
```

Sequence (`data.sequences[n].value`), confirmed against
`examples/sequence.json`:

```
{
  "version": 5, "name": "<pattern name, e.g. PTN00001>",
  "bpm": <float>, "tempoEnable": true,
  "lengthBars": <int>, "lengthPulses": <int = lengthBars * beatsPerBar * 960>,
  "loopStartBar": 0, "loopEndBar": <int>, "loop": true,
  "transposition": 0,
  "timeSignatureTrack": {
    "timeSignatures": [ {"beatsPerBar": 4, "beatLength": 960, "barStart": 0} ]
  },
  "trackClipMaps": [ [ {"key": "<track name string>", "value": <clip>}, ... ] ],
  "seqEventList": {},          # always empty; content lives in clips
  "locators": { ... },         # 6 named markers, copy from template
  "loopStartPulses": 0, "loopEndPulses": <int>,
  "autoSelectTrackIndex": -1
}
```

`trackClipMaps` is a doubly-nested array; the outer array is always a
single row for a plain (non-clip-launch) sequence, and each entry in that
row keys by the **track's own `name` string**, not an index — confirmed
directly in `examples/sequence.json` (`"key": "HipHop Bass"`, etc).

Clip (one entry per track that has events in this sequence), confirmed
against the same example:

```
{
  "version": 2, "launchQuantisation": 1,
  "startPulses": 0, "endPulses": <lengthPulses>,
  "loopStartPulses": 0, "loopEndPulses": <lengthPulses>,
  "loop": true, "legato": true, "launch": 0,
  "name": "<clip name>", "colour": 0,
  "eventList": {
    "length": 9223372036854775807,   # int64-max sentinel, leave untouched
    "events": [ ... ],
    "version": 2,
    "quantisation": {"version": 1, "pulses": 0, "swing": 0.0, "strength": 1.0},
    "numFilterTypes": 30
  },
  "perClipParameterValues": { ... }
}
```

Given how much clip-level boilerplate there is (`launchQuantisation`,
`quantisation`, `perClipParameterValues`, etc.), the design in §7 clones an
existing template clip and only overwrites `name`, `startPulses`/`endPulses`,
and `eventList.events`, rather than constructing a clip from a literal dict.

Event, confirmed against `examples/event-note.json`,
`event-automation.json`, `event-audio.json`, and `10-event-types.md`'s own
JSON samples — **the type-specific payload is nested under a key named
after the type**, not flattened onto the event:

```
{
  "version": 2,
  "time": <pulses from clip start>,
  "type": 3,               # 1=track automation, 2=pad automation, 3=note, 4=audio
  "channel": 0,             # always 0 in observed data
  "selected": false, "muted": false, "invented": false,
  "note": {                 # nested; key name matches the event type ("note" for type 3)
    "version": 1,
    "note": <midi note 0-127>,
    "velocity": <0.0-1.0>,
    "length": <pulses>,
    "probability": 100, "ratchet": 1, "articulation": 197,
    "modifierValue0"..."modifierValue15": 0.0,
    "modifierActiveState0"..."modifierActiveState15": false,
    "EnumCerealisationWrapper(selectedModifierType)": "<last-selected modifier name>"
  }
}
```

Pulses use **960 PPQ**; a 4/4 bar is `960 * 4 = 3840` pulses (confirmed:
`09-sequences-events.md`'s own conversion table, and `16 bars * 4 * 960 =
61440` matching `sequence.json`'s `lengthPulses`). Since the SP404 bar
grid is 1920 ticks per bar (§3.2), the tick→pulse scale factor is a clean
**×2**.

## 5. Mapping strategy

### 5.1 Bank → track/program (the 160-pad vs. 128-slot problem)

An SP404mk2 project has 10 banks (`A`..`J`) × 16 pads = 160 pads. A single
MPC drum program has 128 instrument slots — this ceiling is corroborated
independently by MPCTK's own addressing helper
(`src/mpctk/generation/pads.py`): `BANK_NAMES = tuple("ABCDEFGH")` (8
letter-banks of 16 pads = 128), which is how a *real* MPC-side tool
addresses pads within one drum program. Two options were considered:

1. Pack all 160 pads into as few drum programs as possible using
   MPC-style letter-bank addressing (2 programs of 80, or similar),
   splitting SP404 banks across programs.
2. **One SP404 bank = one MPC track, each with its own drum program using
   16 of its 128 instrument slots.**

Option 2 is the design choice, because:

- It's a 1:1, order-preserving mapping — no cross-bank slot arithmetic,
  easy to reason about and to reverse for debugging.
- The SP404 already has 10 banks — more than MPC's own 8 letter-banks per
  program — so packing into a *single* program was never going to be a
  clean fit anyway; splitting by SP404 bank sidesteps that mismatch
  entirely instead of picking an arbitrary repacking scheme.
- Per-bank BPM (`Project.bank_bpms`) maps naturally onto one tempo/warp
  reference per track instead of needing to be reconciled per-instrument
  within a shared program.
- Mute groups and pad links are scoped per bank on the SP404 UI already;
  keeping each bank as its own program keeps that scoping intact instead
  of guessing whether it was ever meant to apply across banks.
- 10 tracks is trivial for MPC Live III / MPC Sample (limits are in the
  hundreds of tracks).

Each track is named after its bank letter (`A`..`J`) and only created if
at least one pad in that bank has a non-empty `name` (mirrors the "empty
banks are skipped" behavior already used in `sp404_padconf.py`). The
track's `name` field is also what `trackClipMaps` keys against (§4.3), so
this naming choice doubles as the join key between sequences and tracks —
no separate index bookkeeping needed.

### 5.2 Pad → instrument slot & MIDI note

Within a bank's drum program, pad `n` (1-indexed, 1..16) maps to
instrument slot `n - 1` and MIDI note `36 + n` (i.e. notes 37..52). This
is a deliberately simple, sequential scheme — not an attempt to match
MPC's own factory default `padNoteMap` (which, per the real
`track-drum.json` example, uses a scattered GM-style layout like
`36, 37, 42, 82, 40, 38, 46, 44, ...` for a standard acoustic kit). That
default is irrelevant to us: `padNoteMap` is fully data-driven per
project, and dispatch of an incoming note to a pad/instrument goes through
`padNoteMap`, not through each instrument's own `lowNote`/`highNote` range
— real drum instruments are observed with `lowNote: 0, highNote: 127`
(the full range) and rely on `padNoteMap` for routing. So `lowNote`/
`highNote` can be left at the template default (0–127) for every
instrument we populate; only `padNoteMap` needs per-pad values.

`padNoteMap.noteForPad` is populated with `value(n-1) = 36 + n` for the 16
used slots; unused slots (pads 17..128) keep whatever the template
provides.

### 5.3 Pattern → sequence

One `PTN#####.BIN` file → one MPC sequence, in file order. Sequence name
is derived from the pattern's file index (`PTN00001` → `A01`-style pattern
names aren't recoverable from the `.BIN` itself — see §11 — so the numeric
`PTN#####` id is used as the sequence name unless/until a better source is
found, e.g. the companion `P08-PTN#####.txt` scratch files are debug
dumps, not shipped project data, and won't exist in a real export).

For each event in the pattern (after the `sp404.ptn` extensions in §3.2):

1. Resolve `pad_id.name` (e.g. `"B07"`) to a bank letter (`B`) and local
   pad number (`7`).
2. Look up that bank's track by **name** (the letter itself, since
   `trackClipMaps` keys by track name, not index — §4.3, §5.1). Skipped
   empty banks simply have no corresponding entry.
3. Emit a type-3 note event into that track's clip for this sequence,
   following the nested event shape from §4.3 (`{"type": 3, "time": ...,
   "note": {...}}`, not a flat dict):
   - `time` = `absolute_tick * 2` (§4.3 scale factor)
   - `note.note` = `36 + local_pad_number` (§5.2)
   - `note.velocity` = `event.velocity / 127.0`
   - `note.length` = `(gate_ticks + 1) * 2`, falling back to a one-bar
     default (`3840`) when the pad's trig mode is `ONE_SHOT` and gate
     length is meaningless (SP404 one-shots always play to completion
     regardless of recorded gate length).
   - `note.probability = 100`, `note.ratchet = 1`,
     `note.articulation = 197` — all observed as fixed/constant values
     across the real corpus, so this is not an approximation.
   - All 16 modifier slots and the
     `"EnumCerealisationWrapper(selectedModifierType)"` key are copied
     from a template note event (§7) and left untouched — no SP404
     equivalent, and this key must exist with *some* value for the file
     to round-trip safely.
4. Per-event chromatic pitch (§3.2 byte 3) is **not** applied in the first
   version. Given §5.2's finding that drum dispatch goes through
   `padNoteMap` rather than per-instrument key ranges, a semitone-style
   per-event transposition isn't a natural fit for this schema the way it
   would be for a keygroup/melodic program; the more plausible mechanism
   (a note modifier slot, or a duplicate `padNoteMap` entry) needs
   confirming on real hardware first. Logged as a lossy-conversion warning
   instead of silently dropped, so users know it happened (see §11).

`lengthBars` / `loopEndBar` for the sequence come from the pattern
footer (§3.2).

### 5.4 Field mapping tables

**Pad → MPC instrument**

| SP404 (`sp404.padconf.Pad`) | MPC field | Notes |
|---|---|---|
| `vol` (0-127) | `instruments[i].mixable.volume` | `vol / 127.0` — `mixable.volume` is a plain float (§4.0), unlike layer volume |
| `gate` (bool) | `instruments[i].triggerMode` | `True` → `1` (Note Off / gated); `False` → `0` (One Shot), unless `trig_mode` has `LOOP` (below) |
| `TrigMode.ONE_SHOT` in `trig_mode` | `instruments[i].triggerMode` | forces `0` regardless of `gate` |
| `TrigMode.LOOP` in `trig_mode` | `layersv[0].loop` | `True`; see loop row below |
| `TrigMode.FIXED_VELOCITY` in `trig_mode` | *(no direct MPC field)* | approximate by setting the instrument's `velocityScale` to flatten dynamics; flagged as best-effort in §11 |
| `mute_group` (`Bank` enum) | `instruments[i].whichMuteGroup` | `NONE`→`0`, `A`..`J`→`1..10` (bank-local numbering is fine since mute groups are scoped per program already) |
| `pad_link` (`Bank` enum) | `instruments[i].simultPlayTargets` | best-effort; SP404 pad-link semantics aren't fully reverse-engineered (§11) — mapped as "also trigger the linked pad's slot" |
| `bpm_sync` (bool) | `instruments[i].bpmLock` / `warpEnable` | direct |
| `bpm` (float) | `instruments[i].tempo` | direct |
| `time_stretch_perc` (%, 100=normal) | `instruments[i].stretchPercentage` | direct — both are already percentages (100=no change), no unit conversion needed. Formerly mapped to `coarseTune`/`fineTune` under the (incorrect) name `pitch_perc`; see §3.4/§11 |
| `pitch_coarse` / `pitch_fine` (semitones/cents) | `instruments[i].coarseTune` / `fineTune` | direct, but clamp to MPC's real limits: `[-24, 24]` semitones, `[-90, 90]` cents — confirmed hardware limits from MPCTK's `COARSE_TUNE_MIN/MAX`, `FINE_TUNE_MIN/MAX`. SP404's own range is narrower (`-12..12` semitones, `-100..100` cents per the external RE project), so it always fits without clamping in practice; not yet verified against a real non-zero value on hardware — see §11 |
| `chromatic` (`MONO`/`LEGATO`/`POLY`) | *(program-level `drum.monophonic`/`drum.poliphony`, not per-pad — see §4.3)* | approximate at the whole-track level using the pad's own value if pads disagree within a bank, log a warning (§11) |
| `play_mode` (`FORWARD`/`REVERSE`/`FWD_PINGPONG`/`REV_PINGPONG`) | `layersv[0].direction` | `FORWARD`→`0`, `REVERSE`/`REV_PINGPONG`→`1`; ping-pong itself has no documented MPC layer field, so it degrades to plain forward/reverse with a logged warning |
| `bus_fx` | *(dropped)* | explicitly out of scope |
| `name` | sample-pool `name`, `layersv[0].sampleName` | display name, no extension |
| `sample_start` / `sample_end` | `layersv[0].sampleStart` / `sampleEnd` | direct, in frames — no physical audio trimming (§5.5) |
| `loop_start` | `layersv[0].loopStart` | direct; `loopEnd` = `sample_end` |
| `markers` | *(ignored)* | see §5.5 |

Note the two distinct layer fields from §4.0/§4.3: `sampleName` (display
name, no extension) is set from `pad.name`; `sampleFile` (filename with
extension) is set from the WAV filename we write and must match the
sample-pool `path` — these are **not** the same field, unlike what the
`12-samples.md` prose claims.

**Pattern event → MPC note event**: see §5.3 (table form would just repeat
that list).

**Project → MPC project**

| SP404 | MPC field |
|---|---|
| `Project.project_name` | used to name the `.xpj` and the `[Project Data]` folder |
| `bank_bpms[letter]` | per-track `program.drum.instruments[*].tempo` default, and the *first* bank's BPM seeds `data.masterTempo` |

### 5.5 Sample handling: no physical trimming, no chop reproduction

Each pad's `.SMP` region is decoded to a **full WAV** covering the whole
underlying sample as stored on the SP404 (see §3.3), and `sample_start`
/`sample_end` are carried over as MPC layer trim points rather than
physically cutting the audio. This:

- Avoids re-deriving audio boundaries by hand (fewer opportunities to
  introduce off-by-one errors versus the already-verified
  `sample_start`/`sample_end` math in `sp404.padconf.Pad`).
- Matches the instruction to treat every pad as one sample: the SP404's
  internal chop markers (`pad.markers`) are read but not translated into
  MPC "slices" — each pad still becomes exactly one instrument with one
  layer, and `layersv[0].sliceIndex` stays at its template default
  (`128`, the "whole layer region, not a slice" sentinel per MPCTK's
  `model.py`).
- Leaves the door open for a later "slices" mode without re-decoding
  audio, if that's ever wanted.

If two pads reference the exact same underlying `.SMP` file (same
`SMPL/BANK<n>-<m>.SMP`, different start/end), they are still decoded once
and written once, and both pads' layers point at the same sample-pool
`path` (via their own `sampleFile`) with their own `sampleStart`/
`sampleEnd` — mirroring the SP404's own "shared sample buffer" model and
avoiding duplicate WAV files.

## 6. SMP → WAV conversion

New helper, `convert/xpj/wav.py`:

1. Use `sp404.smp.Sample` to get `samplerate`, `mode`, `size`.
2. Re-open the file, seek to `0x200`, read the remainder.
3. Reinterpret as big-endian `int16` (mono) or interleaved L/R big-endian
   `int16` pairs (stereo), byte-swap to little-endian.
4. Write a canonical 16-bit PCM WAV via Python's `wave` module (or manual
   RIFF header) with `nchannels = mode.value`, `sampwidth = 2`,
   `framerate = samplerate`.

This is a straight, small module — the byte-swap approach in
`testing/SP404mk2/mk2_notes.txt` (from earlier research with numpy) is
correct in spirit but hardcodes 44100/mono; the real implementation reads
rate/mode from `Sample` instead of hardcoding them, and only needs
`struct`/`wave`/`array`, no numpy dependency, to stay consistent with the
project's existing minimal-dependency style (`requirements.txt` currently
only needs `pyyaml`).

## 7. XPJ generation approach: template + mutate, not build-from-scratch

`kurtjcu`'s own documentation notes ~120 undocumented/unexplained fields
in the full schema, and MPC-Sample-Toolkit reaches the same conclusion in
practice: its `Layer`/`Track`/`SliceInfo` dataclasses (`src/mpctk/xpj/model.py`)
each carry a catch-all `raw_data: dict[str, Any]` field precisely so that
any key the tool doesn't explicitly model round-trips untouched. We follow
the same principle, at two levels:

1. **Capture a template project once**: save an empty project with 10
   empty drum tracks (named `A`..`J`) from real MPC Sample or MPC Live III
   software, export the `.xpj`, gunzip it, and check the raw JSON into
   `convert/xpj/template/empty_project.json` (plus the 5 header lines in a
   small sidecar, e.g. `empty_project.header.txt`).
2. **Capture a template note event, separately**: place a single note in
   the grid on one of those tracks, save, and extract that one event
   object into `convert/xpj/template/note_event.json`. Every note event we
   generate is a deep copy of this template with only `time`, `note.note`,
   `note.velocity`, and `note.length` overwritten — this is what
   guarantees the 16 modifier slots and the
   `"EnumCerealisationWrapper(selectedModifierType)"` key (§4.1, §5.3) are
   always present and valid without us having to hand-author them.
3. At convert time: load the project template JSON, then only mutate the
   fields this design actually maps (§5.4) — tracks'
   `program.drum.instruments`, `program.padNoteMap`, track/sample pool
   entries, and `sequences` (built from cloned template clips, §4.3).
   Every constant/UI-state key (Q-Link mappings, quantiser defaults, XY
   pad modes, locators, etc., see §4.3) passes through untouched.
4. Re-serialize: JSON-encode, prepend the 5 header lines + a newline,
   gzip, write to `<ProjectName>.xpj` — matching MPCTK's own writer
   exactly (§4.1).

This bounds the risk of "hardware refuses to load the file because of a
missing undocumented field" to whatever was already present in a
hardware-saved template, rather than to gaps in the reverse-engineered
spec.

## 8. Proposed module layout

```
convert/
  xpj/
    DESIGN.md              (this file)
    __init__.py
    template/
      empty_project.json       # captured from real MPC software, see §7
      empty_project.header.txt
      note_event.json          # captured from real MPC software, see §7
    model.py               # intermediate representation: Bank, PadSlot,
                            # PatternEvent-with-absolute-tick, decoupled
                            # from both sp404's raw structs and MPC's JSON
    mapping.py             # the tables in §5.4 as data + pure functions
    wav.py                 # SMP -> WAV (§6)
    writer.py              # template loading, JSON mutation, gzip/header
                            # framing, on-disk [Project Data] layout (§4.2)
    convert.py             # top-level orchestration: read sp404 export,
                            # build model.py objects, call writer.py
```

`sp404/ptn.py` gains the `absolute_tick`/`gate_ticks` extensions from
§3.2 in place — `convert/xpj` should not re-implement pattern parsing.

A CLI entry point at the repo root, consistent with the existing
`sp404_padconf.py` / `sp404_smp.py` / `sp404_ptn.py` scripts:

```
sp404_to_xpj.py <path-to-export-folder> <output-folder> [--project-name NAME]
```

## 9. Output layout produced by the converter

```
<output-folder>/
  <ProjectName>.xpj
  <ProjectName> [Project Data]/
    Samples/
      A01 - <pad name>.wav
      A02 - <pad name>.wav
      ...
```

One WAV per unique underlying sample buffer (§5.5), named from the pad's
`name` field with the originating pad prefixed for readability and
collision-avoidance. The WAV's filename (with extension) is what gets
written into both the sample-pool `path` and the layer's `sampleFile`
(§4.0, §5.4) — not `sampleName`, which stays as the plain display name.

## 10. Validation & test strategy

- **Unit tests** (extend `tests/`): tick-accumulation and gate-length
  decoding in `sp404/ptn.py` against the known-good hex dumps already in
  `testing/SP404mk2/PTN.txt` and the `PTN/PTN0000*.BIN` fixtures; SMP→WAV
  byte-swap correctness against a short synthetic `.SMP`.
- **Golden-file test** for `writer.py`: convert one of the fixture
  exports (`testing/SP404mk2/pad-sequencer/2026-04-08/`) and diff the
  produced JSON against a checked-in expected output, so regressions in
  field mapping are caught without needing hardware.
- **Manual hardware/software validation checklist** (required before
  calling this done, since several assumptions in §11 can only be
  confirmed this way):
  1. Load the produced `.xpj` in MPC Sample or MPC Live III software.
  2. Confirm all 10 (or fewer) tracks appear with correct sample
     assignments and pad volumes.
  3. Play each sequence, confirm note timing/velocity matches the
     original SP404 pattern by ear against a recording from the SP404.
  4. Confirm `[Project Data]/Samples` folder name and relative path
     resolution actually works when the project folder is moved/copied.

## 11. Open questions / risks

- **`[Project Data]` folder naming** (§4.2) — only sourced from
  documentation, not a hardware-saved example. Verify against a real save
  before shipping.
- **`pad_link` semantics** (§5.4) — `sp404.padconf.Pad.pad_link` is
  decoded as a bank value, but its runtime behavior (choke vs. simultaneous
  trigger vs. something else) isn't confirmed in `testing/SP404mk2/*.txt`.
  Mapped as best-effort `simultPlayTargets`; revisit once confirmed.
- **Pitch coarse/fine now exposed, but unverified against hardware**
  (§3.4, §5.4) — `sp404.padconf.Pad.pitch_coarse`/`pitch_fine` (words 13/14)
  are now read using a new signed-big-endian helper
  (`spr.read_slong_b`), since every other `Pad` field is unsigned. Every
  pad in the `pad-params/PADCONF.BIN` fixture reads `0` for both, so the
  signed decoding path (negative values) has not actually been exercised
  against a real captured value yet — worth a targeted test once a
  fixture with a non-zero pitch setting exists.
- **`chromatic` (mono/legato/poly) is per-pad on the SP404 but per-program
  on the MPC drum object** (`program.drum.monophonic`/`poliphony`, §4.3,
  §5.4) — needs a policy for banks whose pads disagree (majority vote?
  last-wins? per-instrument override, if one exists and wasn't
  documented?). Note `poliphony` is the drum-program-level field name
  (typo preserved); the per-instrument field is spelled correctly
  (`polyphony`) but its effective role in mono/poly behavior for drum
  programs specifically (as opposed to keygroups) isn't confirmed.
- **Ping-pong playback modes** have no documented MPC layer field —
  confirm whether newer firmware added one before accepting the
  forward/reverse degradation in §5.4.
- **Per-event chromatic pitch** (§3.2 byte 3, §5.3 step 4) is decoded but
  not applied in v1. Given dispatch happens via `padNoteMap` rather than
  per-instrument key ranges (§5.2), note-transposition is not obviously
  the right mechanism the way it would be for a keygroup; a note modifier
  slot is more plausible but unconfirmed. Decide once basic playback is
  validated on hardware.
- **Sequence names**: `PTN#####.BIN` carries no human-readable name in the
  binary itself; confirm there isn't a name stored elsewhere in the export
  (e.g. an index file not yet seen in the test fixtures) before settling
  on numeric names.
- **`FIXED_VELOCITY` trig mode** has no direct MPC instrument-level
  equivalent found in the schema so far; current plan approximates via
  `velocityScale`, needs confirming this actually flattens dynamics the
  same way on MPC.

## 12. Code style

New code in `convert/xpj/` and the `sp404_to_xpj.py` CLI should read like
it belongs next to the existing `sp404/` package, not like a separate
project bolted on. Concretely, follow `sp404/padconf.py`, `sp404/smp.py`,
and `sp404/ptn.py` — **not** the ad-hoc scripts under `testing/wav/`
(those are one-off Gemini-assisted scratch scripts used during research,
not maintained code, and their style — type hints, argparse-less
`if __name__` blocks with hardcoded config constants, heavier commenting —
should not be copied).

Observed conventions to match:

- **No type hints.** None of `sp404/padconf.py`, `sp404/smp.py`, or
  `sp404/ptn.py` use `typing` annotations anywhere, including on
  constructors. New modules (`wav.py`, `mapping.py`, `model.py`,
  `writer.py`, `convert.py`) should follow suit for consistency, even
  though other tools researched for this design (MPCTK) do use them
  heavily — that's their convention, not this repo's.
- **Class shape: public class, private `_read`.** `Project`, `Sample`,
  and `Pattern` are all constructed with a file path, and immediately call
  a private `_read(self, file_path)` that does the actual parsing inside
  `with open(file_path, 'rb') as f:`. Mirror this for anything that reads
  a file: e.g. a `wav.py` writer function takes a `Sample`-like input and
  a destination path, and does the work in one pass without a separate
  "load into memory, then process" split unless the data genuinely needs
  two passes (as `Pattern` currently does for its footer).
- **`IntEnum` for closed vocabularies, with a `parse()` staticmethod when
  raw-value decoding needs logic.** See `padconf.py`'s `Bank`, `BusFX`,
  `Chromatic.parse()`, `TrigMode.parse()`, `PlayMode.parse()`. Any new
  fixed vocabulary introduced for the XPJ side (e.g. `TriggerMode` for
  MPC's One Shot/Note Off/Note On, if it's worth modeling as an enum
  rather than a plain int) should follow the same shape: the enum owns its
  own decode/encode logic as a `parse()`/`to_sp404()`-style staticmethod,
  not a free function elsewhere.
- **Minimal, targeted docstrings.** One-line class/module docstrings only
  where the name doesn't already say enough (`"""Represents a single event
  within an SP404mk2 pattern"""`). No multi-paragraph docstrings, no
  per-parameter `:param:` blocks.
- **Comments explain provenance/confidence, not mechanics.** E.g.
  `padconf.py`'s `# verified in sp404 app, sample start and end match`.
  When writing the XPJ mapping code, comment *which field mappings are
  confirmed vs. best-effort* (cross-reference §11) rather than restating
  what the code obviously does.
- **Fail loud on malformed input.** `raise ValueError(...)` with a
  specific message on a bad magic number, wrong length, or out-of-range
  value (see `smp.py`'s samplerate check, `ptn.py`'s length checks,
  `padconf.py`'s magic check). No broad `try/except` swallowing errors.
- **No `print()` in library code.** `sp404/*.py` never prints; formatting
  and display are the CLI wrapper's job. `writer.py`/`convert.py` should
  return data (or write the files they're asked to write) and let
  `sp404_to_xpj.py` be the only place that prints anything.
- **CLI wrapper shape**, matching `sp404_padconf.py`/`sp404_smp.py`/
  `sp404_ptn.py`: `import sys`, argv-length check with a `Usage: ...`
  message and `sys.exit(1)` on failure, then do the work and print a
  plain summary. Those three scripts print a `yaml.dump(..., default_flow_style=False,
  sort_keys=False)` of the parsed data since their job is "dump structured
  data for a human to read." `sp404_to_xpj.py`'s job is "write files," so
  it should print a short plain-text or YAML summary of what was written
  (project name, track count, sequence count, sample count, output paths)
  in the same spirit, not silently exit 0.
- **No new dependencies.** `requirements.txt` currently only needs
  `pyyaml` (for the CLI scripts' output formatting). Everything the XPJ
  converter needs — `gzip`, `json`, `struct`, `wave`, `array` — is stdlib.
  Don't add `numpy` or anything else; §6 already flags this specifically
  for the WAV conversion, but it applies to the whole package.
- **Tests**: one `unittest.TestCase` file per module under `tests/`,
  matching `tests/test_ptn.py`'s shape — plain `self.assertEqual`/
  `self.assertRaises`, a one-line docstring per test method describing
  what's being verified, no pytest fixtures or parametrization (the
  project doesn't depend on pytest).
- **Module-level constants in ALL_CAPS**, e.g. `padconf.py`'s `BANKS`,
  `EMPTY_MARKER`; `ptn.py`'s `_PADS`. Leading underscore for
  module-private constants not meant to be imported (`_PADS`), no
  underscore for ones that are part of the public surface (`BANKS`).

## 13. Phased implementation plan

1. Extend `sp404/ptn.py` with absolute-tick accumulation, gate-length and
   per-event chromatic-pitch decoding, filler filtering (§3.2). Add unit
   tests against existing fixtures.
2. Capture the empty-project XPJ template and the template note event
   from real MPC software (§7). This unblocks all JSON-shape work and
   should happen early since everything else depends on it.
3. Build `wav.py` (§6) and validate output WAVs play correctly and match
   the SP404 app's own export/preview audio.
4. Build `mapping.py` + `model.py`: pure, testable transforms from
   `sp404` objects to an intermediate model, independent of JSON shape.
5. Build `writer.py`: template mutation + gzip/header framing + on-disk
   layout (§4.2, §9).
6. Wire up `convert.py` + `sp404_to_xpj.py` CLI.
7. Run the manual validation checklist (§10) on real MPC hardware/software
   and fold in whatever §11 questions get resolved.

## References

- [kurtjcu/MPC-project-file-definitions](https://github.com/kurtjcu/MPC-project-file-definitions) — primary XPJ format reference used throughout §4; treat its example JSON files as higher-confidence than its prose (§4.0).
- [tarikcampos/MPC-Sample-Toolkit](https://github.com/tarikcampos/MPC-Sample-Toolkit) — existing open-source XPJ generator (WAV → MPC Sample); confirmed the template-based generation approach in §7 and independently verified several field names/shapes in §4.0.
- [Duffman007/MPC2Live](https://github.com/Duffman007/MPC2Live) — existing open-source XPJ reader (XPJ → Ableton Live).
- [MPC-Tutor: MPC X, MPC One & MPC Live Projects — The Complete Lowdown](https://www.mpc-tutor.com/mpc-x-mpc-live-projects-lowdown/) — on-disk project/`[Project Data]` folder layout, §4.2.
- `testing/SP404mk2/PTN.txt`, `PADCONF.txt`, `SMPL.txt`, `mk2_notes.txt` — this repo's own SP404mk2 reverse-engineering notes, primary source for §3.
- Credited in this repo's `README.md`: [NearTao](https://neartao.com/) / [gsterlin/sp404mk2-tools](https://github.com/gsterlin/sp404mk2-tools) for the original SP404mk2 PADCONF/PTN reverse engineering this project builds on.
