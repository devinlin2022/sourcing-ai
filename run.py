import argparse

import uvicorn

from app.api import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--ngrok", action="store_true")
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    app = create_app()

    if args.ngrok:
        try:
            from pyngrok import ngrok

            from app.config import NGROK_AUTHTOKEN

            if NGROK_AUTHTOKEN:
                ngrok.set_auth_token(NGROK_AUTHTOKEN)
            tunnel = ngrok.connect(args.port)
            print(f"\n  公网地址: {tunnel.public_url}\n")
        except Exception as e:
            print(f"ngrok 启动失败（可继续用本地地址）: {e}")

    print(f"  本地地址: http://127.0.0.1:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
