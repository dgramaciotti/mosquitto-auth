# Tests

This folder consists of docker configuration files, a fast-api simple server to be used for authentication and test files.

## Setup

You can use `docker` to setup and run, or change configuration and run with [venv](https://docs.python.org/3/library/venv.html) on a local setup.

## Run

1. Check into the tests folder
2. `docker compose up` will set up the `mosquitto` broker and a simple `fastAPI` server with endpoints that will be called for authentication
3. Run all the tests with `docker compose run --rm test-runner`


## Load Test
1. Run this test with `docker compose run --rm load-test`


### Performance Metrics
- **Average Throughput:** represents the rate of messages sent to the broker per second.
- **Users:** number of users logged to the broker
- **Topics:** topics of the messages
- **Messages Sent:** a random message just for load test purpose.
- **Unique Messages Received:** messages that were sent and returned.  
- **Unique Messages Lost:** messages that were sent but **not** returned.
