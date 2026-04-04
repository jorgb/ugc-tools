import sys
import yaml
from sp404.padconf import Project, BANKS

def main():
    if len(sys.argv) < 2:
        print("Usage: python sp404_padconf.py <path_to_padconf.bin>")
        sys.exit(1)

    project = Project(sys.argv[1])
    
    project_data = {
        'project_name': project.project_name,
        'banks': {}
    }
    
    for bank_idx, bank_name in enumerate(BANKS):
        bank_data = {
            'bpm': project.bank_bpms.get(bank_name, 0.0),
            'pads': {}
        }
        
        # There are 16 pads per bank
        start_idx = bank_idx * 16
        end_idx = start_idx + 16
        
        for pad in project.pads[start_idx:end_idx]:
            # Assuming a pad is empty if it has no name
            if pad.name and pad.name.strip():
                # Normalize pad_nr (1-16) within the bank
                local_pad_nr = ((pad.pad_nr - 1) % 16) + 1 
                
                pad_info = {
                    'name': pad.name,
                    'sample_start': pad.sample_start,
                    'sample_end': pad.sample_end,
                    'vol': pad.vol,
                    'gate': pad.gate,
                    'mute_group': pad.mute_group.name,
                    'pad_link': pad.pad_link.name,
                    'bpm_sync': pad.bpm_sync,
                    'bpm': pad.bpm,
                    'loop_start': pad.loop_start,
                    'play_mode': pad.play_mode.name,
                    'trig_mode': [tm.name for tm in pad.trig_mode],
                    'bus_fx': pad.bus_fx.name,
                    'chromatic': pad.chromatic.name,
                    'pitch_perc': pad.pitch_perc,
                }
                
                if pad.markers:
                    pad_info['markers'] = pad.markers
                
                bank_data['pads'][f'pad_{local_pad_nr}'] = pad_info
                
        # Only add the bank to the output if it has any non-empty pads
        if bank_data['pads']:
            project_data['banks'][f'bank_{bank_name}'] = bank_data

    print(yaml.dump(project_data, default_flow_style=False, sort_keys=False))


if __name__ == "__main__":
    main()
