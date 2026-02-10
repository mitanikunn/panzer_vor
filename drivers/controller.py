import asyncio
import evdev
from evdev import ecodes

class PS4Controller:
    def __init__(self, device_path=None):
        self.device_path = device_path
        self.device = None
        self.connected = False
        
        # 現在の入力状態を保持
        self.state = {
            'throttle': 0.0,    # 左スティック縦 (Code 1: ABS_Y)
            'turn': 0.0,        # 左スティック横 (Code 0: ABS_X)
            'turret_pan': 0.0,  # 右スティック横 (Code 3: ABS_RX)
            'turret_tilt': 0.0, # 右スティック縦 (Code 4: ABS_RY)
            'fire': False       # 〇ボタン
        }

    async def connect(self):
        while not self.connected:
            print("Searching for Wireless Controller...")
            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
            for dev in devices:
                caps = dev.capabilities()
                if "Wireless Controller" in dev.name:
                    if 1 in caps and 3 in caps: # EV_KEY(1) and EV_ABS(3) exist
                        if 304 in caps.get(1, []): # BTN_SOUTH (× or 〇) exists
                             self.device = dev
                             self.connected = True
                             try:
                                 self.device.grab() # 排他制御
                             except Exception:
                                 pass
                             print(f"Connected to Gamepad at {dev.path}")
                             return
            await asyncio.sleep(2)

    async def listen(self):
        while True: # 無限ループで再接続を試みる構造にする
            if not self.device:
                await self.connect()

            try:
                async for event in self.device.async_read_loop():
                    self._process_event(event)
            except (OSError, asyncio.CancelledError):
                print("Controller disconnected or loop cancelled.")
                self.connected = False
                self.device = None
                await asyncio.sleep(1) # 再接続前のウェイト
    def _process_event(self, event):
        if event.type == ecodes.EV_ABS:
            # 正規化関数にデッドバンドを追加
            def normalize(val):
                # 中心値からのズレを計算 (-127.5 ~ 127.5)
                centered = val - 127.5
                
                # デッドバンド: 中心付近の ±10 (約8%) は 0 とみなす
                if abs(centered) < 10:
                    return 0.0
                
                # 正規化 (-1.0 ~ 1.0)
                return centered / 127.5

            # --- 左スティック (走行用) ---
            if event.code == 1:
                self.state['throttle'] = -normalize(event.value)
            
            elif event.code == 0:
                self.state['turn'] = normalize(event.value)

            # --- 右スティック (砲塔用) ---
            elif event.code == 3: 
                self.state['turret_pan'] = normalize(event.value)
                
            elif event.code == 4:
                self.state['turret_tilt'] = -normalize(event.value)
            
            # 不要な軸は無視
            elif event.code == 2 or event.code == 5:
                pass 

        # ボタン操作 (KEY)
        elif event.type == ecodes.EV_KEY:
            if event.code == 305: # 〇ボタン
                self.state['fire'] = (event.value == 1)