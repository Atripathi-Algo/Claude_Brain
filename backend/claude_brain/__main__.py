import argparse

import uvicorn

from . import config
from .api import create_app


def main():
    ap = argparse.ArgumentParser(prog="claude_brain")
    ap.add_argument("--port", type=int, default=config.load()["port"])
    a = ap.parse_args()
    print(f"Claude Brain on http://127.0.0.1:{a.port}  (read-only)")
    uvicorn.run(create_app(), host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
