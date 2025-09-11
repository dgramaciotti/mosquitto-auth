[WIP]
# Mosquitto auth

This repository is a [mosquitto](https://mosquitto.org/) plugin that provides user authentication and authorization. It was heavily inspired by the mosquitto [dynamic_security](https://github.com/eclipse-mosquitto/mosquitto/tree/master/plugins/dynamic-security) plugin, as well as the [mosquitto-go-auth](https://github.com/iegomez/mosquitto-go-auth) plugin. It applies the mosquitto v5 [interface](https://mosquitto.org/api/files/mosquitto_plugin-h.html) functions, which are now the go to for new plugins.

Currently the only option is HTTP authentication, which is done by calling the config endpoints with a POST request containing the user and request information.

## Configuration

The root `mosquitto.conf` file on this repo provides an examples configuration. There are 3 required options:

- `plugin`
ex. `plugin /mosquitto/plugins/libauth_plugin.so`
This will link the plugin dynamic library file, which by the build process is always this path.
- `auth_opt_user_auth_url`
ex. `auth_opt_user_auth_url http://host.docker.internal:8181/my/auth/path`
This is the URL that will be called with user information. If the request returns a status 200, the request is considered OK, otherwise access is denied.
- `auth_opt_acl_auth_url`
ex. `auth_opt_acl_auth_url http://host.docker.internal:8181/my/authorization/path`
This is the URL that will be called with user and topic information, for ACL checks. If the request returns a status 200, the request is considered OK, otherwise access is denied.

## Specification

Internally, on attempts to connect to the broker as a new user, or perform topic actions, the plugin will do HTTP calls with the following contractss:

### User auth
```
POST <user_auth_url>
Content-Type: application/json
User-Agent: mosquitto-client
Authorization: Bearer <username>

Body 
{
  "username": "<username>",
  "password": "<password>",
  "client_id": "<client_id>"
}

```

### ACL auth

```
POST <user_acl_url>
Content-Type: application/json
User-Agent: mosquitto-client
Authorization: Bearer <username>

Body 
{
  "username": "<username>",
  "client_id": "<client_id>",
  "topic": "<topic>",
  "access": 1 // 1 read, 2 write, 3 subscribe
}
```

## Run

### Docker

Currently theres a debian build / runtime, as well as a root docker compose which spins up the broker with the plugin.

`docker compose up --build`

### Build

If the required build paths are provided for the mosquitto headers and libcurl, the code can also be built outside of the docker context with:

`cmake -S . -B build && cmake --build build`