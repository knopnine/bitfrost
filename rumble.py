"""Haptic feedback and rumble translation for Nintendo Switch Pro and ODM controllers."""

from typing import Tuple

# High-frequency amplitude lookup table (from dekuNukem and SDL hidapi)
# Maps 16-bit amplitude [0..65535] to 8-bit Switch high amplitude code
HFA_TABLE = [
    (0, 0x00), (514, 0x02), (775, 0x04), (921, 0x06), (1096, 0x08),
    (1303, 0x0A), (1550, 0x0C), (1843, 0x0E), (2192, 0x10), (2606, 0x12),
    (3100, 0x14), (3686, 0x16), (4383, 0x18), (5213, 0x1A), (6199, 0x1C),
    (7372, 0x1E), (7698, 0x20), (8039, 0x22), (8395, 0x24), (8767, 0x26),
    (9155, 0x28), (9560, 0x2A), (9984, 0x2C), (10426, 0x2E), (10887, 0x30),
    (11369, 0x32), (11873, 0x34), (12398, 0x36), (12947, 0x38), (13520, 0x3A),
    (14119, 0x3C), (14744, 0x3E), (15067, 0x40), (15397, 0x42), (15734, 0x44),
    (16079, 0x46), (16431, 0x48), (16790, 0x4A), (17158, 0x4C), (17534, 0x4E),
    (17918, 0x50), (18310, 0x52), (18711, 0x54), (19121, 0x56), (19540, 0x58),
    (19967, 0x5A), (20405, 0x5C), (20851, 0x5E), (21308, 0x60), (21775, 0x62),
    (22251, 0x64), (22739, 0x66), (23236, 0x68), (23745, 0x6A), (24265, 0x6C),
    (24797, 0x6E), (25340, 0x70), (25894, 0x72), (26462, 0x74), (27041, 0x76),
    (27633, 0x78), (28238, 0x7A), (28856, 0x7C), (29488, 0x7E), (30134, 0x80),
    (30794, 0x82), (31468, 0x84), (32157, 0x86), (32861, 0x88), (33581, 0x8A),
    (34316, 0x8C), (35068, 0x8E), (35836, 0x90), (36620, 0x92), (37422, 0x94),
    (38242, 0x96), (39079, 0x98), (39935, 0x9A), (40809, 0x9C), (41703, 0x9E),
    (42616, 0xA0), (43549, 0xA2), (44503, 0xA4), (45477, 0xA6), (46473, 0xA8),
    (47491, 0xAA), (48531, 0xAC), (49593, 0xAE), (50679, 0xB0), (51789, 0xB2),
    (52923, 0xB4), (54082, 0xB6), (55266, 0xB8), (56476, 0xBA), (57713, 0xBC),
    (58977, 0xBE), (60268, 0xC0), (61588, 0xC2), (62936, 0xC4), (64315, 0xC6),
    (65535, 0xC8)
]

