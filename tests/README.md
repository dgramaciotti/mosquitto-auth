# Tests

This folder consists of docker configuration files, a fast-api simple server to be used for authentication and test files.

## Setup

You can use `docker` to setup and run, or change configuration and run with [venv](https://docs.python.org/3/library/venv.html) on a local setup.

## Run

1. Check into the tests folder
2. `docker compose up` will set up the `mosquitto` broker and a simple `fastAPI` server with endpoints that will be called for authentication
3. Run the tests with `docker compose run --rm test-runner`


## Load Test Report

### Performance Metrics
- **Average Throughput:** 136.97 msgs/s
- **Users:** 50  
- **Topics:** 5  
- **Messages Sent:** 1000  
- **Unique Messages Received:** 243  
- **Unique Messages Lost:** 757 

### Observations
- The system successfully processed **24.3%** of the messages.  
- A significant portion (**75.7%**) of the messages were lost.  
