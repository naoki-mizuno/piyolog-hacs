"""Constants for the PiyoLog integration."""

# Import classes from client.py to avoid duplication
from .client import (
    EventType,
    PoopAmount,
    PoopHardness,
    PoopColor,
    BreastfeedingOrder,
    POOP_AMOUNT_MAP,
    POOP_HARDNESS_MAP,
    POOP_COLOR_MAP,
    BREASTFEEDING_ORDER_MAP,
)

DOMAIN = "piyolog"

# Configuration keys
CONF_USER_ID = "user_id"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_TOKEN = "client_token"
CONF_DEFAULT_BABY_ID = "default_baby_id"
CONF_SYNC_INTERVAL = "sync_interval"

# Default values
DEFAULT_SYNC_INTERVAL = 30  # seconds
MIN_SYNC_INTERVAL = 30
MAX_SYNC_INTERVAL = 300

DEFAULT_MILK_AMOUNT = 100  # ml

# API constants
API_BASE_URL = "https://api2.piyolog.com"
API_VERSION = 2.0
API_SECRET = "NewPiyoLogApp"

# PiyoLog assumes Japan Standard Time (JST, UTC+9) for event datetimes.
# Used when parsing API "YYYYMMDD HH:mm" and when sending default "now" to the API.
PIYOLOG_TIMEZONE = "Asia/Tokyo"


# Service names
SERVICE_ADD_PEE = "add_pee"
SERVICE_ADD_POO = "add_poo"
SERVICE_ADD_SLEEP = "add_sleep"
SERVICE_ADD_WAKE_UP = "add_wake_up"
SERVICE_ADD_PEE_AND_POO = "add_pee_and_poo"
SERVICE_ADD_MILK = "add_milk"
SERVICE_ADD_BREASTFEEDING = "add_breastfeeding"
SERVICE_ADD_BATH = "add_bath"
SERVICE_ADD_WALK = "add_walk"
SERVICE_FORCE_SYNC = "force_sync"

# Event type to name mapping (for firing HA events in Phase 3)
EVENT_TYPE_NAMES = {
    EventType.OTHER: "other",
    EventType.MOTHERS_MILK: "breastfeeding",
    EventType.MILK: "milk",
    EventType.MILKING: "expressed_milk",
    EventType.SLEEP_BEGIN: "sleep",
    EventType.SLEEP_END: "wake_up",
    EventType.PEE: "pee",
    EventType.POO: "poo",
    EventType.BODY_TEMPERATURE: "body_temperature",
    EventType.MEAL: "baby_food",
    EventType.BODY_HEIGHT: "height",
    EventType.BODY_WEIGHT: "weight",
    EventType.COUGH: "cough",
    EventType.VOMITING: "vomit",
    EventType.RASH: "rash",
    EventType.INJURY: "injury",
    EventType.BATH: "bath",
    EventType.SNACK: "snack",
    EventType.MEAL2: "meal",
    EventType.DRINK: "drink",
    EventType.MEDICINE: "medicine",
    EventType.HOSPITAL: "hospital",
    EventType.WALKING: "walk",
    EventType.PUMPING: "pumping",
    EventType.CUSTOM1: "custom1",
    EventType.CUSTOM2: "custom2",
    EventType.CUSTOM3: "custom3",
    EventType.CUSTOM4: "custom4",
    EventType.CUSTOM5: "custom5",
    EventType.VACCINE: "vaccine",
    EventType.CUSTOM6: "custom6",
    EventType.CUSTOM7: "custom7",
    EventType.CUSTOM8: "custom8",
    EventType.CUSTOM9: "custom9",
    EventType.CUSTOM10: "custom10",
    EventType.MILESTONE: "milestone",
    EventType.HEAD: "head_circumference",
    EventType.CHEST: "chest_circumference",
    EventType.MEMO: "memo",
}

# Attribute names for service calls
ATTR_BABY_ID = "baby_id"
ATTR_BABY_INDEX = "baby_index"
ATTR_DATETIME = "datetime"
ATTR_MEMO = "memo"
ATTR_AMOUNT = "amount"
ATTR_POO_AMOUNT = "poo_amount"
ATTR_POO_HARDNESS = "poo_hardness"
ATTR_POO_COLOR = "poo_color"
ATTR_BREASTFEEDING_LEFT_MINUTES = "breastfeeding_left_minutes"
ATTR_BREASTFEEDING_RIGHT_MINUTES = "breastfeeding_right_minutes"
ATTR_BREASTFEEDING_ORDER = "breastfeeding_order"
