import os
import time
import threading
import random
import string
import pytest
import paho.mqtt.client as mqtt


class MQTTLoadTester:
    def __init__(self):
        # config from env or defaults
        self.BROKER_HOST = os.getenv("TEST_BROKER_HOST", "mosquitto-auth")
        self.BROKER_PORT = int(os.getenv("TEST_BROKER_PORT", 9001))  # WebSockets port
        self.TOPICS = [f"load/topic{i}" for i in range(5)]
        self.NUM_USERS = 50
        self.MESSAGES_PER_USER = 20
        self.PAYLOAD_SIZE = 1024
        self.TIMEOUT = 15
        self.LOG_FILE = "mqtt_load_test_realistic_log.txt"

    def random_payload(self, size=None):
        """
        Return a random alphanumeric payload of given size (default: PAYLOAD_SIZE).
        """
        if size is None:
            size = self.PAYLOAD_SIZE
        return ''.join(random.choices(string.ascii_letters + string.digits, k=size))

    def create_client(self, username, password, messages, connect_timeout=5, sub_timeout=5):
        """
        Create an MQTT client and ensure:
         - it connects (waits for on_connect)
         - it subscribes to all topics and waits for on_subscribe acks

        Returns the client object. If connection fails the client is returned
        anyway but with a log entry.
        """
        # unique client id to avoid collisions when many clients connect quickly
        client_id = f"{username}-{int(time.time()*1000)}-{random.randint(0,9999)}"
        client = mqtt.Client(client_id=client_id, transport="websockets")

        # synchronization primitives and counters
        connected_evt = threading.Event()
        subscribe_counter = {"n": 0}
        expected_subs = len(self.TOPICS)

        # message callback: store received messages (topic, payload, receive_time)
        def on_message(c, userdata, msg):
            receive_time = time.time()
            try:
                payload = msg.payload.decode()
            except Exception:
                payload = str(msg.payload)
            messages.append((msg.topic, payload, receive_time))
            # write short log entry (first 50 chars)
            with open(self.LOG_FILE, "a") as f:
                f.write(f"[RECEIVE] {username} received at {msg.topic}: {payload[:50]}...\n")

        # on_connect: set event on successful connection
        def on_connect(c, userdata, flags, rc):
            if rc == 0:
                connected_evt.set()
                with open(self.LOG_FILE, "a") as f:
                    f.write(f"[CONNECT] {username} connected (client_id={client_id}).\n")
            else:
                with open(self.LOG_FILE, "a") as f:
                    f.write(f"[CONNECT-ERR] {username} rc={rc}\n")

        # on_subscribe: increment counter so we know how many subscribe acks arrived
        def on_subscribe(c, userdata, mid, granted_qos):
            subscribe_counter["n"] += 1

        client.on_message = on_message
        client.on_connect = on_connect
        client.on_subscribe = on_subscribe

        client.username_pw_set(username, password)

        # Use connect_async + loop_start so the background thread handles network ops
        try:
            client.connect_async(self.BROKER_HOST, self.BROKER_PORT, keepalive=60)
        except Exception as e:
            with open(self.LOG_FILE, "a") as f:
                f.write(f"[CONNECT-EXCEPTION] {username} connect_async failed: {e}\n")
            # still start loop to allow retries if desired
        client.loop_start()

        # wait for on_connect up to connect_timeout seconds
        if not connected_evt.wait(timeout=connect_timeout):
            with open(self.LOG_FILE, "a") as f:
                f.write(f"[WARN] {username} didn't confirm connect within {connect_timeout}s.\n")
            # we continue — sometimes broker accepts subscribe requests queued before connect,
            # but usually it's better to bail or log. We'll attempt to subscribe anyway.

        # subscribe to topics and wait for subscribe acks (up to sub_timeout)
        for topic in self.TOPICS:
            try:
                client.subscribe(topic)
            except Exception as e:
                with open(self.LOG_FILE, "a") as f:
                    f.write(f"[SUBSCRIBE-EXCEPTION] {username} subscribe({topic}) failed: {e}\n")

        # wait for expected subscribe acks (or timeout)
        t0 = time.time()
        while subscribe_counter["n"] < expected_subs and (time.time() - t0) < sub_timeout:
            time.sleep(0.01)

        if subscribe_counter["n"] < expected_subs:
            with open(self.LOG_FILE, "a") as f:
                f.write(
                    f"[WARN] {username} got {subscribe_counter['n']}/{expected_subs} subscribe acks "
                    f"within {sub_timeout}s. Broker may not deliver messages yet.\n"
                )

        # small safety delay so subscriptions are fully realized on broker
        time.sleep(0.05)

        return client

    def user_task(self, index, messages_list, sent_times):
        """
        Task executed by each simulated user (runs in its own thread).
        - creates a client (which waits for connect + subscribe)
        - publishes messages
        - keeps the connection alive for TIMEOUT seconds to receive messages
        - stops and disconnects
        """
        username = f"user{index}"
        password = f"pass{index}"
        messages = messages_list[index]

        # create client and ensure subscription readiness as best as possible
        client = self.create_client(username, password, messages)

        # publish a number of messages, recording send times locally (per-user list)
        for i in range(self.MESSAGES_PER_USER):
            topic = random.choice(self.TOPICS)
            payload = f"{username}_msg{i}_" + self.random_payload(900)
            send_time = time.time()
            sent_times.append((topic, payload, send_time))

            try:
                client.publish(topic, payload)  # default QoS 0
            except Exception as e:
                with open(self.LOG_FILE, "a") as f:
                    f.write(f"[PUBLISH-ERR] {username} publish failed: {e}\n")

            # log the send (short payload preview)
            with open(self.LOG_FILE, "a") as f:
                f.write(f"[SEND] {username} sent to {topic}: {payload[:50]}...\n")

            # small random delay to simulate realistic behaviour
            time.sleep(random.uniform(0.01, 0.1))

        # keep client alive so messages can arrive
        t0 = time.time()
        while time.time() - t0 < self.TIMEOUT:
            time.sleep(0.05)

        # stop background loop and disconnect cleanly
        client.loop_stop()
        try:
            client.disconnect()
        except Exception:
            pass

    def run_test(self, messages_list, sent_times):
        """
        Spawn NUM_USERS threads to run user_task concurrently, wait for completion,
        then compute and return a summary string of statistics.
        """
        threads = []
        start_time = time.time()

        # create and start threads
        for i in range(self.NUM_USERS):
            t = threading.Thread(target=self.user_task, args=(i, messages_list, sent_times[i]))
            t.daemon = True
            t.start()
            threads.append(t)

        # wait for all threads
        for t in threads:
            t.join()

        end_time = time.time()

        # compute stats
        total_sent = self.NUM_USERS * self.MESSAGES_PER_USER
        total_received = sum(len(msgs) for msgs in messages_list)

        latencies = []
        payload_to_sendtime = {}
        for user_sent in sent_times:
            for topic, payload, t_send in user_sent:
                payload_to_sendtime[payload] = t_send

        unique_payloads_sent = set(payload_to_sendtime.keys())
        unique_payloads_received = set()

        for user_received in messages_list:
            for topic, payload, t_receive in user_received:
                unique_payloads_received.add(payload)
                if payload in payload_to_sendtime:
                    latencies.append(t_receive - payload_to_sendtime[payload])

        lost = len(unique_payloads_sent - unique_payloads_received)
        duration = end_time - start_time

        latency_avg = sum(latencies) / len(latencies) if latencies else 0
        latency_min = min(latencies) if latencies else 0
        latency_max = max(latencies) if latencies else 0

        summary = (
            f"==== Load test finished ====\n"
            f"Users: {self.NUM_USERS}\n"
            f"Topics: {len(self.TOPICS)}\n"
            f"Messages sent: {total_sent}\n"
            f"Unique messages received: {len(unique_payloads_received)}\n"
            f"Unique messages lost: {lost}\n"
            f"Total test duration: {duration:.2f}s\n"
            f"Average throughput: {total_received / duration:.2f} msgs/s\n"
            f"Average latency: {latency_avg:.3f}s\n"
            f"Minimum latency: {latency_min:.3f}s\n"
            f"Maximum latency: {latency_max:.3f}s\n"
        )
        return summary


# ----------------- Pytest integration -----------------

@pytest.fixture
def mqtt_load_test():
    """
    Prepare tester and data structures for pytest.
    """
    tester = MQTTLoadTester()
    open(tester.LOG_FILE, "w").close()  # clear previous log
    messages_list = [[] for _ in range(tester.NUM_USERS)]
    sent_times = [[] for _ in range(tester.NUM_USERS)]
    return tester, messages_list, sent_times


def test_mqtt_load_realistic(mqtt_load_test):
    """
    Run load test and save summary.
    """
    tester, messages_list, sent_times = mqtt_load_test
    summary = tester.run_test(messages_list, sent_times)

    print(summary)
    with open(tester.LOG_FILE, "a") as f:
        f.write(summary)

    # Basic checks: the test executed and produced a summary string
    assert "Load test finished" in summary
    assert "Users" in summary
