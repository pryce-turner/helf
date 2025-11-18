"""MQTT service for receiving body composition measurements."""
import json
import logging
import os
from typing import Callable
from datetime import datetime
from zoneinfo import ZoneInfo
import paho.mqtt.client as mqtt
from app import body_composition_data

# Pacific timezone
PACIFIC_TZ = ZoneInfo("America/Los_Angeles")

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
                ("openScaleSync/measurements/last", 0),  # Single measurement from scale
                ("openScaleSync/measurements/all", 0),   # Bulk sync from app
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
            # Format: {"date":"2025-11-17T08:56-0800","fat":23.8,"id":179,"muscle":39.1,"water":50.89,"weight":87.15}
            date_str = payload.get('date')  # ISO 8601 format
            weight = payload.get('weight')

            if date_str and weight:
                # Parse ISO 8601 date string to datetime and convert to Pacific time
                try:
                    # Parse ISO 8601 with timezone offset
                    dt = datetime.fromisoformat(date_str)
                    # Convert to Pacific time if timezone-aware, otherwise assume Pacific
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=PACIFIC_TZ)
                    else:
                        dt = dt.astimezone(PACIFIC_TZ)
                except ValueError:
                    # Fallback: try parsing without timezone and assume Pacific
                    dt = datetime.fromisoformat(date_str.replace('T', ' ').split('-')[0])
                    dt = dt.replace(tzinfo=PACIFIC_TZ)

                # Convert to Unix timestamp in milliseconds for consistency
                timestamp = int(dt.timestamp() * 1000)

                # Extract optional fields from payload
                body_fat = payload.get('fat')         # Body fat percentage
                muscle_mass = payload.get('muscle')   # Muscle mass
                water = payload.get('water')          # Water percentage
                bmi = payload.get('bmi')              # BMI
                bone_mass = payload.get('bone')       # Bone mass
                visceral_fat = payload.get('visceralFat')  # Visceral fat
                metabolic_age = payload.get('metabolicAge')  # Metabolic age
                protein = payload.get('protein')      # Protein percentage
                weight_unit = 'kg'  # openScale uses kg - store as-is

                # Save to CSV as received (append-only, no conversion, deduplicated)
                saved = body_composition_data.write_measurement(
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

                topic_type = msg.topic.split('/')[-1]  # 'last' or 'all'
                if saved:
                    logger.info(f"Saved {topic_type} measurement: {weight} kg (fat: {body_fat}%, muscle: {muscle_mass}%)")
                else:
                    logger.info(f"Skipped duplicate {topic_type} measurement: {weight} kg")

                # Call callback if provided
                if self.on_measurement_callback:
                    self.on_measurement_callback(payload)

            else:
                logger.warning(f"Missing required fields in payload: {payload}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON payload: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)

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
