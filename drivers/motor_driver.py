
# L9110S Pin	RasPi Pin (BCM)	役割
# A-IA	GPIO 17	左モーター (A) 正転/逆転
# A-IB	GPIO 27	左モーター (A) 正転/逆転
# B-IA	GPIO 22	右モーター (B) 正転/逆転
# B-IB	GPIO 23	右モーター (B) 正転/逆転
# VCC	Battery (+)	モーター電源 (2.5V-12V)
# GND	Battery (-) & Pi GND	GNDは必ずPiと共有すること




import yaml
from gpiozero import Motor
from gpiozero.pins.pigpio import PiGPIOFactory # オプション: 高精度PWM用

class TankDriveSystem:
    def __init__(self, config_path="config/config.yaml"):
        # 設定のロード
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
            
        drive_conf = self.config['drive_system']
        
        # GPIOZeroを使ったL9110Sの初期化
        # Motorクラスは forward/backward ピンを指定するだけで、
        # 正転・逆転・ブレーキ・PWM制御を全部やってくれます。
        
        self.left_motor = Motor(
            forward=drive_conf['motor_left']['pin_forward'],
            backward=drive_conf['motor_left']['pin_backward']
        )
        
        self.right_motor = Motor(
            forward=drive_conf['motor_right']['pin_forward'],
            backward=drive_conf['motor_right']['pin_backward']
        )
        
        # 状態保持
        self.current_left = 0.0
        self.current_right = 0.0

    def _apply_motor_config(self, raw_val, motor_conf):
        """設定（反転・トリム）を適用して最終出力を計算"""
        val = raw_val * motor_conf.get('trim', 1.0)
        
        if motor_conf.get('inverted', False):
            val *= -1
            
        return max(min(val, 1.0), -1.0)

    def drive(self, throttle, turn):
        """
        アーケードドライブ制御
        throttle: 前進/後退 (-1.0 ~ 1.0)
        turn: 旋回 (-1.0 ~ 1.0)
        """
        max_s = self.config['drive_system'].get('max_speed', 1.0)
        throttle *= max_s
        turn *= max_s

        # ミキシング計算
        left_val = throttle + turn
        right_val = throttle - turn

        # 正規化
        mag = max(abs(left_val), abs(right_val), 1.0)
        left_val /= mag
        right_val /= mag

        # 出力計算
        final_left = self._apply_motor_config(left_val, self.config['drive_system']['motor_left'])
        final_right = self._apply_motor_config(right_val, self.config['drive_system']['motor_right'])
        
        # gpiozeroへの出力 (-1.0 ~ 1.0 を受け付ける)
        # valueプロパティに入れるだけでPWMと回転方向を自動制御
        self.left_motor.value = final_left
        self.right_motor.value = final_right

    def stop(self):
        self.left_motor.value = 0
        self.right_motor.value = 0
        self.left_motor.close()
        self.right_motor.close()
