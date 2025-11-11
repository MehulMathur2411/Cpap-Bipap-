from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder
import time
import json
from concurrent.futures import Future
import os

# ---------- AWS IoT Configuration ----------
ENDPOINT = "a2jqpfwttlq1yk-ats.iot.us-east-1.amazonaws.com"
CLIENT_ID = "iotconsole-560333af-04b9-45fb-8cd0-4ef4cd819d92"

BASE_PATH = r"C:\Users\tanya\OneDrive\Desktop\CPAP\AWS"
PATH_TO_CERTIFICATE = os.path.join(BASE_PATH, "6e5d12437ffc7b19a750505da172d382b6e81026243aa254bce059b8bc45796f-certificate.pem.crt")
PATH_TO_PRIVATE_KEY = os.path.join(BASE_PATH, "6e5d12437ffc7b19a750505da172d382b6e81026243aa254bce059b8bc45796f-private.pem.key")
PATH_TO_AMAZON_ROOT_CA = os.path.join(BASE_PATH, "AmazonRootCA1.pem")

TOPIC = "esp32/data1"
ACK_TOPIC = "esp32/data"

SAMPLE_DATA = {
    "device_status": 1,
    "device_data": "*,141025,141025,1300,1400,1,4,5,8,5,4,2,9,1,8,7,3,9,3,5,2,1,2,3,12345678,#"
    
}

QUEUE_FILE = os.path.join(BASE_PATH, "pending_data.json")

# Global variables
pending_messages = []
is_connected = False
ack_received = True


# ---------- Load/Save Pending Messages ----------
def load_pending():
    global pending_messages
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, 'r') as f:
                pending_messages = json.load(f)
            print(f"Loaded {len(pending_messages)} pending messages from file: {pending_messages}")
        except Exception as e:
            print(f"Error loading pending messages: {e}")
            pending_messages = []
    else:
        print(f"No pending data file found at {QUEUE_FILE}")
        pending_messages = []

def save_pending():
    global pending_messages
    try:
        with open(QUEUE_FILE, 'w') as f:
            json.dump(pending_messages, f)
        print("Pending messages saved to file.")
    except Exception as e:
        print(f"Error saving pending messages: {e}")

# ---------- Check for Duplicate Sample Data ----------
def is_duplicate_sample(data):
    global pending_messages
    for msg in pending_messages:
        if data == msg:
            return True
    return False

# ---------- Callback for Received Messages ----------
def on_message_received(topic, payload, dup, qos, retain, **kwargs):
    global ack_received
    try:
        print(f"\nReceived message from topic '{topic}':")
        message = json.loads(payload.decode('utf-8'))
        print(f"Message content: {json.dumps(message, indent=2)}")
        if topic == ACK_TOPIC and message.get("acknowledgment") == 1:
            print("Acknowledgment received")
            ack_received = True
        print("Message received successfully!")
    except Exception as e:
        print(f"Error processing received message: {e}")

# ---------- Connection Callbacks ----------
def on_connection_interrupted(connection, error, **kwargs):
    global is_connected
    is_connected = False
    print(f"Connection interrupted. Error: {error}. Device is now DISCONNECTED.")

def on_connection_resumed(connection, return_code, session_present, **kwargs):
    global is_connected, ack_received
    is_connected = True
    ack_received = True  
    print(f"Connection resumed. Return code: {return_code}, Session present: {session_present}. Device is now CONNECTED.")
    load_pending()
    if not session_present:
        subscribe_to_topics(connection)
    if pending_messages:
        send_pending(connection)

# ---------- Send Data Function ----------
def send_data(data, connection):
    global ack_received
    message_json = json.dumps(data)
    print(f"Publishing message to topic '{TOPIC}':\n{message_json}")
    try:
        publish_future, packet_id = connection.publish(
            topic=TOPIC,
            payload=message_json,
            qos=mqtt.QoS.AT_LEAST_ONCE
        )
        publish_future.result(timeout=10)
        print("Data sent to AWS IoT Core! Waiting for acknowledgment...")
        print(f"Packet ID: {packet_id}")
        ack_received = False
        return True
    except Exception as e:
        print(f"Publish failed: {e}")
        return False

# ---------- Send Pending Messages ----------
def send_pending(connection):
    global pending_messages, ack_received
    print(f"send_pending: ack_received={ack_received}, pending_messages_count={len(pending_messages)}")
    if not is_connected:
        print("Cannot send pending messages: Device is DISCONNECTED.")
        return
    if pending_messages and ack_received:
        data = pending_messages[0]
        print(f"Attempting to send pending message: {data}")
        if send_data(data, connection):
            start_time = time.time()
            while not ack_received and time.time() - start_time < 10:
                time.sleep(0.1)
            if ack_received:
                print("Message acknowledged, removing from queue")
                pending_messages.pop(0)
                save_pending()
            else:
                print("No acknowledgment received within timeout. Proceeding to next message (fallback).")
                pending_messages.pop(0)
                save_pending()
        else:
            print("Failed to send pending message.")

