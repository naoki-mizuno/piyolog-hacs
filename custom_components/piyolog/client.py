import requests
import hashlib
import uuid
import time
import dateparser
from datetime import datetime, timezone

from zoneinfo import ZoneInfo

# PiyoLog API assumes JST (UTC+9) for event datetimes. Client uses this when
# defaulting to "now" and when formatting datetimes for the API.
_JST = ZoneInfo("Asia/Tokyo")


# Event Type Constants
class EventType:
    """Baby event type constants."""

    # Basic Events
    OTHER = 0
    MOTHERS_MILK = 1  # Breastfeeding
    MILK = 2  # Formula/Bottle
    MILKING = 3  # Expressed (pumped) breast milk
    SLEEP_BEGIN = 4
    SLEEP_END = 5
    PEE = 6
    POO = 7
    BODY_TEMPERATURE = 8
    MEAL = 9  # Baby food
    BODY_HEIGHT = 10
    BODY_WEIGHT = 11
    COUGH = 12
    VOMITING = 13
    RASH = 14
    INJURY = 15
    BATH = 16
    SNACK = 17
    MEAL2 = 18  # Regular meal
    DRINK = 19
    MEDICINE = 20
    HOSPITAL = 21
    WALKING = 22
    PUMPING = 23

    # Custom Events (24-28, 30-34)
    CUSTOM1 = 24
    CUSTOM2 = 25
    CUSTOM3 = 26
    CUSTOM4 = 27
    CUSTOM5 = 28
    VACCINE = 29
    CUSTOM6 = 30
    CUSTOM7 = 31
    CUSTOM8 = 32
    CUSTOM9 = 33
    CUSTOM10 = 34

    # Special Events
    MILESTONE = 35
    HEAD = 36  # Head circumference
    CHEST = 37  # Chest circumference
    MEMO = 38  # General note


# Poop Event Property Enums
class PoopAmount:
    """Poop amount/volume constants (stored in 'amount' field)."""

    DEFAULT = 0  # 記録しない / Not recorded
    SMALL = 1  # 少なめ / Small
    LARGE = 2  # 多め / Large
    NORMAL = 3  # ふつう / Medium
    MINIMUM = 4  # ちょこっと / Bit


class PoopHardness:
    """Poop hardness/consistency constants (stored in 'value' field)."""

    DEFAULT = 0  # 記録しない / Not recorded
    DIARRHEA = 1  # 下痢 / Diarrhea
    SOFT = 2  # やわらかめ / Soft
    HARD = 3  # かため / Hard
    NORMAL = 4  # ふつう / Medium


class PoopColor:
    """Poop color constants (stored in 'left_time' field)."""

    DEFAULT = 0  # 記録しない / Not recorded
    WHITE = 1  # 白 / White
    YELLOW = 2  # 黄 / Yellow
    ORANGE = 3  # 橙 / Orange
    BROWN = 4  # 茶 / Brown
    GREEN = 5  # 緑 / Green
    RED = 6  # 赤 / Red
    BLACK = 7  # 黒 / Black


# Breastfeeding Order Enum
class BreastfeedingOrder:
    """Breastfeeding order constants (stored in 'value' field)."""

    UNSPECIFIED = 0  # 順序なし / No order
    LEFT_TO_RIGHT = 1  # 左から / L to R
    RIGHT_TO_LEFT = 2  # 右から / R to L


# String name to PoopAmount mapping
POOP_AMOUNT_MAP = {
    "default": PoopAmount.DEFAULT,
    "none": PoopAmount.DEFAULT,
    "0": PoopAmount.DEFAULT,
    "small": PoopAmount.SMALL,
    "少なめ": PoopAmount.SMALL,
    "1": PoopAmount.SMALL,
    "large": PoopAmount.LARGE,
    "多め": PoopAmount.LARGE,
    "2": PoopAmount.LARGE,
    "normal": PoopAmount.NORMAL,
    "medium": PoopAmount.NORMAL,
    "普通": PoopAmount.NORMAL,
    "ふつう": PoopAmount.NORMAL,
    "3": PoopAmount.NORMAL,
    "minimum": PoopAmount.MINIMUM,
    "bit": PoopAmount.MINIMUM,
    "ちょこっと": PoopAmount.MINIMUM,
    "4": PoopAmount.MINIMUM,
}


# String name to PoopHardness mapping
POOP_HARDNESS_MAP = {
    "default": PoopHardness.DEFAULT,
    "none": PoopHardness.DEFAULT,
    "0": PoopHardness.DEFAULT,
    "diarrhea": PoopHardness.DIARRHEA,
    "下痢": PoopHardness.DIARRHEA,
    "1": PoopHardness.DIARRHEA,
    "soft": PoopHardness.SOFT,
    "やわらかめ": PoopHardness.SOFT,
    "2": PoopHardness.SOFT,
    "hard": PoopHardness.HARD,
    "かため": PoopHardness.HARD,
    "3": PoopHardness.HARD,
    "normal": PoopHardness.NORMAL,
    "medium": PoopHardness.NORMAL,
    "普通": PoopHardness.NORMAL,
    "ふつう": PoopHardness.NORMAL,
    "4": PoopHardness.NORMAL,
}


