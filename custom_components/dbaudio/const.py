"""Constants for the d&b audiotechnik integration."""
from __future__ import annotations

DOMAIN = "dbaudio"

CONF_MODEL = "model"

MODEL_PORT: dict[str, int] = {
    "5D": 50014,
    "10D": 30013,
    "30D": 30013,
    "40D": 50014,
    "D20": 30013,
    "D40": 50014,
    "D80": 30013,
}

MODELS = list(MODEL_PORT.keys())
PLATFORMS = ["switch", "number", "select", "sensor"]

CHANNEL_LABELS = ["A", "B", "C", "D"]
PRESET_COUNT = 15
CHANNEL_COUNT = 4

SPEAKER_NAMES: list[str] = [
    "Q1", "Q7", "Q-SUB", "C7-TOP", "C7-SUB", "Linear", "E0", "E3", "E9",
    "Not available", "C3", "C4-TOP", "C4-SUB", "C6", "E12-SUB", "E18-SUB",
    "Ci45", "Ci60", "Ci80", "Ci90", "M2", "F1222", "E1", "B2-SUB", "B1-SUB",
    "MAX act.", "F1220", "F2", "Q10", "M1220", "J8 Arc", "J8 Line", "J12 Arc",
    "J-SUB", "MAX", "M4", "M4 act.", "Q1 Line", "E8", "E12", "E15-SUB",
    "E12-X", "E3-X", "E12-D", "E12-DX", "J12 Line", "J-INFRA", "T10 PS",
    "T10 Arc", "T10 Line", "T-SUB", "B4-SUB", "E8-X", "M6", "M6 act.", "E6",
    "4S", "5S", "8S", "10S/A", "10S/A-D", "10ADArc", "10ADLin", "12S",
    "12S-D", "18S-SUB", "27S-SUB", "12S-SUB", "10A Arc", "10A Lin", "E4",
    "E5", "V8 Arc", "V8 Line", "V-SUB", "V12 Arc", "V12 Line", "16C", "24C",
    "24C-E", "Y7P", "Y10P", "B6-SUB", "Y8 Arc", "Y8 Line", "Y12 Arc",
    "Y12 Line", "Y-SUB", "MAX2", "V7P", "V10P", "J8 AP", "J12 AP",
    "J-SUB AP", "V8 AP", "V12 AP", "V-SUB AP", "Y8 AP", "Y12 AP",
    "Y-SUB AP", "B22-SUB", "B6-INF", "T10 AP", "T-SUB AP", "24S", "24S-D",
    "21S-SUB", "GSL8 Arc", "GSL8 Line", "GSL8 AP", "GSL12 Arc", "GSL12 Line",
    "GSL12 AP", "SL-SUB", "SL-SUB AP", "KSL8 Arc", "KSL8 Line", "KSL8 AP",
    "KSL12 Arc", "KSL12 Line", "KSL12 AP", "B8-SUB", "AL60 PS", "AL60 Out",
    "AL60 In", "AL60 AP", "AL90 PS", "AL90 Out", "AL90 In", "AL90 AP",
    "KSL-SUB", "KSL-SUB Fln", "KSL-SUB AP", "44S", "XSL8 Arc", "XSL8 Line",
    "XSL8 AP", "XSL12 Arc", "XSL12 Line", "XSL12 AP", "XSL-SUB",
    "XSL-SUB Fln", "XSL-SUB AP",
]
