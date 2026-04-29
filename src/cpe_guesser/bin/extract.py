import argparse
import sys

from cpe_guesser.cpeimport.reader.generic import GenericCPEReader


def main():
    parser = argparse.ArgumentParser(
        description="Extract unique CPE based on regex from any input text"
    )

    parser.add_argument(
        "CPE_FILES", type=str, nargs="+", help="Text file containing CPE data"
    )

    args = parser.parse_args()

    for cpe_file in args.CPE_FILES:
        if cpe_file == "-":
            reader = GenericCPEReader("stdin", stream=sys.stdin)
        else:
            reader = GenericCPEReader(cpe_file)

        for cpe in reader.find_all_cpe_str():
            print(f"{cpe}")


if __name__ == "__main__":
    main()
