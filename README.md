# UGC-TOOLS

Universal Groovebox Conversion Tools. This project contains tools for parsing and converting audio and/or project files related to the [M8](https://dirtywave.com/), [SP404mk2](https://www.roland.com/nl/products/sp-404mk2/), [MPC](https://www.akaipro.com/products/collections/mpc/) and other grooveboxes.

⚠️ At the moment this project is very much **a work in progress**, and I am only working on it slowly as time, energy or creativity allows. Please see the [CONTRIBUTING.md](CONTRIBUTING.md) if you are interested in helping out!

## Goal 

This project is created with the goal of converting to / from different groovebox formats, and extracting or offering samples. If the time comes maybe also manipulating the project files outside the grooveboxes themselves.

For example, extracting the pattern info and samples directly from a SP404mk2 project file

## Roadmap

Things I want to eventually accomplish (will most likely change over time)

- [ ] SP404mk2
  - [x] Write parser for SP404mk2 PADCONF.BIN format (banks, start / end, play modes)
  - [ ] Write parser for .SMP file (extract chop points, sample data, etc.)
  - [ ] Write parser for .PTN file (extract sequence information)
- [ ] MPC (MPC Sample / Live III)
  - [ ] Figure out the XPJ format
  - [ ] ...
- [ ] M8
  - [ ] Parse M8 project file
  - [ ] ...
- [ ] Convert SP404mk2 project to MPC Projects
- [ ] Convert SP404mk2 chop points or several pad to M8


## Structure

- contrib 
  - wxPatternEditor, created by [u/BlueSGL](https://www.reddit.com/user/blueSGL/), see [reddit post](https://www.reddit.com/r/SP404/comments/1r9jfhw/pattern_editor_script_for_sp404mk2_alter/)
- sp404 
  - smp.py (import for .SMP file parsing)
  - padconf.py (import for PADCONF.BIN file parsing)
- testing 
  - M8 (research to M8 format files)
  - SP404mk2 (research to SP404mk2 format files)
  - wav (research to wav file structure)
- sp404_smp.py - example tool reading SMP files
- sp404_padconf.py - example tool reading PADCONF files


## Installation

Before you can run the scripts, you need to install the required Python packages. 
It's recommended to set up a virtual environment.

```bash
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
```

Then install the required packages:

```bash
pip install -r requirements.txt
```

## Usage

The module directories can be used directly by just copying the files over, I will eventually make a pip installable package if needed. For now just copy the directory and use it like this:

```python
import sys
import yaml
from sp404.smp import Sample

def main():

    sample = Sample(sys.argv[1])
    
    print(yaml.dump({
        'samplerate': sample.samplerate,
        'mode': sample.mode.name,
        'size': sample.size
    }, default_flow_style=False))

if __name__ == "__main__":
    main()

```

### Example(s)

You can run the provided scripts from the command line on your project files. For instance, to dump the pad configuration of a given `PADCONF.BIN` file:

```bash
python sp404_padconf.py testing/SP404mk2/pad-params/PADCONF.BIN
```
Which will produce the following:

````yaml
project_name: PROJECT_16
banks:
  bank_A:
    bpm: 90.0
    pads:
      pad_1:
        name: 001 short hendry - 5PLH
        sample_start: 0
        sample_end: 19178
        vol: 127
        gate: true
        mute_group: NONE
        pad_link: NONE
        bpm_sync: false
        bpm: 90.0
        loop_start: 0
        play_mode: FORWARD
        trig_mode:
        - FIXED_VELOCITY
        bus_fx: BUS_1
        chromatic: MONO
        pitch_perc: 100.0
      pad_2:
        name: 001 short hendry - 5PLH
        sample_start: 0
        sample_end: 19178
        vol: 127
        gate: true
        mute_group: NONE
        pad_link: NONE
        bpm_sync: false
        bpm: 90.0
        loop_start: 0
        play_mode: FORWARD
        trig_mode:
        - LOOP
        bus_fx: BUS_1
        chromatic: MONO
        pitch_perc: 100.0
      pad_3:
        name: 001 short hendry - 5PLH
        ...
````

## Credits

- Thank you [NearTao](https://neartao.com/) for doing the grunt of the work for the SP404mk2 reverse engineering
  - [NearTao youtube channel](https://www.youtube.com/neartao)
  - [Github repository](https://github.com/gsterlin/sp404mk2-tools) 
- Thank you [u/BlueSGL](https://www.reddit.com/user/blueSGL/) for making the pattern editor script (see **contrib** below)


## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
