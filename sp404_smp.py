import sys
import yaml
from sp404.smp import Sample

def main():
    """
    Main entry point for the SP-404 SMP file metadata extractor.
    Parses the provided .smp file and prints its properties in YAML format.
    """
    if len(sys.argv) < 2:
        print("Usage: python sp404_smp.py <path_to_file.smp>")
        sys.exit(1)

    sample = Sample(sys.argv[1])
    
    print(yaml.dump({
        'samplerate': sample.samplerate,
        'mode': sample.mode.name,
        'size': sample.size
    }, default_flow_style=False))

if __name__ == "__main__":
    main()
