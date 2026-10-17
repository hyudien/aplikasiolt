import argparse
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Open an interactive SSH session to a ZTE OLT."
    )
    parser.add_argument("host", help="OLT IP address or hostname")
    parser.add_argument("username", help="SSH username on the OLT")
    args = parser.parse_args()

    if args.host.startswith("-") or not args.username or args.username.startswith("-"):
        parser.error("host and username must not start with a hyphen")
    if any(char.isspace() for char in args.username):
        parser.error("username must not contain whitespace")

    try:
        return subprocess.run(
            ["ssh", "-tt", "-l", args.username, "--", args.host],
            check=False,
        ).returncode
    except FileNotFoundError:
        print(
            "OpenSSH client 'ssh' was not found. Install OpenSSH and try again.",
            file=sys.stderr,
        )
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
