import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from screenshot_bot.workflow import build_wechat_official_server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-path", default=str(ROOT / "config.example.json"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--path", default="/wechat/official/webhook")
    parser.add_argument("--ready-file", default="")
    args = parser.parse_args()

    server = build_wechat_official_server(args.config_path, args.host, args.port, args.path)
    if args.ready_file:
        ready_path = Path(args.ready_file)
        ready_path.parent.mkdir(parents=True, exist_ok=True)
        ready_path.write_text(json.dumps(server.ready_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(server.ready_payload, ensure_ascii=True), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
