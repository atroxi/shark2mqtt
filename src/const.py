"""Shark/Ayla/Auth0 constants and enums."""

from dataclasses import dataclass
from enum import IntEnum


@dataclass(frozen=True)
class RegionConfig:
    """Region-specific API configuration."""

    auth0_url: str
    auth0_token_url: str
    auth0_client_id: str
    auth0_redirect_uri: str
    ayla_login_url: str
    ayla_device_url: str
    ayla_app_id: str
    ayla_app_secret: str
    skegox_base: str
    skegox_api_key: str


REGIONS: dict[str, RegionConfig] = {
    "us": RegionConfig(
        auth0_url="https://login.sharkninja.com",
        auth0_token_url="https://login.sharkninja.com/oauth/token",
        auth0_client_id="wsguxrqm77mq4LtrTrwg8ZJUxmSrexGi",
        auth0_redirect_uri="com.sharkninja.shark://login.sharkninja.com/ios/com.sharkninja.shark/callback",
        ayla_login_url="https://user-sharkue1.aylanetworks.com",
        ayla_device_url="https://ads-sharkue1.aylanetworks.com",
        ayla_app_id="ios_shark_prod-3A-id",
        ayla_app_secret="ios_shark_prod-74tFWGNg34LQCmR0m45SsThqrqs",
        skegox_base="https://stakra.slatra.thor.skegox.com",
        skegox_api_key="QQdbSrgicK2PxvACI1a2P5AN2xgO78Lw1VvnYczb",
    ),
    "eu": RegionConfig(
        auth0_url="https://logineu.sharkninja.com",
        auth0_token_url="https://logineu.sharkninja.com/oauth/token",
        auth0_client_id="rKDx9O18dBrY3eoJMTkRiBZHDvd9Mx1I",
        auth0_redirect_uri="com.sharkninja.shark://logineu.sharkninja.com/ios/com.sharkninja.shark/callback",
        ayla_login_url="https://user-field-eu.aylanetworks.com",
        ayla_device_url="https://ads-eu.aylanetworks.com",
        ayla_app_id="android_shark_prod-lg-id",
        ayla_app_secret="android_shark_prod-xuf9mlHOo0p3Ty5bboFROSyRBlE",
        skegox_base="https://stakra.rannsaka.thor.skegox.com",
        skegox_api_key="T5m8d45crZDV9I5aCEZr4n2gSqJW64r2RNXqqhh1",
    ),
}

AUTH0_SCOPES = "openid email profile offline_access"
AUTH0_CUSTOM_SCHEME = "com.sharkninja.shark://"


class OperatingMode(IntEnum):
    """Shark vacuum operating modes."""

    STOP = 0
    PAUSE = 1
    START = 2
    RETURN = 3
    EXPLORE = 4
    # Mode 5 still unknown
    ROOM_CLEAN = 6  # room/area clean (observed on RV2820ZECA)
    MOP = 7
    VACUUM_AND_MOP = 8


class PowerMode(IntEnum):
    """Suction power levels."""

    ECO = 0
    NORMAL = 1
    MAX = 2


# Map OperatingMode to Home Assistant vacuum state strings
OPERATING_MODE_TO_HA_STATE: dict[OperatingMode, str] = {
    OperatingMode.STOP: "idle",
    OperatingMode.PAUSE: "paused",
    OperatingMode.START: "cleaning",
    OperatingMode.RETURN: "returning",
    OperatingMode.EXPLORE: "cleaning",
    OperatingMode.ROOM_CLEAN: "cleaning",
    OperatingMode.MOP: "cleaning",
    OperatingMode.VACUUM_AND_MOP: "cleaning",
}

POWER_MODE_NAMES: dict[PowerMode, str] = {
    PowerMode.ECO: "eco",
    PowerMode.NORMAL: "normal",
    PowerMode.MAX: "max",
}

POWER_MODE_BY_NAME: dict[str, PowerMode] = {v: k for k, v in POWER_MODE_NAMES.items()}

# HA command strings to OperatingMode
HA_COMMAND_TO_MODE: dict[str, OperatingMode] = {
    "start": OperatingMode.START,
    "stop": OperatingMode.STOP,
    "pause": OperatingMode.PAUSE,
    "return_to_base": OperatingMode.RETURN,
}

