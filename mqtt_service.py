"""MQTT service for receiving body composition measurements."""
import json
import logging
import os
from typing import Callable
import paho.mqtt.client as mqtt
import body_composition_data

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MQTTService:
    """MQTT client service for body composition data."""

    def __init__(self, broker_host="localhost", broker_port=1883,
                 on_measurement_callback: Callable = None):
        """
        Initialize MQTT service.

        Args:
            broker_host: MQTT broker hostname
            broker_port: MQTT broker port
            on_measurement_callback: Optional callback function when measurement received
        """
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.on_measurement_callback = on_measurement_callback

        # Create MQTT client
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        self.is_connected = False

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Callback when connected to MQTT broker."""
        if reason_code == 0:
            logger.info(f"Connected to MQTT broker at {self.broker_host}:{self.broker_port}")
            self.is_connected = True

            # Subscribe to openScaleSync topics
            topics = [
                ("openScaleSync/measurements/insert", 0),
                ("openScaleSync/measurements/update", 0),
            ]
            for topic, qos in topics:
                client.subscribe(topic, qos)
                logger.info(f"Subscribed to topic: {topic}")
        else:
            logger.error(f"Failed to connect to MQTT broker: {reason_code}")
            self.is_connected = False

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        """Callback when disconnected from MQTT broker."""
        logger.warning(f"Disconnected from MQTT broker: {reason_code}")
        self.is_connected = False

    def _on_message(self, client, userdata, msg):
        """Callback when a message is received."""
        try:
            # Parse JSON payload
            payload = json.loads(msg.payload.decode())
            logger.info(f"Received message on {msg.topic}: {payload}")

            # Extract measurements
            timestamp = payload.get('date')  # Unix timestamp in milliseconds
            weight = payload.get('weight')

            if timestamp and weight:
                # Optional fields (may be added by openScale-sync in the future)
                body_fat = payload.get('fat')
                muscle_mass = payload.get('muscle')
                bmi = payload.get('bmi')
                water = payload.get('water')
                bone_mass = payload.get('bone')
                visceral_fat = payload.get('visceralFat')
                metabolic_age = payload.get('metabolicAge')
                protein = payload.get('protein')
                weight_unit = payload.get('unit', 'kg')

                # Save to CSV
                if msg.topic == "openScaleSync/measurements/insert":
                    body_composition_data.write_measurement(
                        timestamp=timestamp,
                        weight=weight,
                        weight_unit=weight_unit,
                        body_fat=body_fat,
                        muscle_mass=muscle_mass,
                        bmi=bmi,
                        water=water,
                        bone_mass=bone_mass,
                        visceral_fat=visceral_fat,
                        metabolic_age=metabolic_age,
                        protein=protein
                    )
                    logger.info(f"Saved body composition measurement: {weight} {weight_unit}")

                    # Call callback if provided
                    if self.on_measurement_callback:
                        self.on_measurement_callback(payload)

                elif msg.topic == "openScaleSync/measurements/update":
                    # For updates, we'd need to identify which measurement to update
                    # For now, treat it as insert
                    logger.info("Received update message, treating as insert")
                    body_composition_data.write_measurement(
                        timestamp=timestamp,
                        weight=weight,
                        weight_unit=weight_unit,
                        body_fat=body_fat,
                        muscle_mass=muscle_mass,
                        bmi=bmi,
                        water=water,
                        bone_mass=bone_mass,
                        visceral_fat=visceral_fat,
                        metabolic_age=metabolic_age,
                        protein=protein
                    )

                    if self.on_measurement_callback:
                        self.on_measurement_callback(payload)

            else:
                logger.warning(f"Missing required fields in payload: {payload}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON payload: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def start(self):
        """Start the MQTT client and connect to broker."""
        try:
            logger.info(f"Connecting to MQTT broker at {self.broker_host}:{self.broker_port}...")
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start()  # Start background thread
            logger.info("MQTT service started")
        except Exception as e:
            logger.error(f"Failed to start MQTT service: {e}")

    def stop(self):
        """Stop the MQTT client."""
        logger.info("Stopping MQTT service...")
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("MQTT service stopped")

    def get_status(self):
        """Get the current connection status."""
        return {
            'connected': self.is_connected,
            'broker': f"{self.broker_host}:{self.broker_port}"
        }