# ---------- Subscribe to Topics ----------
def subscribe_to_topics(connection):
    if not is_connected:
        print("Cannot subscribe: Device is DISCONNECTED.")
        return False
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Subscribing to topic '{TOPIC}' (attempt {attempt + 1})...")
            subscribe_future, packet_id = connection.subscribe(
                topic=TOPIC,
                qos=mqtt.QoS.AT_LEAST_ONCE,
                callback=on_message_received
            )
            subscribe_result = subscribe_future.result(timeout=10)
            print(f"Subscribed to topic '{TOPIC}' with QoS: {subscribe_result['qos']}")
            print(f"Subscription packet ID: {packet_id}")

            print(f"Subscribing to acknowledgment topic '{ACK_TOPIC}' (attempt {attempt + 1})...")
            subscribe_future, packet_id = connection.subscribe(
                topic=ACK_TOPIC,
                qos=mqtt.QoS.AT_LEAST_ONCE,
                callback=on_message_received
            )
            subscribe_result = subscribe_future.result(timeout=10)
            print(f"Subscribed to topic '{ACK_TOPIC}' with QoS: {subscribe_result['qos']}")
            print(f"Subscription packet ID: {packet_id}")
            return True
        except Exception as e:
            print(f"Subscription failed: {e}. Retrying..." if attempt < max_retries - 1 else f"Subscription failed after {max_retries} attempts: {e}")
            time.sleep(1)
    return False

# ---------- AWS IoT Connection Setup ----------
io.init_logging(io.LogLevel.Error, 'stderr')
event_loop_group = io.EventLoopGroup(1)
host_resolver = io.DefaultHostResolver(event_loop_group)
client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

mqtt_connection = mqtt_connection_builder.mtls_from_path(
    endpoint=ENDPOINT,
    cert_filepath=PATH_TO_CERTIFICATE,
    pri_key_filepath=PATH_TO_PRIVATE_KEY,
    client_bootstrap=client_bootstrap,
    ca_filepath=PATH_TO_AMAZON_ROOT_CA,
    on_connection_interrupted=on_connection_interrupted,
    on_connection_resumed=on_connection_resumed,
    client_id=CLIENT_ID,
    clean_session=False,
    keep_alive_secs=30
)

# Load any pending messages from disk before attempting to connect
load_pending()

# Connect with retry every 1 second
while not is_connected:
    print(f"Connecting to {ENDPOINT} with client ID '{CLIENT_ID}'...")
    try:
        connect_future: Future = mqtt_connection.connect()
        connect_future.result(timeout=10)
        is_connected = True
        print("Connected successfully to AWS IoT Core! Device is now CONNECTED.")
        subscribe_to_topics(mqtt_connection)
        send_pending(mqtt_connection)
    except Exception as e:
        print(f"Connection failed: {e}. Device is DISCONNECTED. Retrying in 1 second...")
        time.sleep(1)

# Publish sample data
if not is_connected:
    print("Cannot send sample data: Device is DISCONNECTED.")
    if not is_duplicate_sample(SAMPLE_DATA):
        pending_messages.append(SAMPLE_DATA)
        save_pending()
else:
    if not send_data(SAMPLE_DATA, mqtt_connection):
        if not is_duplicate_sample(SAMPLE_DATA):
            pending_messages.append(SAMPLE_DATA)
            save_pending()

try:
    print("\nKeeping connection alive to receive messages and check for pending data (press Ctrl+C to exit)...")
    while True:
        print(f"Device connection status: {'CONNECTED' if is_connected else 'DISCONNECTED'}")
        if is_connected:
            if pending_messages and ack_received:
                send_pending(mqtt_connection)
        else:
            print("Attempting to reconnect...")
            try:
                connect_future: Future = mqtt_connection.connect()


                
                connect_future.result(timeout=10)
                is_connected = True
                print("Reconnected successfully to AWS IoT Core! Device is now CONNECTED.")
                subscribe_to_topics(mqtt_connection)
                send_pending(mqtt_connection)
            except Exception as e:
                print(f"Reconnection failed: {e}. Retrying in 1 second...")
            new_sample_data = SAMPLE_DATA.copy()
            if not is_duplicate_sample(new_sample_data):
                pending_messages.append(new_sample_data)
                save_pending()
            print("New data queued to pending_data.json since device is DISCONNECTED.")
        time.sleep(2 if not is_connected else 1)
except KeyboardInterrupt:
    print("\nDisconnecting from AWS IoT Core...")
    disconnect_future = mqtt_connection.disconnect()
    disconnect_future.result()
    is_connected = False
    print("Disconnected successfully! Device is now DISCONNECTED.")