"""Protocol constants for Nintendo Switch Pro Controller and generic ODM clones."""

from enum import IntEnum


# Switch Output Report IDs
OUTPUT_REPORT_RUMBLE_AND_SUBCMD = 0x01
OUTPUT_REPORT_RUMBLE_ONLY       = 0x10
OUTPUT_REPORT_USB_CMD           = 0x80

# Switch Input Report IDs
INPUT_REPORT_SUBCMD_REPLY = 0x21
INPUT_REPORT_STANDARD_FULL = 0x30
INPUT_REPORT_NFC_IR        = 0x31
INPUT_REPORT_SIMPLE_HID    = 0x3F

# Switch Subcommands
SUBCMD_GET_ONLY_CONTROLLER_STATE = 0x00
SUBCMD_BLUETOOTH_MANUAL_PAIRING  = 0x01
SUBCMD_REQUEST_DEVICE_INFO       = 0x02
SUBCMD_SET_INPUT_REPORT_MODE     = 0x03
SUBCMD_SPI_FLASH_READ            = 0x10
SUBCMD_SET_PLAYER_LIGHTS         = 0x30
SUBCMD_ENABLE_VIBRATION          = 0x48
SUBCMD_ENABLE_IMU                = 0x40

# Input Report Modes for Subcommand 0x03
REPORT_MODE_STANDARD_FULL = 0x30
REPORT_MODE_NFC_IR        = 0x31
REPORT_MODE_SIMPLE_HID    = 0x3F

# Switch Neutral Rumble Data (8 bytes)
NEUTRAL_RUMBLE = bytes([0x00, 0x01, 0x40, 0x40, 0x00, 0x01, 0x40, 0x40])

# Switch USB Handshake Packets
USB_HANDSHAKE_INIT    = bytes([0x80, 0x01])
USB_HANDSHAKE_TIMEOUT = bytes([0x80, 0x03])
USB_HANDSHAKE_EN_USB  = bytes([0x80, 0x04])
USB_HANDSHAKE_RESET   = bytes([0x80, 0x05])
USB_HANDSHAKE_STATUS  = bytes([0x80, 0x02])


class BatteryStatus(IntEnum):
    EMPTY    = 0
    CRITICAL = 1
    LOW      = 2
    MEDIUM   = 3
    FULL     = 4

    @classmethod
    def from_high_nibble(cls, nibble: int) -> "BatteryStatus":
        """Convert Switch byte[2] high nibble to BatteryStatus."""
        # Battery level is in bits 1-3 of the high nibble (or level / 2)
        # 8 = Full, 6 = Medium, 4 = Low, 2 = Critical, 0 = Empty
        val = (nibble & 0x0E) >> 1
        if val >= 4:
            return cls.FULL
        elif val == 3:
            return cls.MEDIUM
        elif val == 2:
            return cls.LOW
        elif val == 1:
            return cls.CRITICAL
        return cls.EMPTY


class ProtocolMode(IntEnum):
    UNKNOWN        = 0
    SWITCH_FULL    = 1  # Standard report 0x30 (12-bit sticks, IMU, battery)
    SWITCH_REPLY   = 2  # Subcommand reply report 0x21
    ODM_SIMPLE_3F  = 3  # Report 0x3F (common in third party ODM clones)
    GENERIC_HID    = 4  # Raw DirectInput / generic buffer fallback
