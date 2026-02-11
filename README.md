# Panzer Vor! - RC Tank Control System (Pi Zero W Edition)

Raspberry Pi Zero W を搭載したRC戦車（1/16 Leopard 2A6等）を、ブラウザからFPV操縦するためのシステムです。
PS4コントローラーを使用し、スムーズな走行、砲塔制御、そしてリアルな走行音・発砲音をブラウザ経由で再生します。

> **Note:** This README is optimized for **Raspberry Pi Zero W v1.1** (Single Core ARMv6).
> For Raspberry Pi 4/5, configuration can be higher (resolution/fps).

## Features

- 🎮 **PS4 Controller Support**: Full control via DualShock 4 (Bluetooth).
- 🎥 **Low-Latency FPV**: Lightweight MJPEG streaming optimized for Pi Zero W (320x240 @ 10fps).
- 🔊 **Realistic Sound FX**: Engine idle/drive crossfading, cannon fire, and machine gun sounds played on the browser side.
- ⚙️ **Turret Control**: Pan/Tilt servo control with recoil simulation.
- 📱 **Responsive Web UI**: "Mission Control" interface accessible from PC/Smartphone.

## Hardware Requirements

- **Raspberry Pi Zero W v1.1** (or Pi 3/4/5)
- **Raspberry Pi Camera Module** (v2 or compatible)
- **Motor Driver** (e.g., L298N, DRV8833) connected to GPIO.
- **Servos** (x2) for Turret Pan/Tilt.
- **PS4 Controller** (DualShock 4).
- **Mobile Battery** (for Pi) & **Li-Po Battery** (for Motors).

## Installation & Setup

### 1. OS Installation
Install **Raspberry Pi OS Lite (Legacy, Bullseye)**.
*Note: `Bookworm` is supported but requires `rpicam-apps` instead of `raspivid`. This guide assumes Bullseye.*

### 2. System Configuration
Access your Pi via SSH and run `sudo raspi-config`:

1.  **Enable Legacy Camera**:
    *   `Interface Options` -> `Legacy Camera` -> `Enable` -> `Yes`.
    *   *(Crucial for Pi Zero W to use `raspivid` hardware encoding)*.
2.  **GPU Memory**:
    *   `Performance Options` -> `GPU Memory` -> Set to **128** MB.
3.  **Expand Filesystem**:
    *   `Advanced Options` -> `Expand Filesystem`.

Reboot the Pi:
```bash
sudo reboot
3. Install Dependencies
Update packages and install Python libraries, system tools, and Bluetooth support.

bash
sudo apt update && sudo apt install -y \
    python3-pip \
    git \
    libatlas-base-dev \
    bluetooth \
    bluez \
    bluez-tools \
    udev
4. Bluetooth Setup (PS4 Controller)
Pair your PS4 Controller manually via bluetoothctl.

bash
sudo bluetoothctl
# Inside bluetoothctl:
agent on
default-agent
scan on
# Press SHARE + PS Button on controller until light bar flashes white.
# Wait for MAC address (e.g., A4:50:...) to appear.
pair <MAC_ADDRESS>
trust <MAC_ADDRESS>
connect <MAC_ADDRESS>
# Controller light should turn solid.
exit
5. Clone & Install Project
bash
git clone https://github.com/mitanikunn/panzer_vor.git
cd panzer_vor

# Create Virtual Environment (Recommended)
python3 -m venv venv
source venv/bin/activate

# Install Python Requirements
pip install -r requirements.txt
requirements.txt:

text
aiohttp
pyyaml
evdev
RPi.GPIO
pigpio
Note: You may need sudo pigpiod running if using pigpio library.

6. Configuration
Edit config/config.yaml to match your pin layout.

text
# config/config.yaml
motor_driver:
  left:
    pwm_pin: 12
    dir_pin: 5
    en_pin: 6
  right:
    pwm_pin: 13
    dir_pin: 19
    en_pin: 26

turret_system:
  pan_pin: 18
  tilt_pin: 23
  fire_pin: 24  # Relay or FET for Airsoft gun
Running the System
Start the System:

bash
source venv/bin/activate
python main.py
Access Mission Control:
Open a browser (Chrome/Edge recommended) on your PC/Phone:
http://<RASPBERRY_PI_IP>:8080

Important: Ensure no proxy is active on your PC if connecting via IP.

Operation:

Click "ENGINE START" on the web UI (required for audio).

Left Stick: Drive Tank.

Right Stick: Control Turret.

L2: Machine Gun.

R2 / Circle: Fire Main Cannon.

Troubleshooting (Pi Zero W Specifics)
1. Camera Stream Lag / Not Loading
Pi Zero W has a single-core CPU. If the stream is unstable:

Ensure Legacy Camera is enabled (vcgencmd get_camera should return supported=1).

Check resolution in main.py. Keep it 320x240 @ 10fps for Zero W.

Disable web proxies on your client PC.

2. "503 Service Unavailable" or Connection Refused
Check if python main.py is actually running without errors.

If connecting from a corporate network/VPN, try using SSH Tunneling:
ssh -L 8080:localhost:8080 pi@<IP>
Then access http://localhost:8080.

3. Audio Not Playing
Modern browsers block auto-playing audio. You MUST click the "ENGINE START" button on the UI to enable sound.

Check volume slider in the Web UI.

4. Controller Disconnects
Pi Zero W's onboard Bluetooth shares antenna with Wi-Fi. Heavy streaming usage can cause interference.

Use a 5GHz Wi-Fi dongle if possible, or keep the controller close to the Pi.

License
MIT License