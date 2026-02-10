import yaml
import time
from drivers.motor_driver import TankDriveSystem
from drivers.servo_driver import TurretController

# コンフィグ読み込み
with open("config/config.yaml", "r") as f:
    full_config = yaml.safe_load(f)

# システム初期化
tank = TankDriveSystem("config/config.yaml") # パスは適宜調整
turret = TurretController(full_config['turret_system'])

try:
    print("--- Tank System Check ---")
    
    # 砲塔を回しながら前進
    print("Action: Advance & Scan")
    tank.drive(0.5, 0.0) # 前進
    
    turret.set_turret(45, 10) # 右45度、上10度
    time.sleep(1)
    
    turret.set_turret(-45, -5) # 左45度、下5度
    time.sleep(1)
    
    # 停止して発砲
    tank.stop()
    print("Action: FIRE!")
    turret.set_turret(0, 0) # 正面
    time.sleep(0.5)
    turret.fire_gun()
    
    time.sleep(1)

finally:
    tank.stop()
    # サーボのデタッチは自動で行われます
