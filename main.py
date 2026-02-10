import asyncio
import yaml
import sys
import os
from drivers.motor_driver import TankDriveSystem
from drivers.servo_driver import TurretController
from drivers.controller import PS4Controller
from aiohttp import web

# --- カメラ設定 ---
# rpicam-vidがインストールされているか確認
CAMERA_CMD = "rpicam-vid"

# MJPEG配信ハンドラ (非同期サブプロセス版)
# --- 境界検出あり版 (画質安定、遅延小) ---
async def mjpeg_handler(request):
    boundary = "boundarydonotcross"
    response = web.StreamResponse(status=200, reason='OK', headers={
        'Content-Type': 'multipart/x-mixed-replace;boundary={}'.format(boundary),
        'Cache-Control': 'no-store, no-cache, must-revalidate',
    })
    await response.prepare(request)

    proc = await asyncio.create_subprocess_exec(
        'rpicam-vid', '-t', '0', '--inline', 
        '--width', '320', '--height', '240', 
        '--framerate', '20', 
        '--codec', 'mjpeg', '--quality', '40', '-o', '-',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL
    )

    buffer = b""
    try:
        while True:
            # データ読み込み
            chunk = await proc.stdout.read(4096)
            if not chunk: break
            buffer += chunk
            
            # JPEGの終端 (0xFF 0xD9) を探す
            a = buffer.find(b'\xff\xd8') # Start of Image
            b = buffer.find(b'\xff\xd9') # End of Image
            
            if a != -1 and b != -1:
                # 1枚の画像が完成
                jpg = buffer[a:b+2]
                buffer = buffer[b+2:] # 残りを次へ
                
                # 送信
                await response.write(b'--' + boundary.encode() + b'\r\n')
                await response.write(b'Content-Type: image/jpeg\r\n')
                await response.write(b'Content-Length: ' + str(len(jpg)).encode() + b'\r\n\r\n')
                await response.write(jpg)
                await response.write(b'\r\n')
                
                # バッファが肥大化しないように安全策
                if len(buffer) > 100000: buffer = b""

    except asyncio.CancelledError:
        pass
    finally:
        if proc.returncode is None:
            proc.terminate()
            await proc.wait()
    
    return response



    

async def handle_index(request):
    html = """
    <html>
    <head>
        <title>Panzer Vor!</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { background: #222; color: #fff; text-align: center; margin: 0; padding: 20px; font-family: sans-serif; }
            .container { position: relative; display: inline-block; }
            img { width: 100%; max-width: 640px; border: 2px solid #555; background: #000; }
            .status { margin-top: 10px; font-size: 1.2em; }
            .online { color: #0f0; }
        </style>
    </head>
    <body>
        <h1>Panzer Vor! Mission Control</h1>
        <div class="container">
            <img src="/stream" id="cam" alt="Camera Stream" />
        </div>
        <div class="status">Status: <span class="online">Online</span> (MJPEG Mode)</div>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/stream', mjpeg_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    # 0.0.0.0 で全インターフェース待ち受け
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("Web Server started at http://0.0.0.0:8080")

async def tank_control_loop(tank, turret, controller):
    """コントローラの状態を読み取ってハードウェアを動かすループ"""
    print("Starting Control Loop...")
    
    pan_angle = 0
    tilt_angle = 0
    
    try:
        while True:
            # コントローラーが接続されていない場合のガード
            if not hasattr(controller, 'state'):
                await asyncio.sleep(1)
                continue

            # 1. 走行制御
            throttle = controller.state.get('throttle', 0)
            turn = controller.state.get('turn', 0)
            tank.drive(throttle, turn)
            
            # 2. 砲塔制御
            t_pan = controller.state.get('turret_pan', 0)
            t_tilt = controller.state.get('turret_tilt', 0)

            if t_pan != 0:
                pan_angle += t_pan * 3
                pan_angle = max(min(pan_angle, 90), -90)
                
            if t_tilt != 0:
                tilt_angle += t_tilt * 2
                tilt_angle = max(min(tilt_angle, 40), -20)
            
            turret.set_turret(pan_angle, tilt_angle)
            
            # 3. 発砲
            if controller.state.get('fire', False):
                print("FIRE ACTION!")
                asyncio.create_task(turret.fire_gun())
                controller.state['fire'] = False
            
            # 制御ループ周期 (20Hz)
            await asyncio.sleep(0.05)
            
    except asyncio.CancelledError:
        print("Control loop cancelled.")
    except Exception as e:
        print(f"Error in control loop: {e}")
    finally:
        tank.stop()

async def main():
    # コンフィグ読み込み
    config_path = "config/config.yaml"
    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found.")
        # デフォルト値で続行する場合のフォールバックなどを入れても良い
        sys.exit(1)

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"Config load error: {e}")
        sys.exit(1)

    print("Initializing Hardware...")
    try:
        tank = TankDriveSystem()
        # configからturret_systemを取得、なければ空辞書
        turret = TurretController(config.get('turret_system', {}))
    except Exception as e:
        print(f"Hardware Init Failed: {e}")
        sys.exit(1)
    
    ps4 = PS4Controller()
    
    print("System Ready. Press Ctrl+C to stop.")

    # タスク生成
    input_task = asyncio.create_task(ps4.listen())
    control_task = asyncio.create_task(tank_control_loop(tank, turret, ps4))
    web_task = asyncio.create_task(start_web_server())
    
    try:
        # 全タスクを並列実行
        await asyncio.gather(input_task, control_task, web_task)
    except asyncio.CancelledError:
        print("Main cancelled.")
    finally:
        print("Shutting down...")
        tank.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopping...")
