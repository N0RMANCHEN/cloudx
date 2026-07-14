import sys

from cloudx_local.cli import main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print("cloudx: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
