import pigpio
import time
import sys

# pigpioに接続
pi = pigpio.pi()
if not pi.connected:
    print("pigpiod is not running!")
    sys.exit()

# 砲塔旋回のピン番号 (Configに合わせて変更してください。例: 12)
SERVO_PIN = 12 

print(f"Connecting to GPIO {SERVO_PIN}...")
print("Starting calibration. Press Ctrl+C to stop.")

def set_width(val):
    print(f"Pulse Width: {val} µs")
    pi.set_servo_pulsewidth(SERVO_PIN, val)
    time.sleep(1)

try:
    # 1. まず中央 (1500µs)
    print("--- Center (1500) ---")
    set_width(1500)

    # 2. 最小幅を探る (500µsに向けて減らす)
    print("\n--- Finding MIN limit ---")
    for width in [1200, 1000, 800, 600, 500]:
        set_width(width)
        # ここでサーボが「ジジジ...」と鳴ったら、そこが行き過ぎです！
        # その直前の値が「安全な最小値」です。

    # 一旦戻す
    set_width(1500)

    # 3. 最大幅を探る (2500µsに向けて増やす)
    print("\n--- Finding MAX limit ---")
    for width in [1800, 2000, 2200, 2400, 2500]:
        set_width(width)
        # ここでも「ジジジ...」と鳴ったら行き過ぎです。
    
    # 終了
    set_width(1500)
    print("\nCalibration check finished.")

except KeyboardInterrupt:
    print("\nStopping...")
    pi.set_servo_pulsewidth(SERVO_PIN, 0) # 信号停止
    pi.stop()