# Ayla device property names — GET (read) and SET (write) are separate
# Read properties (returned by GET /properties.json)
PROP_GET_OPERATING_MODE = "GET_Operating_Mode"
PROP_GET_CHARGING_STATUS = "GET_Charging_Status"
PROP_GET_BATTERY_CAPACITY = "GET_Battery_Capacity"
PROP_GET_ERROR_CODE = "GET_Error_Code"
PROP_GET_EXTENDED_ERROR_CODE = "GET_Extended_Error_Code"
PROP_GET_RSSI = "GET_RSSI"
PROP_GET_POWER_MODE = "GET_Power_Mode"
PROP_GET_DOCKED_STATUS = "GET_DockedStatus"
PROP_GET_ROBOT_ROOM_LIST = "GET_Robot_Room_List"
PROP_GET_ROOM_DEFINITION = "GET_Room_Definition"
PROP_GET_DEVICE_MODEL_NUMBER = "GET_Device_Model_Number"
PROP_GET_ROBOT_FIRMWARE_VERSION = "GET_Robot_Firmware_Version"
PROP_GET_FAN_JET_SETTING = "GET_FanJetSetting"
PROP_GET_WARNING_CODE = "GET_Warning_Code"
# Warning codes the robot reports but the Shark app doesn't surface, so they
# shouldn't turn the HA Warning sensor on. 43 is "Refill Pump Overcurrent" on
# the RV2800 series (see RV2800_ERROR_CODES). On an RV2820ZEUS it appears
# around the start of most cleans, including vacuum-only ones, and clears on
# its own hours later. Remove it here if you rely on mopping and want to see it.
IGNORED_WARNING_CODES = frozenset({43})
PROP_GET_EVACUATING = "GET_Evacuating"
PROP_GET_EVACUATE = "GET_evacuate"
PROP_GET_EVACUATE_RESUME_STATUS = "GET_evacuate_resume_status"
PROP_GET_DOCK_ERROR_CODE = "GET_DockErrorCode"
PROP_GET_DOCK_KNOB_STATUS = "GET_dock_knob_status"
PROP_GET_RUN_TIME_CUMULATIVE = "GET_RunTimeCumulative"
PROP_GET_REPLACE_BATTERY = "GET_ReplaceBattery"
PROP_GET_RECOMMEND_RANDR = "GET_RecommendRandR"
PROP_GET_SCHEDULE = "GET_Schedule"
# Mop water flow level (vacuum+mop combo models). Shares the same 0/1/2
# eco/normal/max scale as Power_Mode — confirmed against the SharkClean
# app's "Water Flow Level" slider on a RV2820YEUS unit.
PROP_GET_FLOW_MODE = "GET_Flow_Mode"
# Water tank sensors on mop-washing bases (NeverTouch-style docks), as a JSON
# string, e.g. {"CleanTank":{"Install":0,"Empty":0},"GreyTank":{"Install":0,"Full":0}}.
# Confirmed on an AV301WXEUK by removing each tank with the robot docked:
# CleanTank.Empty -> 1 when the clean water tank is empty or removed,
# GreyTank.Full -> 1 when the dirty water tank is full or removed. The
# Install flags did not change. Values only refresh while the robot is docked.
PROP_GET_DOCK_SENSOR_DATA = "GET_DockSensorData"
# Wet/mop capability signals — presence in the shadow identifies
# mop-capable (water flow level) and wet/dry-capable (wet/dry/deep
# clean modes) device families. All dry-only models (e.g. AV251WAXUS)
# report Flow_Mode but lack both of these.
PROP_GET_MOP_PLATE_ATTACHED = "GET_MopPlateAttached"
PROP_GET_CLEANING_PARAMETERS = "GET_CleaningParameters"
# Extended operating state, a JSON string such as
# '{"operating_mode":6,"sys_st":6}' (observed on UR2850ZEUS).
PROP_GET_OPERATING_MODE_EX = "GET_Operating_Mode_Ex"
# Current clean job: a JSON string with areas_to_clean, cleantype and
# trigger while a job exists, or the bare string "*" when there is none.
PROP_GET_AREAS_TO_CLEAN_V3 = "GET_AreasToClean_V3"
PROP_GET_RECHARGING_TO_RESUME = "GET_RechargingToResume"

