"""Enable ``python3 -m tide ...`` as an entrypoint equivalent to the console script."""
from tide.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
