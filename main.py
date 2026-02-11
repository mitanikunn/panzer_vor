import asyncio
import yaml
import sys
import os
from drivers.motor_driver import TankDriveSystem
from drivers.servo_driver import TurretController
from drivers.controller import PS4Controller
from aiohttp import web
import json

# グローバル状態
GAME_STATE = {
    "fired": False,
    "machinegun": False,
    "speed": 0.0
}

# --- Pi Zero W用 軽量MJPEGストリーミング ---
async def mjpeg_handler(request):
    boundary = "frame"
    response = web.StreamResponse(
        status=200,
        headers={
            'Content-Type': f'multipart/x-mixed-replace;boundary={boundary}',
            'Cache-Control': 'no-cache',
            'Connection': 'close',
        }
    )
    await response.prepare(request)
    
    # 画質設定: 320x240, 10fps, 500kbps
    cmd = ['raspivid', '-t', '0', '-w', '320', '-h', '240', '-fps', '10', 
           '-cd', 'MJPEG', '-b', '500000', '-o', '-', '-n']
    
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )

    buffer = b''
    try:
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk: break
            buffer += chunk

            while True:
                start = buffer.find(b'\xff\xd8')
                end = buffer.find(b'\xff\xd9')
                if start != -1 and end != -1 and start < end:
                    jpg = buffer[start:end+2]
                    buffer = buffer[end+2:]
                    await response.write(f'--{boundary}\r\n'.encode())
                    await response.write(b'Content-Type: image/jpeg\r\n')
                    await response.write(f'Content-Length: {len(jpg)}\r\n\r\n'.encode())
                    await response.write(jpg)
                    await response.write(b'\r\n')
                else:
                    if len(buffer) > 100000: buffer = b''
                    break
    except: pass
    finally:
        if proc.returncode is None:
            try: proc.terminate(); await proc.wait()
            except: pass
    return response

# --- ステータス配信 ---
async def status_handler(request):
    global GAME_STATE
    current_state = GAME_STATE.copy()
    # 発砲フラグは一度送ったら下げる（音の重複防止）
    if GAME_STATE["fired"]: GAME_STATE["fired"] = False
    return web.json_response(current_state)

