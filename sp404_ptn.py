import sys
import yaml
from sp404.ptn import Pattern, PadID

def main():
    if len(sys.argv) < 2:
        print("Usage: python sp404_ptn.py <path_to_pattern.bin>")
        sys.exit(1)

    pattern = Pattern(sys.argv[1])

    pattern_data = {
        'events': []
    }

    for event in pattern.events:

        event_info = {
            'pad': event.pad_id.name if event.pad_id else "...",
            'time': event.note_offset,
            'velocity': event.velocity
        }
        pattern_data['events'].append(event_info)

    if pattern.footer:
        pattern_data['footer'] = pattern.footer.hex()

    print(yaml.dump(pattern_data, default_flow_style=False, sort_keys=False))


if __name__ == "__main__":
    main()
