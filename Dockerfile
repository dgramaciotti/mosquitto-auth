# ---------- Builder ----------
FROM debian:bookworm-slim AS builder

# Install build deps
RUN apt-get update && apt-get install -y \
    git cmake build-essential \
    libssl-dev libcjson-dev libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Clone Mosquitto (for headers only)
RUN git clone --depth 1 --branch v2.0.18 https://github.com/eclipse/mosquitto

# Copy plugin sources
COPY CMakeLists.txt plugin.c ./plugin/

# Build plugin
WORKDIR /src/plugin
RUN cmake -B build -DMOSQUITTO_INCLUDE_DIR=/src/mosquitto/include \
    && cmake --build build

# ---------- Runtime ----------
FROM debian:bookworm-slim

# Install Mosquitto runtime + libcurl (needed by plugin)
RUN apt-get update && apt-get install -y \
    mosquitto libcurl4 \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled plugin
COPY --from=builder /src/plugin/build/libmy_plugin.so /mosquitto/plugins/

# Copy mosquitto.conf
COPY mosquitto.conf /mosquitto/config/mosquitto.conf

# Run Mosquitto
CMD ["mosquitto", "-c", "/mosquitto/config/mosquitto.conf", "-v"]