# String name to PoopColor mapping
POOP_COLOR_MAP = {
    "default": PoopColor.DEFAULT,
    "0": PoopColor.DEFAULT,
    "white": PoopColor.WHITE,
    "白": PoopColor.WHITE,
    "1": PoopColor.WHITE,
    "yellow": PoopColor.YELLOW,
    "黄": PoopColor.YELLOW,
    "黄色": PoopColor.YELLOW,
    "2": PoopColor.YELLOW,
    "orange": PoopColor.ORANGE,
    "橙": PoopColor.ORANGE,
    "オレンジ": PoopColor.ORANGE,
    "3": PoopColor.ORANGE,
    "brown": PoopColor.BROWN,
    "茶": PoopColor.BROWN,
    "茶色": PoopColor.BROWN,
    "4": PoopColor.BROWN,
    "green": PoopColor.GREEN,
    "緑": PoopColor.GREEN,
    "5": PoopColor.GREEN,
    "red": PoopColor.RED,
    "赤": PoopColor.RED,
    "6": PoopColor.RED,
    "black": PoopColor.BLACK,
    "黒": PoopColor.BLACK,
    "7": PoopColor.BLACK,
}


# String name to BreastfeedingOrder mapping
BREASTFEEDING_ORDER_MAP = {
    "default": BreastfeedingOrder.UNSPECIFIED,
    "unspecified": BreastfeedingOrder.UNSPECIFIED,
    "none": BreastfeedingOrder.UNSPECIFIED,
    "no_order": BreastfeedingOrder.UNSPECIFIED,
    "順序なし": BreastfeedingOrder.UNSPECIFIED,
    "0": BreastfeedingOrder.UNSPECIFIED,
    "left_first": BreastfeedingOrder.LEFT_TO_RIGHT,
    "left_to_right": BreastfeedingOrder.LEFT_TO_RIGHT,
    "left_right": BreastfeedingOrder.LEFT_TO_RIGHT,
    "l_to_r": BreastfeedingOrder.LEFT_TO_RIGHT,
    "l_r": BreastfeedingOrder.LEFT_TO_RIGHT,
    "左→右": BreastfeedingOrder.LEFT_TO_RIGHT,
    "左から": BreastfeedingOrder.LEFT_TO_RIGHT,
    "左右": BreastfeedingOrder.LEFT_TO_RIGHT,
    "1": BreastfeedingOrder.LEFT_TO_RIGHT,
    "right_first": BreastfeedingOrder.RIGHT_TO_LEFT,
    "right_to_left": BreastfeedingOrder.RIGHT_TO_LEFT,
    "right_left": BreastfeedingOrder.RIGHT_TO_LEFT,
    "r_to_l": BreastfeedingOrder.RIGHT_TO_LEFT,
    "r_l": BreastfeedingOrder.RIGHT_TO_LEFT,
    "右→左": BreastfeedingOrder.RIGHT_TO_LEFT,
    "右から": BreastfeedingOrder.RIGHT_TO_LEFT,
    "右左": BreastfeedingOrder.RIGHT_TO_LEFT,
    "2": BreastfeedingOrder.RIGHT_TO_LEFT,
}


