# Smart Organic Manure Analysis and Crop Suitability Prediction System (SIH1767 – GOBARdhan)

A full-stack agricultural decision support system connecting IoT telemetry (ESP32), laboratory nutrient profiling (NPK), authority governance, and Machine Learning crop suitability prediction.

---

## 🏗️ Architecture & Features

1. **IoT Telemetry Ingestion (FastAPI & ESP32)**:
   - Dedicated FastAPI service (`ingest_api.py`) receiving live compost telemetry (`temperature_c`, `moisture_percent`).
   - Secure per-device authentication using bcrypt-hashed API keys (`X-Device-Key`).
   - Physical range validation (Temperature: -10 °C to 80 °C, Moisture: 0 % to 100 %).
   - Duplicate rejection and high-frequency flood protection (minimum 5s interval).
   - Real hardware firmware in `firmware/esp32_firmware.ino` using DS18B20 (GPIO 4) and analog soil sensor (GPIO 34).

2. **Machine Learning Pipeline (Scikit-Learn & Random Forest)**:
   - Trained on `data/crop_dataset_synthetic.csv`.
   - Feature Preprocessor: `OneHotEncoder` for soil classification (`Alluvial`, `Red`, `Black`, `Forest`) + numerical pass-through.
   - Classifier: `RandomForestClassifier` with stratified 80/20 train/test split.
   - Evaluated strictly on held-out test data and saved to `model/model.joblib` and `model/metrics.json`.
   - Inference returns Top-2 crops with uncalibrated model confidence.
   - *Transparency Note:* Training data is rule-derived synthetic data; metrics measure adherence to heuristic agronomic rules.

3. **Farmer Portal (Streamlit)**:
   - **Device Registration:** Generates single-view API keys for physical ESP32 nodes.
   - **Add Manure Details:** Live display of real sensor telemetry (with age and refresh), farmer confirmation, and validated NPK manual inputs (0-200 kg/ha). Creates unique sequential tracking code (`SMP-0001`).
   - **Farmer Dashboard:** KPI metric cards, interactive Plotly NPK analysis, manure vs soil benchmark comparisons, and sensor telemetry trends over time.
   - **Most Suitable Crop:** Status tracking (Pending, Approved, Rejected with note, Delivered). Shows Top-2 recommendations and PDF report download **only** once delivered in-app.

4. **Authority Review Portal (Streamlit)**:
   - **Manure Submissions Review:** Comprehensive table with filters; one-click Approve or Reject with audit notes. Double-approval prevention.
   - **Crop Prediction & Advisory:** Runs ML inference on approved samples, visualizes confidence, compiles PDF advisory report, and delivers advisory in-app with instant farmer notification.
   - **Aggregate Manure Analysis:** Per-device historical trends, nutrient distribution across soil types, and global scatter analytics.

5. **PDF Advisory Generation (ReportLab)**:
   - Generates Smart Manure Advisory Reports with sample metadata, sensor telemetry, chemical profile, and Top-2 crop advisories.

---

## 🚀 Setup & Execution Instructions

### 1. Environment & Dependencies
```bash
cd smart_manure
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy the template and configure your secrets:
```bash
cp .env.example .env
```
Ensure `.env` contains:
```env
DB_PATH=smart_manure/app.db
AUTHORITY_EMAIL=officer@gobardhan.gov.in
AUTHORITY_PASSWORD=AdminSecure@2026!
AUTHORITY_NAME=Dr. Rajesh Sharma
```

### 3. Initialize First Authority Account
```bash
python create_authority.py
```

### 4. Train the ML Model
```bash
python ml.py
```
*(This produces `model/model.joblib` and `model/metrics.json`)*.

### 5. Start the ESP32 Telemetry Ingestion API (Port 8000)
```bash
uvicorn ingest_api:app --host 0.0.0.0 --port 8000
```
- Health Check: `http://localhost:8000/api/health`
- Ingest Endpoint: `POST http://localhost:8000/api/readings/ingest`

### 6. Launch the Streamlit Portal (Port 8501)
In a separate terminal:
```bash
streamlit run app.py
```
Access the application at `http://localhost:8501`.

---

## 📡 Physical ESP32 Hardware Deployment Steps
*Status: PENDING PHYSICAL VERIFICATION*

To flash and verify the physical hardware:
1. Open `firmware/esp32_firmware.ino` in Arduino IDE or PlatformIO.
2. Install required Arduino libraries:
   - `DallasTemperature` by Miles Burton
   - `OneWire` by Paul Stoffregen
3. Wiring:
   - **DS18B20**: VCC to 3.3V, GND to GND, DATA to **GPIO 4** with a **4.7kΩ pull-up resistor** between VCC and DATA.
   - **Resistive Soil Moisture Probe**: VCC to 3.3V, GND to GND, AOUT to **GPIO 34**.
4. Configure constants in `firmware/esp32_firmware.ino`:
   - Set `WIFI_SSID` and `WIFI_PASSWORD` to your local Wi-Fi.
   - Set `SERVER_URL` to your computer's local LAN IP: `http://<YOUR_LAN_IP>:8000/api/readings/ingest`.
   - Set `DEVICE_API_KEY` to the key generated when registering your device in the Farmer portal.
5. Flash the ESP32 and open the Serial Monitor at **115200 baud**.
6. Verify output logs:
   - `[WiFi] Connected successfully!`
   - `[HTTP] Posting telemetry: {"temperature_c": ..., "moisture_percent": ...}`
   - `[HTTP] Server Response Status: 201`
7. Check the Farmer Portal under **Add Manure Details** — the latest real temperature, moisture, and timestamp will immediately reflect on screen.
