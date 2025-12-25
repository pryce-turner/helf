"""MQTT service for receiving body composition measurements."""

import json
import logging
from typing import Callable, Optional
from datetime import datetime

import paho.mqtt.client as mqtt

from app.repositories.body_comp_repo import BodyCompositionRepository
from app.models.body_composition import BodyCompositionCreate
from app.utils.date_helpers import PACIFIC_TZ

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MQTTService:
    """MQTT client service for body composition data."""

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        on_measurement_callback: Optional[Callable] = None,
    ):
        """
        Initialize MQTT service.

        Args:
            broker_host: MQTT broker hostname
            broker_port: MQTT broker port
            on_measurement_callback: Optional callback when measurement received
        """
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.on_measurement_callback = on_measurement_callback
        self.body_comp_repo = BodyCompositionRepository()

        # Create MQTT client
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        self.is_connected = False

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Callback when connected to MQTT broker."""
        if reason_code == 0:
            logger.info(
                f"Connected to MQTT broker at {self.broker_host}:{self.broker_port}"
            )
            self.is_connected = True

            # Subscribe to openScaleSync topics
            topics = [
                ("openScaleSync/measurements/last", 0),
                ("openScaleSync/measurements/all", 0),
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
            payload = json.loads(msg.payload.decode())
            logger.info(f"Received message on {msg.topic}: {payload}")

            date_str = payload.get("date")
            weight = payload.get("weight")

            if not date_str or not weight:
                logger.warning(f"Missing required fields in payload: {payload}")
                return

            # Parse ISO 8601 timestamp
            try:
                dt = datetime.fromisoformat(date_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=PACIFIC_TZ)
                else:
                    dt = dt.astimezone(PACIFIC_TZ)
            except ValueError:
                dt = datetime.fromisoformat(date_str.replace("T", " ").split("-")[0])
                dt = dt.replace(tzinfo=PACIFIC_TZ)

            # Create measurement
            measurement = BodyCompositionCreate(
                timestamp=dt,
                date=dt.date().isoformat(),
                weight=weight,
                weight_unit="kg",
                body_fat_pct=payload.get("fat"),
                muscle_mass=payload.get("muscle"),
                bmi=payload.get("bmi"),
                water_pct=payload.get("water"),
                bone_mass=payload.get("bone"),
                visceral_fat=payload.get("visceralFat"),
                metabolic_age=payload.get("metabolicAge"),
                protein_pct=payload.get("protein"),
            )

            # Save to database
            saved = self.body_comp_repo.create(measurement)

            topic_type = msg.topic.split("/")[-1]
            if saved:
                logger.info(
                    f"Saved {topic_type} measurement: {weight} kg "
                    f"(fat: {payload.get('fat')}%, muscle: {payload.get('muscle')}%)"
                )
            else:
                logger.info(f"Skipped duplicate {topic_type} measurement: {weight} kg")

            # Call callback if provided
            if self.on_measurement_callback:
                self.on_measurement_callback(payload)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON payload: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)

    def start(self):
        """Start the MQTT client and connect to broker."""
        try:
            logger.info(
                f"Connecting to MQTT broker at {self.broker_host}:{self.broker_port}..."
            )
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start()
            logger.info("MQTT service started")
        except Exception as e:
            logger.error(f"Failed to start MQTT service: {e}")

    def stop(self):
        """Stop the MQTT client."""
        logger.info("Stopping MQTT service...")
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("MQTT service stopped")

    def get_status(self) -> dict:
        """Get the current connection status."""
        return {
            "connected": self.is_connected,
            "broker": f"{self.broker_host}:{self.broker_port}",
        }
