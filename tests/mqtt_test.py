import os
import time
import paho.mqtt.client as mqtt

BROKER_HOST = os.getenv("TEST_BROKER_HOST", "mosquitto-auth")
BROKER_PORT = os.getenv("TEST_BROKER_PORT", 9001)

messages = []

def on_message(client, userdata, msg):
    messages.append(msg.payload.decode())

def create_client(username, password):
    client = mqtt.Client(transport="websockets")
    client.on_message = on_message
    client.username_pw_set(username, password)
    return client

def test_mqtt_and_auth():
    clients = []
    for n in range(5):
        client = create_client(f"my_username {n}", f"my_password {n}")
        client.connect(BROKER_HOST, BROKER_PORT, 60)
        clients.append(client)
        client.loop_start()
        client.subscribe("test/topic")
   
    time.sleep(0.5)

    for n, client in enumerate(clients):
        client.publish("test/topic", f"hello from {n}")

    time.sleep(0.5)

    for client in clients:
        client.loop_stop()
        client.disconnect()
        
    for n in range(5):
        expected_message = f"hello from {n}"
        assert expected_message in messages, f"Message '{expected_message}' not found in received messages."
    
