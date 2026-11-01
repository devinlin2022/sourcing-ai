import os
import threading
import time


def boot(port: int = 7860):
    import uvicorn

    from app.api import create_app

    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port))
    threading.Thread(target=server.run, daemon=True).start()
    time.sleep(4)

    url = f"http://127.0.0.1:{port}"
    if os.getenv("NGROK_AUTHTOKEN"):
        try:
            from pyngrok import ngrok

            ngrok.set_auth_token(os.getenv("NGROK_AUTHTOKEN"))
            url = ngrok.connect(port).public_url
        except Exception as e:
            print(f"ngrok 失败，使用本地地址: {e}")
    print(f"\n{'=' * 50}\n  Sourcing AI 已启动: {url}\n  登录: admin / "
          f"{os.getenv('ADMIN_PASSWORD', 'admin123')}\n{'=' * 50}\n")
    return server
