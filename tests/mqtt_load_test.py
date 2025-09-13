import os
import time
import threading
import random
import string
import pytest
import paho.mqtt.client as mqtt

BROKER_HOST = os.getenv("TEST_BROKER_HOST", "mosquitto-auth")
BROKER_PORT = int(os.getenv("TEST_BROKER_PORT", 9001))  # WebSockets

TOPICS = [f"load/topic{i}" for i in range(5)]
NUM_USERS = 50
MESSAGES_PER_USER = 20
PAYLOAD_SIZE = 1024
TIMEOUT = 15
LOG_FILE = "mqtt_load_test_realistic_log.txt"


def random_payload(size=PAYLOAD_SIZE):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=size))


def create_client(username, password, messages):
    client = mqtt.Client(transport="websockets")

    def on_message(client, userdata, msg):
        receive_time = time.time()
        payload = msg.payload.decode()
        messages.append((msg.topic, payload, receive_time))
        with open(LOG_FILE, "a") as f:
            f.write(f"[RECEIVE] {username} recebeu em {msg.topic}: {payload[:50]}...\n")

    client.on_message = on_message
    client.username_pw_set(username, password)
    client.connect(BROKER_HOST, BROKER_PORT, 60)
    client.loop_start()
    for topic in TOPICS:
        client.subscribe(topic)
    return client


def user_task(index, messages_list, sent_times):
    username = f"user{index}"
    password = f"pass{index}"
    messages = messages_list[index]
    client = create_client(username, password, messages)

    for i in range(MESSAGES_PER_USER):
        topic = random.choice(TOPICS)
        payload = f"{username}_msg{i}_" + random_payload(900)
        send_time = time.time()
        sent_times.append((topic, payload, send_time))  # registra o envio
        client.publish(topic, payload)
        with open(LOG_FILE, "a") as f:
            f.write(f"[SEND] {username} enviou em {topic}: {payload[:50]}...\n")
        time.sleep(random.uniform(0.01, 0.1))

    t0 = time.time()
    while time.time() - t0 < TIMEOUT:
        time.sleep(0.1)

    client.loop_stop()
    client.disconnect()


@pytest.fixture
def mqtt_load_test():
    # limpa log anterior
    open(LOG_FILE, "w").close()
    messages_list = [[] for _ in range(NUM_USERS)]
    sent_times = [[] for _ in range(NUM_USERS)]
    yield messages_list, sent_times


def test_mqtt_load_realistic(mqtt_load_test):
    messages_list, sent_times = mqtt_load_test
    threads = []

    start_time = time.time()
    for i in range(NUM_USERS):
        t = threading.Thread(target=user_task, args=(i, messages_list, sent_times[i]))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()
    end_time = time.time()

    # Estatísticas detalhadas
    total_sent = NUM_USERS * MESSAGES_PER_USER
    total_received = sum(len(msgs) for msgs in messages_list)

    # Calcular latências e mensagens únicas
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

    latency_avg = sum(latencies)/len(latencies) if latencies else 0
    latency_min = min(latencies) if latencies else 0
    latency_max = max(latencies) if latencies else 0

    summary = (
        f"==== Teste de carga finalizado ====\n"
        f"Usuários: {NUM_USERS}\n"
        f"Tópicos: {len(TOPICS)}\n"
        f"Mensagens enviadas: {total_sent}\n"
        f"Mensagens únicas recebidas: {len(unique_payloads_received)}\n"
        f"Mensagens perdidas (únicas): {lost}\n"
        f"Duração real do teste: {duration:.2f}s\n"
        f"Throughput médio real: {total_received / duration:.2f} msgs/s\n"
        f"Latência média: {latency_avg:.3f}s\n"
        f"Latência mínima: {latency_min:.3f}s\n"
        f"Latência máxima: {latency_max:.3f}s\n"
    )
    print(summary)
    with open(LOG_FILE, "a") as f:
        f.write(summary)
