# HomeCam

A self-hosted home security camera system I built on a Raspberry Pi 5 for my Data Communications course at university (2026 semester project).

It streams live video, detects motion, takes snapshots and backs them up to AWS S3. You can open the dashboard from anywhere, for example from a phone on mobile data, without opening any ports on the router.

## Why I built it this way

Most "remote camera" tutorials assume you own your router, have a public IP and can set up port forwarding. On a university network or in a shared house you usually can't do any of that, because the network sits behind CGNAT and you have no router access.

To get around this I used **Tailscale**. Both the Pi and my phone make outbound connections only, and Tailscale sets up an encrypted WireGuard tunnel between them. The Pi never accepts inbound traffic from the internet, so it works on pretty much any network.

## What it does

- Live video stream (MJPEG) from a night-vision camera, viewable in any browser
- Motion detection with a PIR sensor, with every event logged to a Postgres database
- Automatic snapshots on motion, uploaded to an encrypted S3 bucket
- Local fallback: if S3 can't be reached, snapshots stay on the Pi and upload once the connection is back
- Temperature and humidity readings from a DHT22 sensor
- Red/green LEDs and a buzzer for status and alarms
- Three operating modes (Stealth, Alert and Manual), controlled from the dashboard
- Remote access through Tailscale, with HTTPS and a password on top

## How it works

The system runs as three Docker containers on the Pi, with Tailscale installed directly on the Pi's OS:

- **nginx** handles HTTPS, rate limiting and password login (basic auth), then forwards requests to the app. It only listens on the Pi's Tailscale IP.
- **app** is a Python Flask app. It serves the dashboard and API, and runs background threads for the camera, the motion sensor, the temperature sensor and the S3 uploader.
- **db** is a Postgres database that stores the event log and settings (current mode, alarm schedule).

This is the path a request from my phone takes:

```
Phone  ->  Tailscale tunnel (WireGuard)  ->  nginx (HTTPS + login)  ->  Flask app  ->  Postgres
```

And this is what happens when motion is detected:

1. The PIR sensor goes high and the motion thread picks it up (it checks the pin 20 times a second).
2. The app grabs the latest camera frame and saves it as a JPEG on the Pi.
3. The event gets logged in the database.
4. The snapshot is added to the upload queue and sent to S3.
5. If the system is in Alert mode and it's within the armed hours, the red LED and buzzer go off.

The dashboard is a single HTML page with a bit of plain JavaScript. It refreshes the status every 3 seconds and the event list every 5 seconds.

## Operating modes

- **Stealth**: silent monitoring. Motion is logged and a snapshot is saved and uploaded, with no alarm. The green LED shows the system is on.
- **Alert**: same as Stealth, but if motion happens during the armed hours (for example 22:00 to 06:00), the red LED turns on and the buzzer beeps. Outside those hours it just logs.
- **Manual**: motion is only logged. I can switch the LEDs on and off and take snapshots from the dashboard.

The current mode is saved in the database, so it comes back after a restart.

## Hardware

- Raspberry Pi 5
- CSI night-vision camera (OV5647)
- HC-SR501 PIR motion sensor
- DHT22 temperature and humidity sensor
- Red and green LEDs (with 220 ohm resistors)
- Passive buzzer
- Breadboard and jumper wires

## Tech stack

- Python, Flask, Gunicorn
- PostgreSQL with SQLAlchemy
- Docker and Docker Compose
- nginx (reverse proxy, TLS, basic auth, rate limiting)
- Tailscale (WireGuard VPN)
- AWS S3 and IAM (boto3)
- picamera2 and lgpio for the camera and GPIO

## Security

I tried to follow a "defence in depth" approach, so that no single layer failing exposes the camera:

1. A firewall (UFW) on the Pi blocks everything except SSH, HTTPS and Tailscale.
2. Only devices on my Tailscale network can reach the dashboard at all.
3. nginx encrypts the connection with HTTPS.
4. nginx requires a username and password and rate-limits requests.
5. The AWS user on the Pi can only upload to one bucket and nothing else.

All secrets live in a `.env` file that is never committed (see `.env.example`).

## Things that didn't make it

Not everything went to plan, and I redesigned a few parts along the way:

- **BH1750 light sensor**: Alert mode was originally meant to only trigger when the room was dark. The sensor never showed up on the I2C bus (most likely a damaged chip), so I switched to a time-based schedule instead. That turned out to be a better design anyway, since a flashlight can fool a light sensor but it can't change the clock.
- **RFID reader (RC522)**: I wanted to arm and disarm the system by tapping a card, but the usual Python library depends on RPi.GPIO, which doesn't work on the Pi 5. Mode switching is done from the dashboard instead.
- **WS2812 LED strip**: too fiddly to drive reliably from inside Docker, so I replaced it with two normal LEDs.
- **OpenCV motion detection**: considered, but the PIR sensor already does the job without the extra CPU load and image size.

## Project structure

```
app/                     Flask app, sensor threads, dashboard
  main.py                Routes, mode logic, starts all threads
  camera.py              Camera capture
  pir.py                 Motion sensor
  dht.py                 Temperature / humidity sensor
  leds.py, buzzer.py     Outputs
  uploader.py            S3 upload queue
  db.py                  Database models
  state.py               Shared state between threads
  stubs.py               Fake sensors for testing without a Pi
  templates/index.html   Dashboard
nginx/                   Reverse proxy config
scripts/                 Deploy and certificate scripts
docker-compose.yml       Main container setup
docker-compose.prod.yml  Extra settings for the Pi hardware
HomeCam_Wiki.html        Full project wiki (setup guide + design decisions)
full-wiring-diagram.html Wiring diagram
```

## Running it

The full step-by-step setup (Pi OS, AWS, Tailscale, certificates) is in the wiki. The short version, on the Pi:

```
cp .env.example .env      # then fill in your values
htpasswd -nb <user> <password> > nginx/htpasswd
bash scripts/gen-cert.sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

To test without the Pi hardware, set `STUB_SENSORS=1` and the app uses fake sensors instead.


## What I learned

- How CGNAT works, and why port forwarding isn't always an option
- Setting up a VPN-based approach (Tailscale / WireGuard) instead of exposing services
- Running hardware-facing code inside Docker on a Raspberry Pi 5, which has a different GPIO system from older Pis
- Splitting a system into separate services that talk over a Docker network
- Handling things going wrong, like failed uploads, sensor misreads and hardware that just doesn't work
