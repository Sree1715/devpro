import os
import json
import joblib
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "crop_dataset_synthetic.csv")
MODEL_DIR = os.path.join(BASE_DIR, "model")
MODEL_PATH = os.path.join(MODEL_DIR, "model.joblib")
METRICS_PATH = os.path.join(MODEL_DIR, "metrics.json")

MODEL_NOTE = (
    "Note on Model Metrics: The training data is rule-derived synthetic data (crop_dataset_synthetic.csv). "
    "Therefore, reported accuracy and metrics reflect agreement with the generating rules rather than "
    "real-world agronomic validation."
)

_cached_model = None

def train_and_save_model():
    """Trains a Random Forest classifier pipeline on crop_dataset_synthetic.csv and saves artifacts."""
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Dataset not found at {DATA_PATH}")

    os.makedirs(MODEL_DIR, exist_ok=True)
    df = pd.read_csv(DATA_PATH)

    feature_cols = ["nitrogen", "phosphorus", "potassium", "temperature", "moisture", "soil_type"]
    target_col = "crop"

    X = df[feature_cols]
    y = df[target_col]

    # Stratified 80/20 train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Preprocessing: OneHotEncoder for categorical 'soil_type'
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), ["soil_type"]),
            ("num", "passthrough", ["nitrogen", "phosphorus", "potassium", "temperature", "moisture"])
        ]
    )

    pipeline = Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("classifier", RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1))
    ])

    # Fit pipeline
    pipeline.fit(X_train, y_train)

    # Evaluate exclusively on held-out test set
    y_pred = pipeline.predict(X_test)
    classes = list(pipeline.classes_)

    acc = float(accuracy_score(y_test, y_pred))
    prec = float(precision_score(y_test, y_pred, average="macro", zero_division=0))
    rec = float(recall_score(y_test, y_pred, average="macro", zero_division=0))
    f1 = float(f1_score(y_test, y_pred, average="macro", zero_division=0))
    cm = confusion_matrix(y_test, y_pred, labels=classes).tolist()

    metrics = {
        "model_version": "1.0.0-rf",
        "dataset": "crop_dataset_synthetic.csv",
        "train_samples": int(len(X_train)),
        "test_samples": int(len(X_test)),
        "classes": classes,
        "accuracy": round(acc, 4),
        "precision_macro": round(prec, 4),
        "recall_macro": round(rec, 4),
        "f1_macro": round(f1, 4),
        "confusion_matrix": cm,
        "note": MODEL_NOTE
    }

    # Save model and metrics
    joblib.dump(pipeline, MODEL_PATH)
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print(f"Model saved to {MODEL_PATH}")
    print(f"Metrics saved to {METRICS_PATH}")
    print(f"Test Accuracy: {acc:.4f}, Macro F1: {f1:.4f}")
    return metrics

def load_model():
    """Loads and caches the trained ML pipeline."""
    global _cached_model
    if _cached_model is not None:
        return _cached_model
    if not os.path.exists(MODEL_PATH):
        # Auto-train if not yet trained
        train_and_save_model()
    _cached_model = joblib.load(MODEL_PATH)
    return _cached_model

def get_model_metrics():
    """Loads metrics.json."""
    if not os.path.exists(METRICS_PATH):
        train_and_save_model()
    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def predict_top2(features: dict):
    """
    Predict top 2 crops based on input features.
    features: dict with keys nitrogen, phosphorus, potassium, temperature, moisture, soil_type
    Returns list of tuples: [(top1_crop, prob1), (top2_crop, prob2)]
    """
    model = load_model()
    input_df = pd.DataFrame([{
        "nitrogen": float(features["nitrogen"]),
        "phosphorus": float(features["phosphorus"]),
        "potassium": float(features["potassium"]),
        "temperature": float(features["temperature"]),
        "moisture": float(features["moisture"]),
        "soil_type": str(features["soil_type"]).strip()
    }])

    probabilities = model.predict_proba(input_df)[0]
    classes = model.classes_

    # Sort classes by probability descending
    top_indices = np.argsort(probabilities)[::-1][:2]
    top_results = [
        (classes[i], float(probabilities[i]))
        for i in top_indices
    ]
    return top_results

if __name__ == "__main__":
    train_and_save_model()
