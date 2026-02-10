import asyncio
import evdev
from evdev import ecodes, InputDevice, list_devices

async def print_events(device):
    print(f"--- Listening to {device.name} ---")
    print(f"Path: {device.path}")
    print("Press Ctrl+C to stop")
    
    try:
        async for event in device.async_read_loop():
            if event.type == ecodes.EV_ABS:
                code_name = ecodes.ABS.get(event.code, f"CODE_{event.code}")
                print(f"[Stick/Trigger] {code_name} (Code {event.code}): {event.value}")
            elif event.type == ecodes.EV_KEY:
                key_name = ecodes.KEY.get(event.code, f"CODE_{event.code}")
                state = "Pressed" if event.value == 1 else "Released"
                print(f"[Button] {key_name} (Code {event.code}): {state}")
    except OSError:
        print("Device disconnected.")

async def main():
    print("Searching for Gamepad...")
    devices = [InputDevice(path) for path in list_devices()]
    
    target_device = None
    
    for dev in devices:
        print(f"Check: {dev.name} ({dev.path})")
        
        # "Wireless Controller" という名前を含み、かつ
        # EV_ABS（スティック）と EV_KEY（ボタン）の両方を持っているものを探す
        caps = dev.capabilities()
        if ecodes.EV_ABS in caps and ecodes.EV_KEY in caps:
            # さらに絞り込み：Motion Sensorsではないことを確認（BTN_SOUTH=×ボタンを持っているか）
            if ecodes.BTN_SOUTH in caps.get(ecodes.EV_KEY, []):
                print(f" -> FOUND GAMEPAD! : {dev.name}")
                target_device = dev
                break
            else:
                print(" -> Has ABS/KEY but missing gamepad buttons (Maybe Touchpad?)")
        else:
            print(" -> Not a gamepad (Missing ABS or KEY)")

    if target_device:
        # 他のアプリ（Xorgなど）に取られないようにgrabする
        try:
            target_device.grab()
            print("Grabbed device (exclusive access).")
        except Exception as e:
            print(f"Warning: Could not grab device: {e}")
            
        await print_events(target_device)
    else:
        print("\nNo Gamepad found. Please check bluetooth connection.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