# String name to EventType mapping (for convenience)
EVENT_TYPE_MAP = {
    "other": EventType.OTHER,
    "その他": EventType.OTHER,
    # 母乳
    "breastfeeding": EventType.MOTHERS_MILK,
    "breast": EventType.MOTHERS_MILK,
    "breast_milk": EventType.MOTHERS_MILK,
    "mothers_milk": EventType.MOTHERS_MILK,
    "母乳": EventType.MOTHERS_MILK,
    # ミルク
    "milk": EventType.MILK,
    "formula": EventType.MILK,
    "ミルク": EventType.MILK,
    # 搾母乳
    "pumped_breast_milk": EventType.MILKING,
    "expressed_breast_milk": EventType.MILKING,
    "搾母乳": EventType.MILKING,
    # 搾乳
    "pumping": EventType.PUMPING,
    "搾乳": EventType.PUMPING,
    # 寝る
    "sleep_start": EventType.SLEEP_BEGIN,
    "sleep_begin": EventType.SLEEP_BEGIN,
    "sleep": EventType.SLEEP_BEGIN,
    "寝る": EventType.SLEEP_BEGIN,
    # 起きる
    "sleep_end": EventType.SLEEP_END,
    "wake_up": EventType.SLEEP_END,
    "起きる": EventType.SLEEP_END,
    # おしっこ
    "pee": EventType.PEE,
    "piss": EventType.PEE,
    "おしっこ": EventType.PEE,
    # うんち
    "poop": EventType.POO,
    "poo": EventType.POO,
    "shit": EventType.POO,
    "うんち": EventType.POO,
    "うんこ": EventType.POO,
    # 体温
    "temperature": EventType.BODY_TEMPERATURE,
    "body_temperature": EventType.BODY_TEMPERATURE,
    "体温": EventType.BODY_TEMPERATURE,
    # 離乳食
    "meal": EventType.MEAL,
    "baby_food": EventType.MEAL,
    "baby_meal": EventType.MEAL,
    "離乳食": EventType.MEAL,
    # 身長
    "height": EventType.BODY_HEIGHT,
    "身長": EventType.BODY_HEIGHT,
    # 体重
    "weight": EventType.BODY_WEIGHT,
    "体重": EventType.BODY_WEIGHT,
    # 咳
    "cough": EventType.COUGH,
    "咳": EventType.COUGH,
    "せき": EventType.COUGH,
    # 嘔吐
    "vomit": EventType.VOMITING,
    "vomiting": EventType.VOMITING,
    "吐く": EventType.VOMITING,
    "嘔吐": EventType.VOMITING,
    # 発疹
    "rash": EventType.RASH,
    "発疹": EventType.RASH,
    # けが
    "injury": EventType.INJURY,
    "けが": EventType.INJURY,
    # お風呂
    "bath": EventType.BATH,
    "お風呂": EventType.BATH,
    # おやつ
    "snack": EventType.SNACK,
    "おやつ": EventType.SNACK,
    # 飲み物
    "drink": EventType.DRINK,
    "飲み物": EventType.DRINK,
    "のみもの": EventType.DRINK,
    # 薬
    "medicine": EventType.MEDICINE,
    "薬": EventType.MEDICINE,
    "くすり": EventType.MEDICINE,
    # 病院
    "hospital": EventType.HOSPITAL,
    "病院": EventType.HOSPITAL,
    # さんぽ
    "walking": EventType.WALKING,
    "walk": EventType.WALKING,
    "さんぽ": EventType.WALKING,
    "お散歩": EventType.WALKING,
    "散歩": EventType.WALKING,
    # ワクチン
    "vaccine": EventType.VACCINE,
    "ワクチン": EventType.VACCINE,
    "予防接種": EventType.VACCINE,
    # 成長記録
    "milestone": EventType.MILESTONE,
    "成長記録": EventType.MILESTONE,
    "できた": EventType.MILESTONE,
    # メモ
    "note": EventType.MEMO,
    "memo": EventType.MEMO,
    "メモ": EventType.MEMO,
    # 食事
    "normal_food": EventType.MEAL2,
    "normal_meal": EventType.MEAL2,
    "regular_meal": EventType.MEAL2,
    "食事": EventType.MEAL2,
    "ごはん": EventType.MEAL2,
    # 頭囲
    "head": EventType.HEAD,
    "head_circumference": EventType.HEAD,
    "頭囲": EventType.HEAD,
    # 胸囲
    "chest": EventType.CHEST,
    "chest_circumference": EventType.CHEST,
    "胸囲": EventType.CHEST,
    # カスタムイベント
    "custom_1": EventType.CUSTOM1,
    "custom1": EventType.CUSTOM1,
    "カスタム1": EventType.CUSTOM1,
    "custom_2": EventType.CUSTOM2,
    "custom2": EventType.CUSTOM2,
    "カスタム2": EventType.CUSTOM2,
    "custom_3": EventType.CUSTOM3,
    "custom3": EventType.CUSTOM3,
    "カスタム3": EventType.CUSTOM3,
    "custom_4": EventType.CUSTOM4,
    "custom4": EventType.CUSTOM4,
    "カスタム4": EventType.CUSTOM4,
    "custom_5": EventType.CUSTOM5,
    "custom5": EventType.CUSTOM5,
    "カスタム5": EventType.CUSTOM5,
    "custom_6": EventType.CUSTOM6,
    "custom6": EventType.CUSTOM6,
    "カスタム6": EventType.CUSTOM6,
    "custom_7": EventType.CUSTOM7,
    "custom7": EventType.CUSTOM7,
    "カスタム7": EventType.CUSTOM7,
    "custom_8": EventType.CUSTOM8,
    "custom8": EventType.CUSTOM8,
    "カスタム8": EventType.CUSTOM8,
    "custom_9": EventType.CUSTOM9,
    "custom9": EventType.CUSTOM9,
    "カスタム9": EventType.CUSTOM9,
    "custom_10": EventType.CUSTOM10,
    "custom10": EventType.CUSTOM10,
    "カスタム10": EventType.CUSTOM10,
}