# Write properties (used with POST /datapoints.json)
PROP_SET_OPERATING_MODE = "SET_Operating_Mode"
PROP_SET_POWER_MODE = "SET_Power_Mode"
PROP_SET_FIND_DEVICE = "SET_Find_Device"
PROP_SET_FLOW_MODE = "SET_Flow_Mode"

# Error code descriptions
# Sources: sharkiqlibs/sharkiq, ayla-iot-unofficial, Hubitat SharkIQ driver,
# Domoticz SharkIQ integration, SharkNinja support docs.
ERROR_CODES: dict[int, str] = {
    0: "No error",
    1: "Side wheel is stuck",
    2: "Side brush is stuck",
    3: "Suction motor failed",
    4: "Brushroll stuck",
    5: "Side wheel is stuck",
    6: "Bumper is stuck",
    7: "Cliff sensor is blocked",
    8: "Battery power is low",
    9: "No dustbin",
    10: "Fall sensor is blocked",
    11: "Front wheel is stuck",
    12: "Wrong power adapter",
    13: "Switched off",
    14: "Magnetic strip error",
    16: "Top bumper is stuck",
    18: "Wheel encoder error",
    21: "Boot error",
    23: "Base placement error",
    24: "Critical low battery",
    26: "Dustbin blockage",
    40: "Dustbin is blocked",
    48: "Mop pad missing",  # reported on RV2820YEUS (issue #27)
}

# RV2800-series (PowerDetect NeverTouch) codes. Several numbers mean something
# different here than in ERROR_CODES above (e.g. 21, 23, 26), so this table is
# used only for these models. Source: SharkNinja support article "RV2800
# Series Shark POWERDETECT NeverTouch Base Robot Vacuum - Robot Error Codes"
# (published 2026-08-20). Where the article lists a number twice, the entry
# with its own dedicated article wins.
RV2800_MODELS = frozenset({
    "RV2800ZE", "RV2820ZE", "RV2820ZEUS", "RV2820ZECA", "RV2800YE",
    "RV2820YE", "RV2820YEUS", "UR2860YS", "AV2810YS", "RV2820YECA",
    "UR2850ZE", "UR2850ZEUS", "RV2810ZE", "RV2810ZEUS",
})
RV2800_ERROR_CODES: dict[int, str] = {
    0: "No error",
    2: "Side brush not spinning",
    3: "Suction motor error",
    4: "Brushroll motor overcurrent",
    5: "Wheel overcurrent",
    6: "Bumper error",
    7: "Cliff sensor error",
    9: "Dust cup error",
    10: "Wheel drop error",
    12: "Charging voltage error",
    17: "Battery low",
    18: "Wheel encoder failure",
    19: "Boot-up error",
    21: "Robot is stuck",
    23: "Robot tank empty",
    26: "Pad shift overcurrent",
    27: "Inclination error",
    30: "Cannot return to base",
    37: "Dock charging overcurrent",
    40: "Auto evacuation error",
    42: "Fanjet motor broken",
    43: "Refill pump overcurrent",
    46: "Brushroll motor overcurrent",
    47: "Active suspension error",
    48: "Pad plate missing",
    50: "Greywater evacuation overcurrent",
    54: "Greywater evacuation overcurrent",
    55: "Pad dry fan overcurrent",
    56: "Refill pump broken",
    58: "Remove pad plate",
    59: "Shuttle motor overcurrent",
    61: "Remove pad plate",
    62: "Pad detach motor overcurrent",
    69: "Robot tank cannot fill",
    1005: "Boot-up error",
    1023: "Suction motor broken",
    1030: "Side brush motor broken",
    1031: "Main brush motor broken",
    1087: "Pad shift overcurrent",
    1089: "Cannot return to base",
    1094: "Dust cup error",
    1095: "Battery low",
    1097: "Robot is stuck",
    1109: "Fanjet motor broken",
    1164: "Shuttle motor broken",
    1165: "Refill pump broken",
    1166: "Pad detach motor broken",
    1167: "Greywater pump broken",
    1168: "Pad dry fan broken",
}
