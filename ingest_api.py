import os
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field
from db import (
    init_db,
    get_connection,
    get_device_by_id,
    get_all_devices,
    get_latest_reading_for_device,
    insert_reading
)
from auth import verify_password

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Smart Manure ESP32 Ingestion API",
    description="FastAPI endpoint for physical ESP32 telemetry ingestion (SIH1767 – GOBARdhan)",
    version="1.0.0"
)

# Initialize DB on startup
@app.on_event("startup")
def startup_event():
    init_db()

class IngestReadingPayload(BaseModel):
    temperature_c: float = Field(..., description="Temperature in Celsius from DS18B20 sensor")
    moisture_percent: Optional[float] = Field(None, description="Moisture percentage from soil sensor (0-100%)")
    moisture_raw_adc: Optional[float] = Field(None, description="Raw ADC value from resistive soil moisture probe (e.g. 0-4095)")

def convert_adc_to_moisture_percent(raw_adc: float) -> float:
    """Convert raw ADC from a resistive soil moisture probe to percentage using ADC_DRY and ADC_WET from .env."""
    try:
        adc_dry = float(os.getenv("ADC_DRY", "3500"))
        adc_wet = float(os.getenv("ADC_WET", "1200"))
    except ValueError:
        adc_dry = 3500.0
        adc_wet = 1200.0

    if adc_dry == adc_wet:
        return 0.0

    if adc_dry > adc_wet:
        moisture = ((adc_dry - raw_adc) / (adc_dry - adc_wet)) * 100.0
    else:
        moisture = ((raw_adc - adc_dry) / (adc_wet - adc_dry)) * 100.0

    return max(0.0, min(100.0, round(moisture, 2)))

def authenticate_device(raw_key: str):
    """Authenticate raw device API key against bcrypt hashed keys in the database."""
    if not raw_key or not raw_key.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Device-Key header."
        )

    clean_key = raw_key.strip()

    # Fast path: Key format with prefix DEV_{id}_{secret}
    if clean_key.startswith("DEV_"):
        parts = clean_key.split("_", 2)
        if len(parts) >= 3 and parts[1].isdigit():
            dev_id = int(parts[1])
            device = get_device_by_id(dev_id)
            if device and verify_password(clean_key, device["api_key_hash"]):
                return device

    # Fallback path: Iterate active registered devices
    devices = get_all_devices()
    for dev in devices:
        if verify_password(clean_key, dev["api_key_hash"]):
            return dev

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or unauthorized X-Device-Key."
    )

@app.get("/api/health")
def health_check():
    """Health check endpoint confirming service and database connectivity."""
    try:
        conn = get_connection()
        conn.execute("SELECT 1")
        conn.close()
        db_status = "connected"
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unreachable: {e}"
        )

    return {
        "status": "healthy",
        "service": "ESP32 Telemetry Ingestion API",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_status
    }

@app.post("/api/readings/ingest", status_code=status.HTTP_201_CREATED)
def ingest_reading(
    payload: IngestReadingPayload,
    x_device_key: Optional[str] = Header(None, alias="X-Device-Key")
):
    """
    Ingest live temperature and moisture telemetry from registered ESP32 devices.
    - Validates X-Device-Key against bcrypt hash
    - Validates physical sensor ranges (Temperature: -10 to 80 °C, Moisture: 0 to 100 %)
    - Rejects duplicate transmissions received within a 5-second window
    """
    if not x_device_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header 'X-Device-Key' is required for device telemetry ingestion."
        )

    # 1. Device Authentication
    device = authenticate_device(x_device_key)
    device_id = device["id"]

    # 2. Sensor Range & Value Resolution
    temp = payload.temperature_c

    if payload.moisture_percent is not None:
        moist = payload.moisture_percent
    elif payload.moisture_raw_adc is not None:
        moist = convert_adc_to_moisture_percent(payload.moisture_raw_adc)
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either 'moisture_percent' or 'moisture_raw_adc' must be provided in the payload."
        )

    if temp < -10.0 or temp > 80.0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Temperature value {temp} °C out of physical range [-10.0, 80.0]."
        )

    if moist < 0.0 or moist > 100.0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Moisture value {moist} % out of physical range [0.0, 100.0]."
        )

    # 3. Duplicate Prevention (Rate Limiting: 5 seconds window)
    latest = get_latest_reading_for_device(device_id)
    if latest:
        last_time_str = latest["received_at"]
        try:
            # Parse SQLite timestamp (formats: '%Y-%m-%d %H:%M:%S' or ISO)
            try:
                last_dt = datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                last_dt = datetime.fromisoformat(last_time_str.replace("Z", ""))
            
            elapsed = (datetime.utcnow() - last_dt).total_seconds()
            if elapsed < 5.0:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Duplicate reading rejected: High frequency transmission ({elapsed:.1f}s elapsed, min 5.0s required)."
                )
        except HTTPException:
            raise
        except Exception:
            # If timestamp parsing fails, proceed safely
            pass

    # 4. Insert reading with server timestamp
    reading_id = insert_reading(
        device_id=device_id,
        temperature_c=temp,
        moisture_percent=moist
    )

    return {
        "status": "success",
        "message": "Telemetry reading successfully ingested",
        "reading_id": reading_id,
        "device_id": device_id,
        "device_name": device["device_name"],
        "temperature_c": temp,
        "moisture_percent": moist,
        "server_timestamp": datetime.now(timezone.utc).isoformat()
    }
