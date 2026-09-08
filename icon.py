"""Gamepad icon generator for window, taskbar, and system tray."""

from PIL import Image, ImageDraw


def generate_gamepad_icon(connected: bool = True, size: int = 64) -> Image.Image:
    """Draw a clean, crisp gamepad icon with connection status indicator."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    scale = size / 64.0

    def s(val: float) -> int:
        return int(round(val * scale))

    # Main Controller Body (smooth rounded controller shape)
    body_color = (40, 44, 52, 255) if connected else (55, 58, 64, 255)
    border_color = (0, 180, 255, 255) if connected else (120, 125, 135, 255)

    # Controller main curve
    draw.rounded_rectangle(
        [s(6), s(14), s(58), s(50)],
        radius=s(14),
        fill=body_color,
        outline=border_color,
        width=max(1, s(2)),
    )

    # Left & Right grips (lower bumps)
    draw.ellipse([s(6), s(28), s(22), s(58)], fill=body_color, outline=border_color, width=max(1, s(2)))
    draw.ellipse([s(42), s(28), s(58), s(58)], fill=body_color, outline=border_color, width=max(1, s(2)))

    # Re-fill center to hide inner grip lines
    draw.rounded_rectangle(
        [s(8), s(16), s(56), s(48)],
        radius=s(12),
        fill=body_color
    )

    # Left D-Pad (cross)
    dpad_color = (180, 185, 195, 255)
    # Horizontal bar
    draw.rectangle([s(14), s(28), s(24), s(32)], fill=dpad_color)
    # Vertical bar
    draw.rectangle([s(17), s(25), s(21), s(35)], fill=dpad_color)

    # Right Action Buttons (ABXY diamond)
    btn_r = s(2)
    # Top (Y: yellow)
    draw.ellipse([s(46)-btn_r, s(25)-btn_r, s(46)+btn_r, s(25)+btn_r], fill=(255, 204, 0, 255))
    # Bottom (A: green)
    draw.ellipse([s(46)-btn_r, s(35)-btn_r, s(46)+btn_r, s(35)+btn_r], fill=(46, 204, 113, 255))
    # Left (X: blue)
    draw.ellipse([s(41)-btn_r, s(30)-btn_r, s(41)+btn_r, s(30)+btn_r], fill=(52, 152, 219, 255))
    # Right (B: red)
    draw.ellipse([s(51)-btn_r, s(30)-btn_r, s(51)+btn_r, s(30)+btn_r], fill=(231, 76, 60, 255))

    # Sticks
    stick_color = (25, 27, 32, 255)
    draw.ellipse([s(24), s(34), s(32), s(42)], fill=stick_color, outline=(100, 105, 115, 255), width=1)
    draw.ellipse([s(32), s(34), s(40), s(42)], fill=stick_color, outline=(100, 105, 115, 255), width=1)

    # Center Status LED (Green = Active/Connected, Orange = Waiting)
    led_color = (46, 204, 113, 255) if connected else (243, 156, 18, 255)
    draw.ellipse([s(30), s(22), s(34), s(26)], fill=led_color)

    return image


def save_ico_file(filepath: str = "app_icon.ico") -> None:
    """Generates and saves a multi-resolution Windows .ico file."""
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    images = [generate_gamepad_icon(connected=True, size=w) for w, _ in sizes]
    images[0].save(filepath, format="ICO", sizes=sizes, append_images=images[1:])
    print(f"[Icon] Generated {filepath}")


if __name__ == "__main__":
    save_ico_file()
