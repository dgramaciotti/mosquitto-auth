from locust import User, TaskSet, events, task, between
import paho.mqtt.client as mqtt
import time

COUNTClient = 0
broker_address="mosquitto-auth"
broker_port = 9001
REQUEST_TYPE = 'MQTT'
PUBLISH_TIMEOUT = 10000

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

class PublishTask(TaskSet):
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
        topic = "devices/readings/mydevice"
        payload = "Device - " + str(self.client._client_id)
        MQTTMessageInfo = self.client.publish(topic,payload,qos=0, retain=False)
        # mid  === message id
        pub_mid = MQTTMessageInfo.mid
        print("Mid = " + str(pub_mid))
        self.client.pubmessage[pub_mid] = Message(
                    REQUEST_TYPE, 0, topic, payload, self.start_time, PUBLISH_TIMEOUT, str(self.client._client_id)
                    )
        MQTTMessageInfo.wait_for_publish()
        
        time.sleep(5)

    wait_time = between(0.5, 10)

class MQTTLocust(User):
    tasks = {PublishTask}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        increment()
        client_name = f"Device-{COUNTClient}"
        self.client = mqtt.Client(transport="websockets", client_id=client_name, protocol=mqtt.MQTTv5, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_publish = self.on_publish
        self.client.pubmessage  = {}

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
            fire_locust_success(
            request_type=REQUEST_TYPE,
            name='connect',
            response_time=0,
            response_length=0
            )
        

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        print(f"Disconnected result code: {reason_code}")

    def on_publish(self, client, userdata, mid, reason_code, properties):
        end_time = time.time()
        message = client.pubmessage.pop(mid, None)
        if not message:
            fire_locust_failure(
                request_type=REQUEST_TYPE,
                name=str(self.client._client_id),
                response_time=0,
                response_length=0,
                exception=Exception(f"Publish ack for unknown mid={mid}")
            )
            return
        total_time =  time_delta(message.start_time, end_time)
        fire_locust_success(
            request_type=REQUEST_TYPE,
            name=str(self.client._client_id),
            response_time=total_time,
            response_length=len(message.payload)
            )