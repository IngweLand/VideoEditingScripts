"""
Process low resolution videos (LRF) from DJI drones.
Either encode them with LUT applied if videos are shot in D-Log
or simply rename lrf files.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

temp_dir = "temp"
convertable_color_modes = ["d_log"]


def get_lrf_files(directory):
    if not os.path.exists(directory):
        raise FileNotFoundError(f"Directory '{directory}' not found.")

    lrf_filenames = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(".lrf"):
                lrf_filenames.append(os.path.join(root, file))

    return lrf_filenames


def get_color_mode(directory, filename_without_extension):
    srt_file = os.path.join(directory, f"{filename_without_extension}.srt")
    if not os.path.exists(srt_file):
        return None
    with open(srt_file, "r") as f:
        srt_content = f.read()
        pattern = r"\[color_md : (.*?)\]"
        match = re.search(pattern, srt_content)
        return match.group(1) if match else None


def process_files(directory, lut_file):
    files = get_lrf_files(directory)
    total_files = len(files)
    print(f"Found {total_files} .lrf files")
    for i, input_file in enumerate(files, start=1):
        print(f"Processing {i}/{total_files}. {input_file}")
        output_directory = os.path.dirname(input_file)
        filename = os.path.basename(input_file)
        filename_without_extension = os.path.splitext(filename)[0]
        color_mode = get_color_mode(output_directory,
                                    filename_without_extension)
        print(f"\t\tColor mode: {color_mode}")
        output_file = os.path.join(
            output_directory, f"{filename_without_extension}_preview.mp4")
        if color_mode.lower() in convertable_color_modes:
            apply_lut(input_file, output_file, lut_file)
        else:
            print("\t\tRenaming...")
            os.rename(input_file, output_file)


def apply_lut(input_file, output_file, lut_file):
    if not os.path.exists(lut_file):
        raise FileNotFoundError(f"LUT file '{lut_file}' not found.")

    print(f"\t\tApplying LUT...")
    ffmpeg_command = [
        'ffmpeg',
        '-y', '-stats',
        '-loglevel', 'error',
        '-i', input_file,
        '-vf',
        f"lut3d={lut_file}",
        '-c:a', 'copy',
        '-maxrate', '12M',
        '-bufsize', '3M',
        output_file
    ]
    subprocess.run(ffmpeg_command, check=True)


def copy_file_to_temp_dir(source_file_path):
    if not os.path.exists(temp_dir):
        os.mkdir(temp_dir)

    dest_file_path = os.path.join(temp_dir,
                                  os.path.basename(source_file_path))
    try:
        shutil.copy2(source_file_path, dest_file_path)
    except (shutil.Error, OSError) as e:
        print(f"Error copying file: {e}")
        return None
    return Path(dest_file_path).as_posix()


if __name__ == "__main__":
    lut_file = "D:\\VideoEditing\\LUTs\\dji_vivid.cube"
    if len(sys.argv) < 2:
        print("Usage: python process_previews.py [directory] [optional]["
              "lut_file]")
        sys.exit(1)

    videos_directory = sys.argv[1]

    if len(sys.argv) == 3:
        lut_file = sys.argv[2]

    lut_file = copy_file_to_temp_dir(lut_file)

    process_files(videos_directory, lut_file)

    try:
        shutil.rmtree(os.path.dirname(lut_file))
    except OSError as e:
        print(f"Error deleting temporary directory: {e}")

    print("Done!")
