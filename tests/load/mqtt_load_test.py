import os
import sys
import json
import time
import threading
import random
import string
import logging
import pytest
import paho.mqtt.client as mqtt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

class MQTTLoadTester:
    def __init__(self, settings_file="settings.json"):
        logging.info("Initializing MQTTLoadTester")

        # Check if settings file exists
        if not os.path.exists(settings_file):
            logging.error(f"Settings file {settings_file} not found")
            raise FileNotFoundError(f"Arquivo {settings_file} não encontrado.")

        # Load settings from JSON file
        with open(settings_file, "r", encoding="utf-8") as f:
            settings = json.load(f)
        logging.info(f"Settings loaded from {settings_file}")

        # Configuration from environment variables or defaults
        self.BROKER_HOST = os.getenv("TEST_BROKER_HOST", "mosquitto-auth")
        self.BROKER_PORT = int(os.getenv("TEST_BROKER_PORT", 9001))  # WebSockets port
        self.TOPICS = [f"load/topic{i}" for i in range(5)]  # Topics for load test
        self.NUM_USERS = settings.get("NUM_USERS", 50)
        self.MESSAGES_PER_USER = settings.get("MESSAGES_PER_USER", 20)
        self.PAYLOAD_SIZE = settings.get("PAYLOAD_SIZE", 1024)
        self.TIMEOUT = settings.get("TIMEOUT", 15)

        # Validate payload size
        if self.PAYLOAD_SIZE < 0:
            logging.error("Invalid payload size")
            raise ValueError("PAYLOAD_SIZE must be >= 0")

        # Prepare default payload
        self.PAYLOAD = "A" * self.PAYLOAD_SIZE
        self.PAYLOAD_BYTES = self.PAYLOAD.encode("utf-8")
        logging.info(f"MQTTLoadTester initialized with {self.NUM_USERS} users")

    def create_client(self, username, password, messages):
        client_id = f"{username}-{int(time.time()*1000)}-{random.randint(0,9999)}"
        client = mqtt.Client(client_id=client_id, transport="websockets")
        logging.info(f"Creating MQTT client {client_id}")

        # Callback para mensagens recebidas
        def on_message(c, userdata, msg):
            try:
                payload = msg.payload.decode()
            except Exception:
                payload = str(msg.payload)
            messages.append((msg.topic, payload, time.time()))
            logging.debug(f"Message received: topic={msg.topic}, payload={payload}")

        # Callback para conexão
        def on_connect(c, userdata, flags, rc):
            if rc == 0:
                logging.info(f"Client {client_id} connected successfully")
                for topic in self.TOPICS:
                    client.subscribe(topic)
                    logging.debug(f"Subscribed to topic: {topic}")
            else:
                logging.warning(f"Client {client_id} failed to connect, rc={rc}")

        client.on_message = on_message
        client.on_connect = on_connect
        client.username_pw_set(username, password)

        client.connect_async(self.BROKER_HOST, self.BROKER_PORT, keepalive=60)
        client.loop_start()  # loop não bloqueante
        logging.info(f"Client {client_id} loop started")

        return client

    def user_task(self, index, messages_list, sent_times):
        username = f"user{index}"
        password = f"pass{index}"
        messages = messages_list[index]
        logging.info(f"Starting task for {username}")

        # Create and connect MQTT client
        client = self.create_client(username, password, messages)

        # Send messages
        for i in range(self.MESSAGES_PER_USER):
            topic = random.choice(self.TOPICS)
            payload = f"{username}_msg{i}_" + self.PAYLOAD
            send_time = time.time()
            sent_times.append((topic, payload, send_time))
            try:
                client.publish(topic, payload)
                logging.debug(f"{username} published message {i} to {topic}")
            except Exception as e:
                logging.error(f"Error publishing message {i} from {username}: {e}")

            # Print single-line progress
            total_sent = sum(len(user) for user in sent_times)
            total_messages = self.NUM_USERS * self.MESSAGES_PER_USER
            print(f"\rProgress: {total_sent/total_messages*100:.1f}%", end="", flush=True)
            time.sleep(random.uniform(0.01, 0.1))

        # Keep client alive to receive messages
        t0 = time.time()
        while time.time() - t0 < self.TIMEOUT:
            time.sleep(0.05)

        # Stop client loop and disconnect
        client.loop_stop()
        try:
            client.disconnect()
            logging.info(f"{username} disconnected")
        except Exception as e:
            logging.error(f"Error disconnecting {username}: {e}")

    def run_test(self, messages_list, sent_times):
        threads = []
        start_time = time.time()
        logging.info("Starting load test")

        # Create threads for each simulated user
        for i in range(self.NUM_USERS):
            t = threading.Thread(target=self.user_task, args=(i, messages_list, sent_times[i]))
            t.daemon = True
            t.start()
            threads.append(t)

        # Wait for all threads to finish
        for t in threads:
            t.join()

        print("\rProgress: 100.0%")  # Finalize progress
        logging.info("All user tasks completed")

        end_time = time.time()
        total_sent = self.NUM_USERS * self.MESSAGES_PER_USER
        total_received = sum(len(msgs) for msgs in messages_list)

        # Calculate message latencies
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

        logging.info(f"Load test finished: {total_sent} messages sent, {total_received} received, {lost} lost")

        # Prepare summary report
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
    tester = MQTTLoadTester()
    messages_list = [[] for _ in range(tester.NUM_USERS)]
    sent_times = [[] for _ in range(tester.NUM_USERS)]
    return tester, messages_list, sent_times

# Entrypoint
def test_mqtt_load_realistic(mqtt_load_test):
    tester, messages_list, sent_times = mqtt_load_test
    summary = tester.run_test(messages_list, sent_times)
    print(summary)
    assert "Load test finished" in summary
    assert "Users" in summary
