# Smart Attendance — single-container deployment.
# dlib (pulled in by face_recognition) compiles from source: the build stage
# needs cmake + a C++ toolchain, and the first build takes several minutes.
FROM python:3.11-slim

# Runtime + build dependencies:
#   build-essential/cmake        -> compile dlib
#   libopenblas-dev/liblapack-dev -> dlib linear algebra
#   libgl1/libglib2.0-0          -> OpenCV runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake \
        libopenblas-dev liblapack-dev \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

ENV FLASK_ENV=production \
    PYTHONUNBUFFERED=1

EXPOSE 5000

# ONE worker: the pipeline thread owns the camera (see run.py docstring).
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", \
     "--timeout", "120", "run:app"]