# Low-frequency amplitude lookup table
LFA_TABLE = [
    (0, 0x0040), (514, 0x8040), (775, 0x0041), (921, 0x8041), (1096, 0x0042),
    (1303, 0x8042), (1550, 0x0043), (1843, 0x8043), (2192, 0x0044), (2606, 0x8044),
    (3100, 0x0045), (3686, 0x8045), (4383, 0x0046), (5213, 0x8046), (6199, 0x0047),
    (7372, 0x8047), (7698, 0x0048), (8039, 0x8048), (8395, 0x0049), (8767, 0x8049),
    (9155, 0x004A), (9560, 0x804A), (9984, 0x004B), (10426, 0x804B), (10887, 0x004C),
    (11369, 0x804C), (11873, 0x004D), (12398, 0x804D), (12947, 0x004E), (13520, 0x804E),
    (14119, 0x004F), (14744, 0x804F), (15067, 0x0050), (15397, 0x8050), (15734, 0x0051),
    (16079, 0x8051), (16431, 0x0052), (16790, 0x8052), (17158, 0x0053), (17534, 0x8053),
    (17918, 0x0054), (18310, 0x8054), (18711, 0x0055), (19121, 0x8055), (19540, 0x0056),
    (19967, 0x8056), (20405, 0x0057), (20851, 0x8057), (21308, 0x0058), (21775, 0x8058),
    (22251, 0x0059), (22739, 0x8059), (23236, 0x005A), (23745, 0x805A), (24265, 0x005B),
    (24797, 0x805B), (25340, 0x005C), (25894, 0x805C), (26462, 0x005D), (27041, 0x805D),
    (27633, 0x005E), (28238, 0x805E), (28856, 0x005F), (29488, 0x805F), (30134, 0x0060),
    (30794, 0x8060), (31468, 0x0061), (32157, 0x8061), (32861, 0x0062), (33581, 0x8062),
    (34316, 0x0063), (35068, 0x8063), (35836, 0x0064), (36620, 0x8064), (37422, 0x0065),
    (38242, 0x8065), (39079, 0x0066), (39935, 0x8066), (40809, 0x0067), (41703, 0x8067),
    (42616, 0x0068), (43549, 0x8068), (44503, 0x0069), (45477, 0x8069), (46473, 0x006A),
    (47491, 0x806A), (48531, 0x006B), (49593, 0x806B), (50679, 0x006C), (51789, 0x806C),
    (52923, 0x006D), (54082, 0x806D), (55266, 0x006E), (56476, 0x806E), (57713, 0x006F),
    (58977, 0x806F), (60268, 0x0070), (61588, 0x8070), (62936, 0x0071), (64315, 0x8071),
    (65535, 0x0072)
]


def encode_high_amplitude(amp_16: int) -> int:
    """Encode 16-bit amplitude to Switch high amplitude byte."""
    for threshold, code in HFA_TABLE:
        if amp_16 <= threshold:
            return code
    return HFA_TABLE[-1][1]


def encode_low_amplitude(amp_16: int) -> int:
    """Encode 16-bit amplitude to Switch low amplitude 16-bit word."""
    for threshold, code in LFA_TABLE:
        if amp_16 <= threshold:
            return code
    return LFA_TABLE[-1][1]


def encode_motor_rumble(amp_8bit: int) -> bytes:
    """Encodes an 8-bit motor value [0..255] into 4 bytes of Switch HD rumble data."""
    if amp_8bit <= 0:
        return bytes([0x00, 0x01, 0x40, 0x40])

    amp_16 = min(65535, amp_8bit * 257)
    hf_amp = encode_high_amplitude(amp_16)
    lf_amp = encode_low_amplitude(amp_16)

    # High frequency default: ~320 Hz (high byte adds 0x01)
    # Low frequency default: ~160 Hz (base 0x40)
    b0 = 0x00
    b1 = (hf_amp + 0x01) & 0xFF
    b2 = (0x40 + ((lf_amp >> 8) & 0xFF)) & 0xFF
    b3 = lf_amp & 0xFF
    return bytes([b0, b1, b2, b3])


def build_rumble_packet(large_motor: int, small_motor: int, packet_counter: int) -> bytes:
    """Constructs a 64-byte Switch Pro Output Report 0x10 (Rumble Only).

    large_motor (0..255): Heavy / Low frequency motor (Left motor)
    small_motor (0..255): Light / High frequency motor (Right motor)
    """
    left_bytes = encode_motor_rumble(large_motor)
    right_bytes = encode_motor_rumble(small_motor)

    packet = bytearray()
    packet.append(0x10)                   # Output Report 0x10: Rumble Only
    packet.append(packet_counter & 0x0F)  # Rolling counter 0..15
    packet.extend(left_bytes)             # Left Joy-Con motor
    packet.extend(right_bytes)            # Right Joy-Con motor

    # Pad to 64 bytes
    return bytes(packet.ljust(64, b"\x00"))
