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
            'l2': 0.0,          # L2ボタン (アナログ値 0.0〜1.0)
            'fire': False       # 〇ボタン
        }

    async def connect(self):
        while not self.connected:
            print("Searching for Wireless Controller...")
            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
            for dev in devices:
                caps = dev.capabilities()
                if "Wireless Controller" in dev.name:
                    if 1 in caps and 3 in caps: 
                        if 304 in caps.get(1, []):
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
        while True:
            if not self.device:
                await self.connect()

            try:
                async for event in self.device.async_read_loop():
                    self._process_event(event)
            except (OSError, asyncio.CancelledError):
                print("Controller disconnected or loop cancelled.")
                self.connected = False
                self.device = None
                await asyncio.sleep(1)

    def _process_event(self, event):
        if event.type == ecodes.EV_ABS:
            # スティック用正規化 (中心0, -1.0〜1.0)
            def normalize_stick(val):
                centered = val - 127.5
                if abs(centered) < 10: # Deadzone
                    return 0.0
                return centered / 127.5

            # トリガー用正規化 (0〜255 -> 0.0〜1.0)
            def normalize_trigger(val):
                return val / 255.0

            # --- 左スティック ---
            if event.code == 1:
                self.state['throttle'] = -normalize_stick(event.value)
            elif event.code == 0:
                self.state['turn'] = normalize_stick(event.value)

            # --- 右スティック ---
            elif event.code == 3: 
                self.state['turret_pan'] = normalize_stick(event.value)
            elif event.code == 4:
                self.state['turret_tilt'] = -normalize_stick(event.value)
            
            # --- L2トリガー (Code 2: ABS_Z) ---
            # ※コントローラーによっては Code 5 (ABS_RZ) がR2
            elif event.code == 2:
                self.state['l2'] = normalize_trigger(event.value)
            
            # R2 (Code 5) は今回は使わないが、将来のために
            elif event.code == 5:
                pass 

        # ボタン操作 (KEY)
        elif event.type == ecodes.EV_KEY:
            if event.code == 305: # 〇ボタン
                self.state['fire'] = (event.value == 1)