class EventBuilder:
    """Builder class for creating baby events with fluent API."""

    def __init__(self, client, event_type, baby_id=None, baby_index=None):
        """
        Initialize event builder.

        Args:
            client: PiyoLogClient instance
            event_type: EventType constant or int
            baby_id: Baby ID (optional, will be resolved)
            baby_index: Baby index (optional, will be resolved)
        """
        self.client = client
        self.event_type = event_type
        self._baby_id = baby_id
        self._baby_index = baby_index
        self._datetime = None
        self._amount = None
        self._value = None
        self._memo = ""
        self._left_time = 0
        self._right_time = 0

    def set_datetime(self, dt):
        """Set event datetime."""
        self._datetime = dt
        return self

    def set_amount(self, amount):
        """Set amount (for milk, pumping, etc.)."""
        self._amount = amount
        return self

    def set_value(self, value):
        """Set value (for temperature, weight, height, etc.)."""
        self._value = value
        return self

    def set_memo(self, memo):
        """Set memo/note."""
        self._memo = memo
        return self

    def set_baby_id(self, baby_id):
        """Set baby ID."""
        self._baby_id = baby_id
        return self

    def set_baby_index(self, baby_index):
        """Set baby index."""
        self._baby_index = baby_index
        return self

    def set_left_time(self, minutes):
        """Set left breast feeding time in minutes."""
        self._left_time = minutes * 60  # Convert to seconds
        return self

    def set_right_time(self, minutes):
        """Set right breast feeding time in minutes."""
        self._right_time = minutes * 60  # Convert to seconds
        return self

    def set_breastfeeding_order(self, order):
        """Set breastfeeding order (BreastfeedingOrder constant)."""
        self._value = order
        return self

    def set_poop_amount(self, amount):
        """Set poop amount (PoopAmount constant)."""
        self._amount = amount
        return self

    def set_poop_hardness(self, hardness):
        """Set poop hardness (PoopHardness constant)."""
        self._value = hardness
        return self

    def set_poop_color(self, color):
        """Set poop color (PoopColor constant)."""
        self._left_time = color
        return self

    def save(self):
        """
        Validate and save the event.

        Returns:
            dict: Server response
        """
        # Resolve baby_id
        baby_id = self.client._resolve_baby_id(self._baby_id, self._baby_index)

        # Normalize datetime
        dt_fields = self.client._normalize_datetime(self._datetime)

        # Build event data
        event_data = {
            "user_id": self.client.user_id,
            "baby_id": baby_id,
            "event_id": self.client._generate_event_id(),
            "type": self.event_type,
            "memo": self._memo,
            "left_time": self._left_time,
            "right_time": self._right_time,
            "amount": self._amount if self._amount is not None else 0,
            "value": self._value if self._value is not None else 0,
            "image_url": "",
            "deleted": False,
            "main_version": 0,
            "minor_version": 0,
            "meta": None,
        }

        # Add datetime fields
        event_data.update(dt_fields)

        # Register event
        return self.client.register_baby_event(event_data)


