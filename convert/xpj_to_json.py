"""
Extracts an MPC XPJ project back to readable JSON, so converter output can be
diffed against projects that are known to load on real hardware.
See convert/xpj/DESIGN.md sections 4.1 and 7.
"""

import argparse
import os
import sys

# repo root, so `sp404` (imported by the xpj package's __init__) is importable
# regardless of the current working directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xpj import reader


def main():
    parser = argparse.ArgumentParser(
        description="Extract one or more MPC .xpj projects to pretty-printed JSON "
                    "(<name>.json) plus the container header lines (<name>.header.txt).")
    parser.add_argument("sources", nargs="+", help=".xpj file(s) to extract")
    parser.add_argument("--output-dir",
                        help="folder to write into (defaults to next to each .xpj)")
    args = parser.parse_args()

    failed = False
    for source in args.sources:
        stem = os.path.splitext(os.path.basename(source))[0]
        output_dir = args.output_dir or os.path.dirname(os.path.abspath(source))
        json_path = os.path.join(output_dir, f"{stem}.json")
        header_path = os.path.join(output_dir, f"{stem}.header.txt")

        try:
            header_lines, project_data = reader.read_project(source)
        except (OSError, ValueError) as e:
            print(f"{source}: {e}", file=sys.stderr)
            failed = True
            continue

        os.makedirs(output_dir, exist_ok=True)
        with open(json_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(reader.to_json_text(project_data))
        with open(header_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write("\n".join(header_lines) + "\n")

        data = project_data.get("data", {})
        print(f"{source}")
        print(f"  header:    {' | '.join(header_lines)}")
        print(f"  tracks:    {len(data.get('tracks', []))}")
        print(f"  sequences: {len(data.get('sequences', []))}")
        print(f"  samples:   {len(data.get('samples', []))}")
        print(f"  wrote:     {json_path}")
        print(f"             {header_path}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
