import os
from PIL import Image, ImageDraw, ImageFont

def generate_icons():
    assets_dir = os.path.join("desktop", "assets")
    os.makedirs(assets_dir, exist_ok=True)

    size = (256, 256)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Draw rounded rectangle background (Emerald Green #10B981)
    bg_color = (16, 185, 129, 255)
    draw.rounded_rectangle([10, 10, 246, 246], radius=48, fill=bg_color)

    # Draw Shield Symbol in white
    # Shield shape points
    shield_points = [
        (128, 45),   # Top center
        (195, 75),   # Top right
        (195, 150),  # Right side
        (128, 215),  # Bottom point
        (61, 150),   # Left side
        (61, 75)     # Top left
    ]
    draw.polygon(shield_points, fill=(255, 255, 255, 255))

    # Inner shield accent (emerald green cross/check mark)
    inner_shield = [
        (128, 65),
        (180, 88),
        (180, 145),
        (128, 198),
        (76, 145),
        (76, 88)
    ]
    draw.polygon(inner_shield, fill=bg_color)

    # Checkmark inside inner shield
    check_points = [
        (100, 135),
        (120, 155),
        (158, 105),
        (144, 95),
        (118, 138),
        (108, 126)
    ]
    draw.polygon(check_points, fill=(255, 255, 255, 255))

    # Save PNG
    png_path = os.path.join(assets_dir, "icon.png")
    image.save(png_path, format="PNG")
    print(f"Generated PNG icon at: {png_path}")

    # Save ICO with multiple embedded sizes
    ico_path = os.path.join(assets_dir, "icon.ico")
    image.save(ico_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"Generated ICO icon at: {ico_path}")

if __name__ == "__main__":
    generate_icons()