class PiyoLogClient:
    # --- Configuration ---
    BASE_URL = "https://api2.piyolog.com/"
    API_VERSION = 2.0  # API version for all endpoints
    # Standard Android User-Agent format to blend in
    DEFAULT_USER_AGENT = "PiyoLog/9.1.0 (Android 14; Pixel 8 Build/UD1A.230803.041)"

    def __init__(
        self, user_agent=None, user_id=None, client_id=None, client_token=None
    ):
        self.user_id = user_id
        self.client_id = client_id
        self.client_token = client_token
        self.uuid = str(uuid.uuid4())  # Persistent UUID for this "device"
        self.USER_AGENT = user_agent if user_agent else self.DEFAULT_USER_AGENT

        # Baby caching for convenience methods
        self._babies = None  # Cached list of babies
        self._default_baby_id = None  # Default baby for convenience methods

        # Version tracking for sync
        self._main_version = 1  # Start with 1 for existing accounts
        self._minor_version = 1  # Start with 1 for existing accounts

    def create_new_user(self, device_name):
        """Registers a new 'device' to get initial credentials."""
        self.user_id = self.uuid

        # Hash formula from reverse engineering: MD5(user_id + "NewPiyoLogApp")
        h = self.__calculate_hash__(f"{self.user_id}NewPiyoLogApp")

        payload = {
            "api_version": self.API_VERSION,
            "user_id": self.user_id,
            "name": device_name,
            "hash": h,
        }

        resp = requests.post(
            f"{self.BASE_URL}create_user",
            json=payload,
            headers={"User-Agent": self.USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == 200:
            self.client_id = data["client_id"]
            self.client_token = data["client_token"]
            return {
                "user_id": self.user_id,
                "client_id": self.client_id,
                "client_token": self.client_token,
            }
        else:
            raise Exception(f"Registration failed: {data}")

    def link_account(self, other_user_id, share_code, device_name):
        """
        Links this client to an existing account using a Share Code.
        The Share Code can be generated in the PiyoLog app: Settings -> Share -> Issue Code.
        """
        if not self.client_id:
            raise Exception("Must call create_new_user() first to establish a session.")

        payload = {
            "api_version": self.API_VERSION,
            "user_id": other_user_id,
            "code": share_code,
            "name": device_name,
            "type": 1,  # 1 = Share (0 = Takeover)
        }

        resp = requests.post(
            f"{self.BASE_URL}share_code_confirm",
            json=payload,
            headers={"User-Agent": self.USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == 200:
            # The server returns the Linked Account's credentials.
            # We must switch to these to access the shared data.
            self.user_id = data["user_id"]
            self.client_id = data["client_id"]
            self.client_token = data["client_token"]

            return {
                "user_id": self.user_id,
                "client_id": self.client_id,
                "client_token": self.client_token,
                "role": data.get("role"),
            }
        else:
            raise Exception(f"Account linking failed: {data}")

    def sync(self, main_version=0, minor_version=0, data=None):
        """
        Syncs data with the server.

        Args:
            main_version: Main version number (0 to get all data)
            minor_version: Minor version number (0 to get all data)
            data: Optional dict containing data to upload (e.g., {"baby_event": [...]})

        Returns:
            dict: Server response containing synced data
        """
        if not self.user_id or not self.client_token:
            raise Exception("Not authenticated.")

        payload = {
            "api_version": self.API_VERSION,
            "user_id": self.user_id,
            "client_id": self.client_id,
            "client_token": self.client_token,
            "main_version": main_version,
            "minor_version": minor_version,
            "app": "PiyoLog for android",
        }

        if data:
            payload["data"] = data

        resp = requests.post(
            f"{self.BASE_URL}sync",
            json=payload,
            headers={"User-Agent": self.USER_AGENT},
        )
        resp.raise_for_status()
        response = resp.json()

        # Update version tracking from server response
        if response.get("status") == 200:
            if "main_version" in response:
                self._main_version = response["main_version"]
            if "minor_version" in response:
                self._minor_version = response["minor_version"]

        return response

    def register_baby_event(self, event_data):
        """
        Registers a baby event by syncing it to the server.

        Args:
            event_data: dict containing baby event data with fields like:
                - event_id: unique event identifier
                - baby_id: baby identifier
                - event_type: type of event (e.g., milk, diaper, sleep)
                - start_at: timestamp in milliseconds
                - minor_version: should be 0 for new events
                - ... other event fields

        Returns:
            dict: Server response from sync
        """
        if not self.user_id or not self.client_token:
            raise Exception("Not authenticated.")

        # Ensure minor_version is 0 for new events
        if "minor_version" not in event_data:
            event_data["minor_version"] = 0

        # Wrap in sync data structure
        sync_data = {"baby_event": [event_data]}

        return self.sync(
            main_version=self._main_version,
            minor_version=self._minor_version,
            data=sync_data,
        )

    def delete_baby_event(self, event):
        """
        Soft-delete an existing baby event by re-uploading it with deleted=true.

        PiyoLog has no dedicated delete endpoint: deletion is performed by
        re-syncing the event with deleted=true, a fresh modified_at, and
        minor_version=0 so the server treats it as a new revision.

        Args:
            event: Existing baby event dict (must contain at least event_id,
                user_id, baby_id, and the original event fields).

        Returns:
            dict: Server response from sync.
        """
        payload = dict(event)
        payload["deleted"] = True
        payload["modified_at"] = int(time.time() * 1000)
        payload["minor_version"] = 0
        return self.register_baby_event(payload)

    def new_baby_event(
        self, event_type, datetime=None, baby_id=None, baby_index=None, memo=""
    ):
        """
        Create a new baby event using the builder pattern.

        Args:
            event_type: EventType constant, int, or string name (case-insensitive)
            datetime: Event datetime (None for current time)
            baby_id: Baby ID (optional)
            baby_index: Baby index (optional)
            memo: Event memo/note

        Returns:
            EventBuilder: Builder instance for fluent API

        Raises:
            ValueError: If event_type string is invalid
        """
        # Convert string event type to constant
        if isinstance(event_type, str):
            event_type_lower = event_type.lower()
            if event_type_lower not in EVENT_TYPE_MAP:
                # Suggest close matches
                suggestions = [
                    k for k in EVENT_TYPE_MAP.keys() if event_type_lower[:3] in k
                ]
                if suggestions:
                    raise ValueError(
                        f"Invalid event type string: '{event_type}'. "
                        f"Did you mean: {', '.join(suggestions[:5])}?"
                    )
                else:
                    raise ValueError(
                        f"Invalid event type string: '{event_type}'. "
                        f"Use EventType constant or valid string."
                    )
            event_type = EVENT_TYPE_MAP[event_type_lower]

        # Create and configure builder
        builder = EventBuilder(self, event_type, baby_id, baby_index)
        builder.set_datetime(datetime)
        builder.set_memo(memo)

        return builder

    # --- Convenience Methods for Baby Events ---

    def add_milk(self, amount, datetime=None, baby_id=None, baby_index=None, memo=""):
        """
        Add milk/formula feeding event.

        Args:
            amount: Amount in ml
            datetime: Event datetime (None for current time)
            baby_id: Baby ID (optional)
            baby_index: Baby index (optional)
            memo: Event memo

        Returns:
            dict: Server response
        """
        return (
            self.new_baby_event(EventType.MILK, datetime, baby_id, baby_index, memo)
            .set_amount(amount)
            .save()
        )

    def add_breastfeeding(
        self,
        left_minutes=0,
        right_minutes=0,
        order=None,
        amount=0,
        datetime=None,
        baby_id=None,
        baby_index=None,
        memo="",
    ):
        """
        Add breastfeeding event.

        Args:
            left_minutes: Left breast feeding duration in minutes
            right_minutes: Right breast feeding duration in minutes
            order: Breastfeeding order (BreastfeedingOrder constant: UNSPECIFIED=0, LEFT_TO_RIGHT=1, RIGHT_TO_LEFT=2)
            amount: Amount in ml (optional, for tracking expressed breast milk volume)
            datetime: Event datetime (None for current time)
            baby_id: Baby ID (optional)
            baby_index: Baby index (optional)
            memo: Event memo

        Returns:
            dict: Server response
        """
        builder = (
            self.new_baby_event(
                EventType.MOTHERS_MILK, datetime, baby_id, baby_index, memo
            )
            .set_left_time(left_minutes)
            .set_right_time(right_minutes)
        )
        if order is not None:
            builder.set_breastfeeding_order(order)
        if amount > 0:
            builder.set_amount(amount)
        return builder.save()

    def add_expressed_breast_milk(
        self, amount, datetime=None, baby_id=None, baby_index=None, memo=""
    ):
        """
        Add expressed (pumped) breast milk event.

        Args:
            amount: Amount in ml
            datetime: Event datetime (None for current time)
            baby_id: Baby ID (optional)
            baby_index: Baby index (optional)
            memo: Event memo

        Returns:
            dict: Server response
        """
        return (
            self.new_baby_event(EventType.MILKING, datetime, baby_id, baby_index, memo)
            .set_amount(amount)
            .save()
        )

    def add_pee(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """
        Add pee event.

        Args:
            datetime: Event datetime (None for current time)
            baby_id: Baby ID (optional)
            baby_index: Baby index (optional)
            memo: Event memo

        Returns:
            dict: Server response
        """
        return self.new_baby_event(
            EventType.PEE, datetime, baby_id, baby_index, memo
        ).save()

    def add_poop(
        self,
        amount=None,
        hardness=None,
        color=None,
        datetime=None,
        baby_id=None,
        baby_index=None,
        memo="",
    ):
        """
        Add poop event.

        Args:
            amount: Poop amount (PoopAmount constant: SMALL=1, LARGE=2, NORMAL=3, MINIMUM=4, or DEFAULT=0)
            hardness: Poop hardness (PoopHardness constant: DIARRHEA=1, SOFT=2, HARD=3, NORMAL=4, or DEFAULT=0)
            color: Poop color (PoopColor constant: WHITE=1, YELLOW=2, ORANGE=3, BROWN=4, GREEN=5, RED=6, BLACK=7, or DEFAULT=0)
            datetime: Event datetime (None for current time)
            baby_id: Baby ID (optional)
            baby_index: Baby index (optional)
            memo: Event memo

        Returns:
            dict: Server response
        """
        builder = self.new_baby_event(
            EventType.POO, datetime, baby_id, baby_index, memo
        )
        if amount is not None:
            builder.set_poop_amount(amount)
        if hardness is not None:
            builder.set_poop_hardness(hardness)
        if color is not None:
            builder.set_poop_color(color)
        return builder.save()

    def add_shit(self, *args, **kwargs):
        """
        This is an alias for add_poop. I just had to add this method because.
        """
        return self.add_poop(*args, **kwargs)

    def add_sleep_begin(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """
        Add sleep start event.

        Args:
            datetime: Event datetime (None for current time)
            baby_id: Baby ID (optional)
            baby_index: Baby index (optional)
            memo: Event memo

        Returns:
            dict: Server response
        """
        return self.new_baby_event(
            EventType.SLEEP_BEGIN, datetime, baby_id, baby_index, memo
        ).save()

    def add_sleep_end(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """
        Add sleep end event.

        Args:
            datetime: Event datetime (None for current time)
            baby_id: Baby ID (optional)
            baby_index: Baby index (optional)
            memo: Event memo

        Returns:
            dict: Server response
        """
        return self.new_baby_event(
            EventType.SLEEP_END, datetime, baby_id, baby_index, memo
        ).save()

    def add_temperature(
        self, value, datetime=None, baby_id=None, baby_index=None, memo=""
    ):
        """
        Add body temperature event.

        Args:
            value: Temperature in celsius
            datetime: Event datetime (None for current time)
            baby_id: Baby ID (optional)
            baby_index: Baby index (optional)
            memo: Event memo

        Returns:
            dict: Server response
        """
        return (
            self.new_baby_event(
                EventType.BODY_TEMPERATURE, datetime, baby_id, baby_index, memo
            )
            .set_value(value)
            .save()
        )

    def add_snack(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """
        Add snack event.

        Args:
            datetime: Event datetime (None for current time)
            baby_id: Baby ID (optional)
            baby_index: Baby index (optional)
            memo: Event memo

        Returns:
            dict: Server response
        """
        return self.new_baby_event(
            EventType.SNACK, datetime, baby_id, baby_index, memo
        ).save()

    def add_baby_meal(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """
        Add baby food/meal event.

        Args:
            datetime: Event datetime (None for current time)
            baby_id: Baby ID (optional)
            baby_index: Baby index (optional)
            memo: Event memo

        Returns:
            dict: Server response
        """
        return self.new_baby_event(
            EventType.MEAL, datetime, baby_id, baby_index, memo
        ).save()

    def add_bath(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """
        Add bath event.

        Args:
            datetime: Event datetime (None for current time)
            baby_id: Baby ID (optional)
            baby_index: Baby index (optional)
            memo: Event memo

        Returns:
            dict: Server response
        """
        return self.new_baby_event(
            EventType.BATH, datetime, baby_id, baby_index, memo
        ).save()

    def add_pumping(
        self, amount, datetime=None, baby_id=None, baby_index=None, memo=""
    ):
        """
        Add pumping/milking event.

        Args:
            amount: Amount in ml
            datetime: Event datetime (None for current time)
            baby_id: Baby ID (optional)
            baby_index: Baby index (optional)
            memo: Event memo

        Returns:
            dict: Server response
        """
        return (
            self.new_baby_event(EventType.PUMPING, datetime, baby_id, baby_index, memo)
            .set_amount(amount)
            .save()
        )

    def add_weight(self, value, datetime=None, baby_id=None, baby_index=None, memo=""):
        """
        Add body weight event.

        Args:
            value: Weight in kg
            datetime: Event datetime (None for current time)
            baby_id: Baby ID (optional)
            baby_index: Baby index (optional)
            memo: Event memo

        Returns:
            dict: Server response
        """
        return (
            self.new_baby_event(
                EventType.BODY_WEIGHT, datetime, baby_id, baby_index, memo
            )
            .set_value(value)
            .save()
        )

    def add_height(self, value, datetime=None, baby_id=None, baby_index=None, memo=""):
        """
        Add body height event.

        Args:
            value: Height in cm
            datetime: Event datetime (None for current time)
            baby_id: Baby ID (optional)
            baby_index: Baby index (optional)
            memo: Event memo

        Returns:
            dict: Server response
        """
        return (
            self.new_baby_event(
                EventType.BODY_HEIGHT, datetime, baby_id, baby_index, memo
            )
            .set_value(value)
            .save()
        )

    def add_vomit(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """Add vomiting event."""
        return self.new_baby_event(
            EventType.VOMITING, datetime, baby_id, baby_index, memo
        ).save()

    def add_cough(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """Add cough event."""
        return self.new_baby_event(
            EventType.COUGH, datetime, baby_id, baby_index, memo
        ).save()

    def add_rash(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """Add rash event."""
        return self.new_baby_event(
            EventType.RASH, datetime, baby_id, baby_index, memo
        ).save()

    def add_injury(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """Add injury event."""
        return self.new_baby_event(
            EventType.INJURY, datetime, baby_id, baby_index, memo
        ).save()

    def add_medicine(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """Add medicine event."""
        return self.new_baby_event(
            EventType.MEDICINE, datetime, baby_id, baby_index, memo
        ).save()

    def add_hospital(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """Add hospital visit event."""
        return self.new_baby_event(
            EventType.HOSPITAL, datetime, baby_id, baby_index, memo
        ).save()

    def add_walking(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """Add walking event."""
        return self.new_baby_event(
            EventType.WALKING, datetime, baby_id, baby_index, memo
        ).save()

    def add_drink(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """Add drink event."""
        return self.new_baby_event(
            EventType.DRINK, datetime, baby_id, baby_index, memo
        ).save()

    def add_meal(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """Add regular meal event."""
        return self.new_baby_event(
            EventType.MEAL2, datetime, baby_id, baby_index, memo
        ).save()

    def add_vaccine(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """Add vaccine event."""
        return self.new_baby_event(
            EventType.VACCINE, datetime, baby_id, baby_index, memo
        ).save()

    def add_milestone(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """Add milestone event."""
        return self.new_baby_event(
            EventType.MILESTONE, datetime, baby_id, baby_index, memo
        ).save()

    def add_note(self, datetime=None, baby_id=None, baby_index=None, memo=""):
        """Add note/memo event."""
        return self.new_baby_event(
            EventType.MEMO, datetime, baby_id, baby_index, memo
        ).save()

    def add_custom(self, number, datetime=None, baby_id=None, baby_index=None, memo=""):
        """
        Add custom event.

        Args:
            number: Custom event number (1-10)
            datetime: Event datetime (None for current time)
            baby_id: Baby ID (optional)
            baby_index: Baby index (optional)
            memo: Event memo

        Returns:
            dict: Server response

        Raises:
            ValueError: If number is not between 1 and 10
        """
        if not isinstance(number, int) or number < 1 or number > 10:
            raise ValueError(
                f"Custom event number must be between 1 and 10, got: {number}"
            )

        # Map number to EventType constant
        custom_types = {
            1: EventType.CUSTOM1,
            2: EventType.CUSTOM2,
            3: EventType.CUSTOM3,
            4: EventType.CUSTOM4,
            5: EventType.CUSTOM5,
            6: EventType.CUSTOM6,
            7: EventType.CUSTOM7,
            8: EventType.CUSTOM8,
            9: EventType.CUSTOM9,
            10: EventType.CUSTOM10,
        }

        event_type = custom_types[number]
        return self.new_baby_event(
            event_type, datetime, baby_id, baby_index, memo
        ).save()

    # --- Baby Management ---

    def get_babies(self):
        """
        Get list of babies from server (cached).

        Returns:
            list: List of baby dicts with fields like baby_id, nickname, birthday, etc.
        """
        if self._babies is None:
            # Fetch baby list from server
            response = self.sync(main_version=1, minor_version=1)
            if response.get("status") == 200 and "data" in response:
                self._babies = response["data"].get("baby", [])
            else:
                self._babies = []

        return self._babies

    def set_default_baby(self, baby_id=None, baby_index=None):
        """
        Set default baby for convenience methods.

        Args:
            baby_id: Baby ID to use as default
            baby_index: 0-based index of baby to use as default

        Raises:
            ValueError: If both or neither arguments provided, or if invalid baby_id/index
        """
        if (baby_id is None and baby_index is None) or (
            baby_id is not None and baby_index is not None
        ):
            raise ValueError("Must provide exactly one of baby_id or baby_index")

        babies = self.get_babies()

        if baby_index is not None:
            if baby_index < 0 or baby_index >= len(babies):
                raise ValueError(
                    f"Invalid baby_index: {baby_index}. Available babies: 0-{len(babies) - 1}"
                )
            self._default_baby_id = babies[baby_index]["baby_id"]
        else:
            # Validate baby_id exists
            baby_ids = [b["baby_id"] for b in babies]
            if baby_id not in baby_ids:
                raise ValueError(f"Baby ID not found: {baby_id}")
            self._default_baby_id = baby_id

    def _resolve_baby_id(self, baby_id=None, baby_index=None):
        """
        Resolve baby_id using priority: explicit baby_id > baby_index > default > auto-select.

        Args:
            baby_id: Explicit baby ID
            baby_index: 0-based index of baby

        Returns:
            str: Resolved baby_id

        Raises:
            ValueError: If multiple babies exist and none of the selection methods apply
        """
        # Priority 1: Explicit baby_id
        if baby_id is not None:
            return baby_id

        babies = self.get_babies()

        if len(babies) == 0:
            raise ValueError("No babies found. Please create a baby first.")

        # Priority 2: baby_index
        if baby_index is not None:
            if baby_index < 0 or baby_index >= len(babies):
                raise ValueError(
                    f"Invalid baby_index: {baby_index}. Available babies: 0-{len(babies) - 1}"
                )
            return babies[baby_index]["baby_id"]

        # Priority 3: Default baby
        if self._default_baby_id is not None:
            return self._default_baby_id

        # Priority 4: Auto-select if only one baby
        if len(babies) == 1:
            return babies[0]["baby_id"]

        # Multiple babies and no selection method
        baby_list = "\n".join(
            [
                f"  [{i}] {b.get('nickname', 'Unnamed')} (ID: {b['baby_id']})"
                for i, b in enumerate(babies)
            ]
        )
        raise ValueError(
            f"Multiple babies found. Please specify one of:\n"
            f"- baby_id='<id>'\n"
            f"- baby_index=<index> (0-based)\n"
            f"- or call set_default_baby() first\n\n"
            f"Available babies:\n{baby_list}"
        )

    # --- Helper Functions ---

    @staticmethod
    def _normalize_datetime(dt_input):
        """
        Convert various datetime formats to required fields for the API.

        PiyoLog assumes JST (UTC+9). Default "now" and parsed times are
        normalized to JST so date/time/datetime sent to the API are correct.

        Args:
            dt_input: None, datetime object, int (timestamp), or string

        Returns:
            dict: Dict with date, time, datetime, datetime2, created_at, modified_at fields

        Raises:
            ValueError: If datetime cannot be parsed
        """
        if dt_input is None:
            dt = datetime.now(_JST)
        elif isinstance(dt_input, datetime):
            if dt_input.tzinfo is None:
                dt = dt_input.replace(tzinfo=_JST)
            else:
                dt = dt_input.astimezone(_JST)
        elif isinstance(dt_input, int):
            if dt_input > 10000000000:
                sec = dt_input / 1000
            else:
                sec = dt_input
            dt = datetime.fromtimestamp(sec, tz=timezone.utc).astimezone(_JST)
        elif isinstance(dt_input, str):
            dt = dateparser.parse(dt_input, settings={"TIMEZONE": "Asia/Tokyo"})
            if dt is None:
                raise ValueError(f"Could not parse datetime: {dt_input}")
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_JST)
            else:
                dt = dt.astimezone(_JST)
        else:
            raise ValueError(f"Unsupported datetime type: {type(dt_input)}")

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        return {
            "date": int(dt.strftime("%Y%m%d")),
            "time": dt.strftime("%H:%M"),
            "datetime": dt.strftime("%Y%m%d %H:%M"),
            "datetime2": int(dt.timestamp() * 1000),
            "created_at": now_ms,
            "modified_at": now_ms,
        }

    @staticmethod
    def _generate_event_id():
        """Generate unique event ID using MD5 hash."""
        unique_string = f"{time.time()}{uuid.uuid4()}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    @staticmethod
    def __calculate_hash__(s):
        return hashlib.md5(s.encode("utf-8")).hexdigest()
