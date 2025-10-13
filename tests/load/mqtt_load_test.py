import uuid
from locust import User, TaskSet, events, task, between
import paho.mqtt.client as mqtt
import time

COUNTClient = 0
broker_address="mosquitto-auth"
broker_port = 9001
REQUEST_TYPE = 'MQTT'
PUBLISH_TIMEOUT = 10000
PUBLISH_MAX_DELAY=5
PUBLISH_MIN_DELAY=2

def fire_locust_success(**kwargs):
    events.request.fire(exception=None, **kwargs)

def fire_locust_failure(**kwargs):
    events.request.fire(exception=kwargs.pop("exception"), **kwargs)

def increment():
    global COUNTClient
    COUNTClient = COUNTClient+1

def time_delta(t1, t2):
    return int((t2 - t1)*1000)

class Message(object):
    def __init__(self, type, qos, topic, payload, start_time, timeout, name):
        self.type = type,
        self.qos = qos,
        self.topic = topic
        self.payload = payload
        self.start_time = start_time
        self.timeout = timeout
        self.name = name

class MqttTask(TaskSet):
    def on_start(self):
        self.client.connect_async(host=broker_address, port=broker_port, keepalive=60)
        self.client.loop_start()

    def on_stop(self):
        self.client.disconnect()
        self.client.loop_stop()

    @task(1)
    def task_pub(self):
        if not self.client.is_connected():
            return
        self.start_time = time.time()
        topic = f"{self.client._client_id}/test/topic"
        msg_id = str(uuid.uuid4())
        payload = f"{msg_id}:Device-{self.client._client_id}"
        MQTTMessageInfo = self.client.publish(topic,payload,qos=2, retain=True)
        # mid  === message id
        pub_mid = MQTTMessageInfo.mid
        print("Mid = " + str(pub_mid))
        self.client.pubmessage[pub_mid] = Message(
                    REQUEST_TYPE, 0, topic, payload, self.start_time, PUBLISH_TIMEOUT, str(self.client._client_id)
                    )
        self.client.submessage[msg_id] = Message(
                    REQUEST_TYPE, 0, topic, payload, self.start_time, PUBLISH_TIMEOUT, str(self.client._client_id)
                    )
        MQTTMessageInfo.wait_for_publish()     

    wait_time = between(PUBLISH_MAX_DELAY, PUBLISH_MIN_DELAY)

class MQTTLocust(User):
    tasks = {MqttTask}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        increment()
        client_name = f"Device-{COUNTClient}"
        self.client = mqtt.Client(transport="websockets", client_id=client_name, protocol=mqtt.MQTTv5, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.username_pw_set(f"testuser-{client_name}", "testpassword")
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_publish = self.on_publish
        self.client.on_subscribe = self.on_subscribe
        self.client.on_message = self.on_message
        self.client.pubmessage  = {}
        self.client.submessage = {}

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
         if reason_code.is_failure:
            fire_locust_failure(
            request_type=REQUEST_TYPE,
            name='connect',
            response_time=0,
            response_length=0,
            exception=Exception(f"Connection failed with reason_code={reason_code}")
            )
         else:
            topic = f"{self.client._client_id}/test/topic"
            self.client.subscribe(topic)
            fire_locust_success(
                request_type=REQUEST_TYPE,
                name='connect',
                response_time=0,
                response_length=0
            )
        

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        print(f"Disconnected result code: {reason_code}")

    def on_subscribe(self, client, userdata, mid, reason_code_list, properties):
        if reason_code_list[0].is_failure:
            fire_locust_failure(
                request_type=REQUEST_TYPE,
                name=f"{str(self.client._client_id)}-subscribe",
                response_time=0,
                response_length=0,
                exception=Exception(f"Failed to subscribe to topic -  {reason_code_list}")
            )
            return  
    
    def on_message(self, client, userdata, message):
        end_time = time.time()
        if not message:
            fire_locust_failure(
                request_type=REQUEST_TYPE,
                name=f"{str(self.client._client_id)}-receive_message",
                response_time=0,
                response_length=0,
                exception=Exception(f"No message on_message callback.")
            )
            return
        payload_str = message.payload.decode("utf-8")

        # Expecting format: "<uuid>:<data>"
        parts = payload_str.split(":", 1)
        msg_id = parts[0] if len(parts) > 1 else None

        if not msg_id or msg_id not in client.submessage:
            # We don't have a matching outgoing publish
            print(f"[WARN] Received unmatched message: {payload_str}")
            return
        msg = client.submessage.pop(msg_id)
        total_time =  time_delta(msg.start_time, end_time)
        fire_locust_success(
        request_type=REQUEST_TYPE,
        name=f"{str(self.client._client_id)}-receive_message",
        response_time=total_time,
        response_length=len(msg.payload)
        )

    def on_publish(self, client, userdata, mid, reason_code, properties):
        end_time = time.time()
        message = client.pubmessage.pop(mid, None)
        if not message:
            fire_locust_failure(
                request_type=REQUEST_TYPE,
                name=f"{str(self.client._client_id)}-publish",
                response_time=0,
                response_length=0,
                exception=Exception(f"Publish ack for unknown mid={mid}")
            )
            return
        total_time =  time_delta(message.start_time, end_time)
        fire_locust_success(
            request_type=REQUEST_TYPE,
            name=f"{str(self.client._client_id)}-publish",
            response_time=total_time,
            response_length=len(message.payload)
            )