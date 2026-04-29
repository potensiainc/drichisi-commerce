from rembg import remove
from PIL import Image
import os
import sys

def remove_background(input_path, output_path):
    """Remove background from image and save as PNG with transparency"""
    with open(input_path, 'rb') as input_file:
        input_data = input_file.read()

    output_data = remove(input_data)

    with open(output_path, 'wb') as output_file:
        output_file.write(output_data)

    print(f"Created: {output_path}")

def process_folder(input_folder, output_folder):
    """Process all images in a folder"""
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    image_extensions = ('.jpg', '.jpeg', '.png', '.webp')

    for filename in os.listdir(input_folder):
        if filename.lower().endswith(image_extensions):
            input_path = os.path.join(input_folder, filename)
            # Change extension to .png for transparency support
            output_filename = os.path.splitext(filename)[0] + '_nobg.png'
            output_path = os.path.join(output_folder, output_filename)

            try:
                remove_background(input_path, output_path)
            except Exception as e:
                print(f"Error processing {filename}: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python remove-bg.py <input_folder> [output_folder]")
        sys.exit(1)

    input_folder = sys.argv[1]
    output_folder = sys.argv[2] if len(sys.argv) > 2 else os.path.join(input_folder, 'nobg')

    process_folder(input_folder, output_folder)
    print("\nBackground removal complete!")
