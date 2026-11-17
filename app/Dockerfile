FROM python:3.11-slim-bookworm

# add raspberry pi apt repo for picamera2, libcamera, lgpio, and gpiod
# these need system libraries not available via pip alone
# python 3.11 matches the abi of the libcamera c extension from the pi repo
RUN apt-get update && apt-get install -y --no-install-recommends \
        gnupg curl \
    && curl -fsSL https://archive.raspberrypi.com/debian/raspberrypi.gpg.key \
       | gpg --dearmor -o /usr/share/keyrings/raspberrypi.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/raspberrypi.gpg] https://archive.raspberrypi.com/debian/ bookworm main" \
       > /etc/apt/sources.list.d/raspberrypi.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3-picamera2 \
        python3-libcamera \
        python3-lgpio \
        libgpiod2 \
        tzdata \
    && apt-get purge -y gnupg curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
	

# make the apt-installed packages visible to python 3.11
ENV PYTHONPATH=/usr/lib/python3/dist-packages

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# one worker only - all sensor threads must share the same process.
# each open MJPEG stream holds a thread for as long as it is watched, so 8 threads
# leaves room for a few viewers while the dashboard API still responds
CMD ["gunicorn", "--workers=1", "--threads=8", "--bind=0.0.0.0:8000", "main:app"]
