"""
Converts an SP404mk2 project export into an MPC XPJ project.
See convert/xpj/DESIGN.md for the full design and open questions.
"""

import argparse
import logging
import os
import sys

# repo root, so `sp404` (a sibling of this file's own `convert/` folder)
# is importable regardless of the current working directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xpj.convert import convert_project


def main():
    parser = argparse.ArgumentParser(
        description="Convert an SP404mk2 project export (PADCONF.BIN, SMPL/, PTN/) "
                    "to an MPC XPJ project (.xpj + [Project Data]/Samples/).")
    parser.add_argument("source", help="folder containing the SP404mk2 export")
    parser.add_argument("destination", help="folder to write the MPC project into")
    parser.add_argument("--project-name",
                        help="override the MPC project name (defaults to the SP404 project name)")
    parser.add_argument("--dry", action="store_true",
                        help="only verify and log what would be converted; write nothing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    padconf_path = os.path.join(args.source, "PADCONF.BIN")
    if not os.path.isfile(padconf_path):
        parser.error(f"{args.source} does not contain a PADCONF.BIN")

    convert_project(args.source, args.destination,
                     project_name=args.project_name, dry_run=args.dry)


if __name__ == "__main__":
    main()
