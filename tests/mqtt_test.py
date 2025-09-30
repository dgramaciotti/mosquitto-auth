import os
import time
import paho.mqtt.client as mqtt

from server.main import ALLOWED_PASSWORD, ALLOWED_TOPIC, ALLOWED_USERNAME

BROKER_HOST = os.getenv("TEST_BROKER_HOST", "mosquitto-auth")
BROKER_PORT = os.getenv("TEST_BROKER_PORT", 9001)

messages = []

def on_message(client, userdata, msg):
    messages.append(msg.payload.decode())

def create_client(username=None, password=None):
    client = mqtt.Client(transport="websockets")
    client.on_message = on_message
    if username and password:
        client.username_pw_set(username, password)
    return client

def test_mqtt_and_auth():
    clients = []
    for n in range(5):
        client = create_client(ALLOWED_USERNAME, ALLOWED_PASSWORD)
        client.connect(BROKER_HOST, BROKER_PORT, 60)
        clients.append(client)
        client.loop_start()
        client.subscribe(ALLOWED_TOPIC)
   
    time.sleep(0.5)

    for n, client in enumerate(clients):
        client.publish(ALLOWED_TOPIC, f"hello from {n}")

    time.sleep(0.5)

    for client in clients:
        client.loop_stop()
        client.disconnect()
        
    for n in range(5):
        expected_message = f"hello from {n}"
        assert expected_message in messages, f"Message '{expected_message}' not found in received messages."

def test_mqtt_empty_auth():
    def on_connect(client, userdata, flags, rc, properties=None):
        assert rc != 0
    client = create_client()
    client.on_connect = on_connect
    client.connect(BROKER_HOST, BROKER_PORT, 60)
        
def test_mqtt_acl_failure():
    failure_status = False
    def on_subscribe(client, userdata, mid, reason_code_list, props=None):
        nonlocal failure_status
        failure_status = reason_code_list[0].is_failure
            
    client = mqtt.Client(transport="websockets", protocol=mqtt.MQTTv5)
    
    client.username_pw_set(ALLOWED_USERNAME, ALLOWED_PASSWORD)
    client.on_subscribe = on_subscribe
    client.connect(BROKER_HOST, BROKER_PORT, 60)
    client.loop_start()

    client.subscribe("some/other/topic")
    time.sleep(0.25)
    assert failure_status
