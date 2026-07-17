from cloudx_cloud.cli import main
from cloudx_cloud.public_metadata import emit_error


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        emit_error("cloudx-remote", exc)
        raise SystemExit(1)
