import os
import time
import paho.mqtt.client as mqtt

BROKER_HOST = os.getenv("TEST_BROKER_HOST", "mosquitto-auth")
BROKER_PORT = os.getenv("TEST_BROKER_PORT", 9001)

messages = []

def on_message(client, userdata, msg):
    messages.append(msg.payload.decode())

def test_mqtt_and_auth():
    # Connect to Mosquitto
    client = mqtt.Client(transport="websockets")
    client.on_message = on_message
    client.connect(BROKER_HOST, BROKER_PORT, 60)

    client.loop_start()
    client.subscribe("test/topic")
    time.sleep(1)

    client.publish("test/topic", "hello")
    time.sleep(1)

    client.loop_stop()
    client.disconnect()

    assert "hello" in messages
