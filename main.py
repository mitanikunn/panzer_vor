import asyncio
import yaml
import sys
from drivers.motor_driver import TankDriveSystem
from drivers.servo_driver import TurretController
from drivers.controller import PS4Controller

async def tank_control_loop(tank, turret, controller):
    """コントローラの状態を読み取ってハードウェアを動かすループ"""
    print("Starting Control Loop...")
    
    pan_angle = 0
    tilt_angle = 0
    
    try:
        while True:
            # 1. 走行制御
            # 常に最新の入力を反映
            tank.drive(controller.state['throttle'], controller.state['turn'])
            
            # 2. 砲塔制御
            # 入力が0なら計算しない（無駄なドリフト防止）
            if controller.state['turret_pan'] != 0:
                pan_angle += controller.state['turret_pan'] * 3
                # 範囲制限をここでも厳格に
                pan_angle = max(min(pan_angle, 90), -90)
                
            if controller.state['turret_tilt'] != 0:
                tilt_angle += controller.state['turret_tilt'] * 2
                tilt_angle = max(min(tilt_angle, 40), -20)
            
            # 前回と同じ値なら送らない（サーボへの負荷軽減 = チャタリング対策）
            # ただし、最初の1回は送る必要があるため、TurretController側でチェックするのがベスト
            turret.set_turret(pan_angle, tilt_angle)
            
            # 3. 発砲 (タスクとして実行)
            if controller.state['fire']:
                print("FIRE ACTION!")
                asyncio.create_task(turret.fire_gun())
                controller.state['fire'] = False # フラグ解除
            
            # 制御ループの周期 (20ms = 50Hz)
            # これがないと他の処理（コントローラ読み取り）がブロックされる
            await asyncio.sleep(0.02)
            
    except asyncio.CancelledError:
        print("Control loop cancelled.")
    except Exception as e:
        print(f"Error in control loop: {e}")
    finally:
        tank.stop()

async def main():
    # 設定読み込み
    try:
        with open("config/config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("Error: config/config.yaml not found.")
        sys.exit(1)

    print("Initializing Hardware...")
    try:
        tank = TankDriveSystem()
        turret = TurretController(config['turret_system'])
    except Exception as e:
        print(f"Hardware Init Failed: {e}")
        # pigpiodが動いていない場合など
        sys.exit(1)
    
    ps4 = PS4Controller()
    
    print("System Ready. Press Ctrl+C to stop.")

    # タスク生成
    # 1. コントローラ入力監視
    input_task = asyncio.create_task(ps4.listen())
    
    # 2. 戦車制御ループ
    control_task = asyncio.create_task(tank_control_loop(tank, turret, ps4))
    
    try:
        # 両方のタスクを実行し続ける
        await asyncio.gather(input_task, control_task)
    except asyncio.CancelledError:
        print("Main cancelled.")
    finally:
        tank.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopping...")
