# ---------- Builder ----------
FROM debian:bookworm-slim AS builder

ARG MOSQUITTO_VERSION=2.0.22
ARG LWS_VERSION=4.4.0

# Build dependencies
RUN apt-get update && apt-get install -y \
    cmake build-essential wget \
    libssl-dev libcjson-dev libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Build libwebsockets from source
RUN wget https://github.com/warmcat/libwebsockets/archive/v${LWS_VERSION}.tar.gz -O /tmp/lws.tar.gz && \
    tar --strip=1 -xf /tmp/lws.tar.gz -C /build && \
    rm /tmp/lws.tar.gz && \
    cmake . \
        -DCMAKE_BUILD_TYPE=MinSizeRel \
        -DCMAKE_INSTALL_PREFIX=/usr \
        -DLWS_IPV6=ON \
        -DLWS_WITHOUT_CLIENT=ON \
        -DLWS_WITHOUT_TESTAPPS=ON \
        -DLWS_WITH_HTTP2=OFF \
        -DLWS_WITH_SHARED=OFF \
        -DLWS_WITH_ZIP_FOPS=OFF \
        -DLWS_WITH_ZLIB=OFF \
        -DLWS_WITH_EXTERNAL_POLL=ON && \
    make -j$(nproc) && make install

# Build Mosquitto
RUN wget http://mosquitto.org/files/source/mosquitto-${MOSQUITTO_VERSION}.tar.gz && \
    tar xzf mosquitto-${MOSQUITTO_VERSION}.tar.gz && \
    cd mosquitto-${MOSQUITTO_VERSION} && \
    make -j$(nproc) \
        CFLAGS="-Wall -O2" \
        WITH_WEBSOCKETS=yes \
        WITH_TLS=yes \
        WITH_PERSISTENCE=yes && \
    make install

# Build plugin
COPY CMakeLists.txt plugin.c /src/plugin/
WORKDIR /src/plugin
RUN cmake -B build -DMOSQUITTO_INCLUDE_DIR=/usr/local/include && \
    cmake --build build

# ---------- Runtime ----------
FROM debian:bookworm-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libssl3 libcurl4 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r mosquitto \
    && useradd -r -g mosquitto -d /mosquitto mosquitto

# Create directories
RUN mkdir -p /mosquitto/{config,data,log,plugins} && \
    chown -R mosquitto:mosquitto /mosquitto

RUN mkdir -p /var/lib/mosquitto && \
    chown -R mosquitto:mosquitto /var/lib/mosquitto

# Copy binaries
COPY --from=builder /usr/local/sbin/mosquitto /usr/local/bin/
COPY --from=builder /usr/local/lib/libmosquitto.so.1 /usr/local/lib/
COPY --from=builder /usr/local/bin/mosquitto_passwd /usr/local/bin/

# Copy plugin
COPY --from=builder /src/plugin/build/libauth_plugin.so /mosquitto/plugins/

RUN ldconfig && chown -R mosquitto:mosquitto /mosquitto

USER mosquitto

CMD ["mosquitto", "-c", "/mosquitto/config/mosquitto.conf"]