import asyncio
import yaml
import sys
import os
from drivers.motor_driver import TankDriveSystem
from drivers.servo_driver import TurretController
from drivers.controller import PS4Controller
from aiohttp import web
import json


# グローバル変数で発砲状態を共有
GAME_STATE = {
    "fired": False,      # 主砲 (単発)
    "machinegun": False, # マシンガン (連射)
    "speed": 0.0
}

# --- カメラ設定 ---
# rpicam-vidがインストールされているか確認
CAMERA_CMD = "rpicam-vid"

# MJPEG配信ハンドラ (非同期サブプロセス版)
# --- 境界検出あり版 (画質安定、遅延小) ---
async def mjpeg_handler(request):
    boundary = "boundarydonotcross"
    response = web.StreamResponse(status=200, reason='OK', headers={
        'Content-Type': 'multipart/x-mixed-replace;boundary={}'.format(boundary),
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
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


# --- 状態確認API ---
async def status_handler(request):
    global GAME_STATE
    fired = GAME_STATE["fired"]
    mg = GAME_STATE["machinegun"]
    speed = GAME_STATE["speed"]
    
    # firedは単発なのでリセット
    if fired:
        GAME_STATE["fired"] = False
        
    return web.json_response({"fired": fired, "machinegun": mg, "speed": speed})


# --- HTMLハンドラ (エンジン音制御追加) ---
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
            #start-btn { 
                padding: 15px 30px; font-size: 1.5em; background: #d00; color: #fff; 
                border: none; border-radius: 5px; cursor: pointer; margin-bottom: 20px;
            }
            /* 音量スライダーのスタイル */
            .controls { margin: 20px auto; width: 80%; max-width: 400px; }
            input[type=range] { width: 100%; cursor: pointer; }
            label { font-size: 1.2em; display: block; margin-bottom: 5px; }
        </style>
    </head>
    <body>
        <h1>Panzer Vor! Mission Control</h1>
        
        <button id="start-btn" onclick="startSystem()">ENGINE START</button>
        
        <div class="controls">
            <label for="vol-slider">Master Volume: <span id="vol-disp">50%</span></label>
            <input type="range" id="vol-slider" min="0" max="100" value="50" oninput="updateVolume(this.value)">
        </div>

        <div class="container">
            <img id="cam" alt="Camera Stream" />
        </div>
        <div class="status">Status: <span style="color:#0f0">Online</span></div>

        <script>
            // 音声ファイル定義
            const fireSound = new Audio('/sounds/lepard2a5_fire_01.mp3');
            const idleSound = new Audio('/sounds/leopard2a5_idring_01.mp3');
            const driveSound = new Audio('/sounds/leopard2a5_go_01.mp3');
            const mgSound = new Audio('/sounds/leopard2a5_machinegun_01.mp3');
            
            idleSound.loop = true;
            driveSound.loop = true;
            mgSound.loop = true;
            
            // マスター音量 (0.0 〜 1.0)
            let masterVolume = 0.5;
            let pollingInterval = null;

            // スライダー操作時に呼ばれる関数
            function updateVolume(val) {
                masterVolume = val / 100.0;
                document.getElementById('vol-disp').innerText = val + "%";
                
                // 単発系・一定音量の音は即座に反映
                // エンジン音はcheckStatusループ内で反映されるのでここでは不要だが念のため
                fireSound.volume = masterVolume;
                mgSound.volume = masterVolume;
            }

            async function startSystem() {
                const btn = document.getElementById('start-btn');
                btn.disabled = true;
                btn.innerText = "Initializing...";

                try {
                    await initAudio(fireSound);
                    await initAudio(idleSound);
                    await initAudio(driveSound);
                    await initAudio(mgSound);
                } catch (e) {
                    console.error("Audio init failed:", e);
                    btn.innerText = "Audio Error (Retry)";
                    btn.disabled = false;
                    return;
                }

                // 始動時はマスター音量を適用
                idleSound.volume = 1.0 * masterVolume;
                idleSound.play();
                driveSound.volume = 0.0;
                driveSound.play();
                
                mgSound.pause();
                mgSound.currentTime = 0;

                document.getElementById('cam').src = "/stream";
                btn.style.display = 'none';

                if (!pollingInterval) {
                    pollingInterval = setInterval(checkStatus, 100);
                }
            }

            function initAudio(audio) {
                return new Promise((resolve, reject) => {
                    audio.onerror = () => reject(new Error(`Failed to load ${audio.src}`));
                    audio.play().then(() => {
                        audio.pause();
                        audio.currentTime = 0;
                        resolve();
                    }).catch(err => reject(err));
                });
            }

            async function checkStatus() {
                try {
                    const res = await fetch('/status');
                    const data = await res.json();
                    
                    // 1. 主砲
                    if (data.fired) {
                        fireSound.volume = masterVolume; // 発射時に音量適用
                        fireSound.currentTime = 0;
                        fireSound.play().catch(e => {});
                    }
                    
                    // 2. マシンガン
                    if (data.machinegun) {
                        mgSound.volume = masterVolume; // 連射中も音量適用
                        if (mgSound.paused) {
                            mgSound.play().catch(e => {});
                        }
                    } else {
                        if (!mgSound.paused) {
                            mgSound.pause();
                            mgSound.currentTime = 0;
                        }
                    }

                    // 3. エンジン音 (クロスフェード x マスター音量)
                    const speed = data.speed;
                    
                    // 本来のバランス計算 (0.0〜1.0)
                    const baseIdleVol = Math.max(0, 1.0 - (speed * 1.5)); 
                    const baseDriveVol = Math.min(1.0, speed * 1.2); 
                    
                    // マスター音量を掛ける
                    const finalIdleVol = baseIdleVol * masterVolume;
                    const finalDriveVol = baseDriveVol * masterVolume;

                    // ピッチ
                    const idleRate = 1.0 + (speed * 0.2);
                    const driveRate = 0.8 + (speed * 0.8);

                    // スムージング適用
                    idleSound.volume = clamp(idleSound.volume + (finalIdleVol - idleSound.volume) * 0.2);
                    driveSound.volume = clamp(driveSound.volume + (finalDriveVol - driveSound.volume) * 0.2);
                    
                    idleSound.playbackRate = idleRate;
                    driveSound.playbackRate = driveRate;

                } catch (e) {}
            }

            function clamp(val) { return Math.max(0, Math.min(1.0, val)); }
        </script>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')



    

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/stream', mjpeg_handler)
    app.router.add_get('/status', status_handler)
    app.router.add_static('/sounds/', path='./sounds/', name='sounds')
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("Web Server started at http://0.0.0.0:8080")






async def tank_control_loop(tank, turret, controller):
    global GAME_STATE
    print("Control Loop Started")
    pan_angle = 0
    tilt_angle = 0
    
    try:
        while True:
            if not hasattr(controller, 'state'):
                await asyncio.sleep(1)
                continue

            # 入力読み取り
            # L2ボタンの値 (0.0 〜 1.0) を取得。0.5以上でONとみなす
            l2_val = controller.state.get('l2', -1.0) # 初期値-1.0等
            # ps4 controllerライブラリによってはL2は -1.0(離)〜1.0(押) だったり 0.0(離)〜1.0(押) だったりする
            # ここでは「0.0より大きい」または「特定ボタン」として判定
            
            # もし `controller.state` に `l2` がアナログ値で入っているなら：
            is_machinegun = (l2_val > 0.1) # 少しでも押したらON
            
            # あるいは `buttons` に入っているなら：
            # is_machinegun = controller.state['buttons']['l2'] 
            
            GAME_STATE["machinegun"] = is_machinegun

            # 走行・主砲
            throttle = controller.state.get('throttle', 0)
            turn = controller.state.get('turn', 0)
            GAME_STATE["speed"] = max(abs(throttle), abs(turn))
            tank.drive(throttle, turn)
            
            t_pan = controller.state.get('turret_pan', 0)
            t_tilt = controller.state.get('turret_tilt', 0)
            if t_pan != 0: pan_angle = max(min(pan_angle + t_pan*3, 90), -90)
            if t_tilt != 0: tilt_angle = max(min(tilt_angle + t_tilt*2, 40), -20)
            turret.set_turret(pan_angle, tilt_angle)
            
            if controller.state.get('fire', False):
                GAME_STATE["fired"] = True
                asyncio.create_task(turret.fire_gun())
                controller.state['fire'] = False
            
            await asyncio.sleep(0.05)
    except Exception as e:
        print(f"Error: {e}")
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
