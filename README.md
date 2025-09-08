[WIP]
# Mosquitto auth

Mosquitto plugin to do authentication. Available for HTTP endpoint calls

## Run

### Docker

The debian build is used for mosquitto because libcurl is weird on alpine.

`docker compose up --build`

### Build

`cmake -S . -B build && cmake --build build`