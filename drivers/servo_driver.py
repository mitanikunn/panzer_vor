# 機能	GPIO Pin	説明
# 砲塔旋回 (Pan)	GPIO 12	PWM0 (ハードウェアPWM推奨)
# 砲身上下 (Tilt)	GPIO 13	PWM1 (ハードウェアPWM推奨)
# 発砲リコイル	GPIO 6	通常GPIO (一瞬の動作なのでOK)

from gpiozero import AngularServo, PWMLED
from gpiozero.pins.pigpio import PiGPIOFactory
import asyncio


class TurretController:
    def __init__(self, config):
        self.config = config
        self.factory = PiGPIOFactory()

        # ---- Pan servo ----
        c_pan = self.config['pan']
        self.pan_servo = AngularServo(
            c_pan['pin'],
            min_angle=c_pan.get('min_angle', -90),
            max_angle=c_pan.get('max_angle', 90),
            initial_angle=c_pan.get('initial_angle', 0),
            min_pulse_width=c_pan.get('min_pulse_width', 1/1000),   # 秒
            max_pulse_width=c_pan.get('max_pulse_width', 2/1000),   # 秒
            frame_width=c_pan.get('frame_width', 20/1000),          # 秒(=50Hz)
            pin_factory=self.factory,
        )

        # ---- Tilt servo ----
        c_tilt = self.config['tilt']
        self.tilt_servo = AngularServo(
            c_tilt['pin'],
            min_angle=c_tilt.get('min_angle', -45),
            max_angle=c_tilt.get('max_angle', 45),
            initial_angle=c_tilt.get('initial_angle', 0),
            min_pulse_width=c_tilt.get('min_pulse_width', 1/1000),
            max_pulse_width=c_tilt.get('max_pulse_width', 2/1000),
            frame_width=c_tilt.get('frame_width', 20/1000),
            pin_factory=self.factory,
        )

        # ---- Fire servo + LED ----
        c_fire = self.config['fire']
        self.fire_servo = AngularServo(
            c_fire['pin'],
            min_angle=c_fire.get('min_angle', -90),
            max_angle=c_fire.get('max_angle', 90),
            initial_angle=c_fire.get('normal_angle', 0),
            min_pulse_width=c_fire.get('min_pulse_width', 1/1000),
            max_pulse_width=c_fire.get('max_pulse_width', 2/1000),
            frame_width=c_fire.get('frame_width', 20/1000),
            pin_factory=self.factory,
        )

        if 'led_pin' in c_fire:
            self.muzzle_flash = PWMLED(c_fire['led_pin'], pin_factory=self.factory)
            self.flash_duration = c_fire.get('flash_duration', 0.05)
        else:
            self.muzzle_flash = None
            self.flash_duration = 0.05

    def set_turret(self, pan, tilt):
        # 角度はここでもクリップしておく（端の唸り対策）
        c_pan = self.config['pan']
        c_tilt = self.config['tilt']
        pan = max(min(pan, c_pan.get('max_angle', 90)), c_pan.get('min_angle', -90))
        tilt = max(min(tilt, c_tilt.get('max_angle', 45)), c_tilt.get('min_angle', -45))

        try:
            self.pan_servo.angle = pan
            self.tilt_servo.angle = tilt
        except ValueError:
            pass

    async def fire_gun(self):
        c_fire = self.config['fire']

        if self.muzzle_flash:
            self.muzzle_flash.value = 1.0

        self.fire_servo.angle = c_fire['recoil_angle']

        if self.muzzle_flash:
            await asyncio.sleep(self.flash_duration)
            self.muzzle_flash.value = 0.0

        await asyncio.sleep(0.1)
        self.fire_servo.angle = c_fire['normal_angle']