# --- Web UI (フル機能版) ---
async def handle_index(request):
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Panzer Vor! Mission Control</title>
        <style>
            body { font-family: 'Courier New', sans-serif; text-align: center; background: #1a1a1a; color: #0f0; margin: 0; }
            h1 { text-shadow: 0 0 10px #0f0; margin-top: 10px; }
            .container { 
                margin: 10px auto; width: 324px; height: 244px; 
                background: #000; border: 2px solid #555; position: relative;
                box-shadow: 0 0 20px rgba(0, 255, 0, 0.2);
            }
            img { width: 320px; height: 240px; object-fit: contain; display: block; margin: 2px; }
            
            button { 
                padding: 10px 30px; font-size: 1.2em; font-weight: bold;
                background: #c00; color: #fff; border: 2px solid #fff; 
                cursor: pointer; text-transform: uppercase; letter-spacing: 2px;
                transition: all 0.3s;
            }
            button:hover { background: #f00; box-shadow: 0 0 15px #f00; }
            button:disabled { background: #333; border-color: #555; color: #888; box-shadow: none; }
            
            .controls { width: 300px; margin: 15px auto; text-align: left; background: #222; padding: 10px; border-radius: 5px; }
            input[type=range] { width: 100%; cursor: pointer; }
            .status-bar { margin-top: 10px; font-size: 0.9em; color: #888; }
            .active { color: #0f0; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1>PANZER VOR!</h1>

        <div class="container">
            <img id="cam" alt="SYSTEM OFFLINE" />
        </div>

        <button id="start-btn" onclick="startSystem()">ENGINE START</button>

        <div class="controls">
            <label>MASTER VOLUME: <span id="vol-disp">50%</span></label>
            <input type="range" min="0" max="100" value="50" oninput="updateVolume(this.value)">
        </div>
        
        <div class="status-bar">
            SYSTEM STATUS: <span id="sys-status" class="active">STANDBY</span>
        </div>

        <script>
            // 効果音設定
            const sounds = {
                fire: new Audio('/sounds/lepard2a5_fire_01.mp3'),
                idle: new Audio('/sounds/leopard2a5_idring_01.mp3'),
                drive: new Audio('/sounds/leopard2a5_go_01.mp3'),
                mg: new Audio('/sounds/leopard2a5_machinegun_01.mp3')
            };

            sounds.idle.loop = true;
            sounds.drive.loop = true;
            sounds.mg.loop = true;

            let masterVol = 0.5;
            let polling = null;

            function updateVolume(val) {
                masterVol = val / 100.0;
                document.getElementById('vol-disp').innerText = val + "%";
                sounds.fire.volume = masterVol;
                sounds.mg.volume = masterVol;
            }

            async function startSystem() {
                const btn = document.getElementById('start-btn');
                btn.disabled = true; btn.innerText = "INITIALIZING...";

                // 音声の事前ロードと再生許可トリガー
                try {
                    await Promise.all(Object.values(sounds).map(s => {
                        return s.play().then(() => { s.pause(); s.currentTime = 0; });
                    }));
                } catch (e) {
                    console.error(e);
                    btn.innerText = "AUDIO ERROR (CLICK TO RETRY)";
                    btn.disabled = false;
                    return;
                }

                // エンジン始動
                sounds.idle.volume = masterVol; sounds.idle.play();
                sounds.drive.volume = 0; sounds.drive.play();
                
                // カメラ始動 (キャッシュ回避)
                document.getElementById('cam').src = "/stream?" + Date.now();
                
                btn.style.display = 'none';
                document.getElementById('sys-status').innerText = "ONLINE - COMBAT READY";
                
                // ポーリング開始 (Zero負荷軽減のため200ms間隔)
                if (!polling) polling = setInterval(syncStatus, 200);
            }

            async function syncStatus() {
                try {
                    const res = await fetch('/status');
                    const data = await res.json();

                    // 発砲音
                    if (data.fired) {
                        sounds.fire.currentTime = 0;
                        sounds.fire.play().catch(()=>{});
                    }

                    // マシンガン
                    if (data.machinegun) {
                        if (sounds.mg.paused) sounds.mg.play().catch(()=>{});
                    } else {
                        sounds.mg.pause(); sounds.mg.currentTime = 0;
                    }

                    // エンジン音のクロスフェード
                    const spd = data.speed;
                    const idleVol = Math.max(0, 1.0 - (spd * 1.5)) * masterVol;
                    const driveVol = Math.min(1.0, spd * 1.2) * masterVol;

                    // ピッチ変化
                    sounds.idle.playbackRate = 1.0 + (spd * 0.2);
                    sounds.drive.playbackRate = 0.8 + (spd * 0.8);

                    // 音量適用 (簡易的なスムージング)
                    sounds.idle.volume = sounds.idle.volume * 0.8 + idleVol * 0.2;
                    sounds.drive.volume = sounds.drive.volume * 0.8 + driveVol * 0.2;

                } catch (e) {}
            }
        </script>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

# --- 制御ループ (砲塔・走行) ---
async def control_loop(tank, turret, controller):
    print("Control Logic Started")
    pan_angle = 0
    tilt_angle = 0
    
    while True:
        try:
            if not controller.state:
                await asyncio.sleep(0.1)
                continue

            # 1. 走行制御
            thr = controller.state.get('throttle', 0)
            trn = controller.state.get('turn', 0)
            tank.drive(thr, trn)
            GAME_STATE["speed"] = max(abs(thr), abs(trn))

            # 2. 砲塔制御 (相対移動 & 制限)
            # 右スティック入力を取得
            t_pan = controller.state.get('turret_pan', 0)   # 左右
            t_tilt = controller.state.get('turret_tilt', 0) # 上下

            if abs(t_pan) > 0.1 or abs(t_tilt) > 0.1:
                # 入力がある場合だけ角度を更新 (感度調整: *3, *2)
                pan_angle += t_pan * 3.0
                tilt_angle += t_tilt * 2.0
                
                # 角度制限 (サーボの限界に合わせて調整してください)
                pan_angle = max(-90, min(90, pan_angle))
                tilt_angle = max(-20, min(40, tilt_angle))
                
                turret.set_turret(pan_angle, tilt_angle)

            # 3. 武装制御
            # L2ボタンで機銃
            l2 = controller.state.get('l2', -1.0)
            GAME_STATE["machinegun"] = (l2 > 0.1)

            # R2または特定ボタンで主砲
            if controller.state.get('fire'):
                GAME_STATE["fired"] = True
                asyncio.create_task(turret.fire_gun())
                controller.state['fire'] = False

            await asyncio.sleep(0.05) # 20Hz制御
            
        except Exception as e:
            print(f"Ctrl Error: {e}")
            await asyncio.sleep(1)

# --- メインエントリ ---
async def main():
    # 設定読み込み
    config = {}
    if os.path.exists("config/config.yaml"):
        with open("config/config.yaml") as f: config = yaml.safe_load(f)

    # ハードウェア初期化
    tank = TankDriveSystem()
    turret = TurretController(config.get('turret_system', {}))
    controller = PS4Controller()

    # Webサーバーセットアップ
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/stream', mjpeg_handler)
    app.router.add_get('/status', status_handler)
    
    # 重要: 音声ファイルへのパスを通す
    # soundsフォルダがないとブラウザで404エラーになります
    app.router.add_static('/sounds/', path='./sounds/', name='sounds')

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 8080).start()
    print("=== Panzer Vor! System Online ===")
    print("Access: http://<IP>:8080")

    # 全タスク並列実行
    await asyncio.gather(
        controller.listen(),
        control_loop(tank, turret, controller)
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMission Aborted.")