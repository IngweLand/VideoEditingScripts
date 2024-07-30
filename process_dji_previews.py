"""
Generate resized previews from DJI drone videos.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

import blackboxprotobuf
from colorama import Style, Fore

temp_dir = "temp"
temp_encode_dir = "temp_encode"
convertable_color_modes = ["d_log"]
input_format = "mp4"
encoding_preset = "p7"
intermediate_video_bitrate = "30M"
final_video_bitrate = "10M"
max_video_bitrate = "30M"
video_buffer_size = "5M"
temp_video_dir = None
video_preview_file_suffix = "_preview"
output_extension = ".mp4"
regenerate_previews = False


def apply_lut(input_file, output_file, lut_file):
    if not os.path.exists(lut_file):
        raise FileNotFoundError(f"LUT file '{lut_file}' not found.")

    print(f"\t\tApplying LUT...")
    ffmpeg_command = [
        'ffmpeg',
        '-y',
        '-vsync', '0',
        '-stats', '-loglevel', 'error',
        '-i', input_file,
        '-vf',
        f"lut3d={lut_file}",
        '-profile:v', 'main',
        '-pix_fmt', 'yuv420p',
        '-c:v', 'hevc_nvenc',
        '-preset', encoding_preset,
        '-c:a', 'copy',
        '-b:v', final_video_bitrate,
        '-maxrate', max_video_bitrate,
        '-bufsize', video_buffer_size,
        output_file
    ]
    subprocess.run(ffmpeg_command, check=True)


def copy_file_to_temp_dir(file):
    if not os.path.exists(temp_dir):
        os.mkdir(temp_dir)

    dest_file_path = os.path.join(temp_dir,
                                  os.path.basename(file))
    try:
        shutil.copy2(file, dest_file_path)
    except (shutil.Error, OSError) as e:
        print(f"Error copying file: {e}")
        sys.exit(1)
    return Path(dest_file_path).as_posix()


def get_bin_filename(file, suffix):
    return f"{get_filename_without_extension(file)}_{suffix}.bin"


def get_color_mode_from_subs(file):
    srt_file = os.path.join(os.path.dirname(file), f"{get_filename_without_extension(file)}.srt")
    if not os.path.exists(srt_file):
        return None
    with open(srt_file, "r") as f:
        srt_content = f.read()
        pattern = r"\[color_md : (.*?)\]"
        match = re.search(pattern, srt_content)
        return match.group(1) if match else None


def get_color_mode_from_data_stream(file):
    filename = get_bin_filename(file, "0")
    intermediate_file = os.path.join(temp_video_dir, filename)
    ffmpeg_command = [
        'ffmpeg',
        '-v', 'quiet',
        '-i', file,
        '-map', '0:d:0',
        '-f', 'data',
        intermediate_file
    ]
    subprocess.run(ffmpeg_command, check=True)
    binary_data = load_binary_file(intermediate_file)
    message, typedef = blackboxprotobuf.protobuf_to_json(binary_data)
    message = json.loads(message)
    try:
        color_mode_code = message['2']['2']['3']['1']
        print(f"Color mode code: {color_mode_code}; file: {file}")
        if color_mode_code == 9:
            return "hlog"
        if color_mode_code == 19:
            return "dlog_m"
        if color_mode_code == 2:
            return "d_log"
        return "default"
    except:
        return "default"


def get_dji_videos_with_color_mode(files) -> List[Tuple[str, str]]:
    dji_files = []
    for f in files:
        metadata = get_video_metadata(f)
        tags = metadata['format']['tags']
        if "encoder" in tags and "DJI" in tags['encoder']:
            color_mode = get_color_mode_from_subs(f)
            if color_mode is None:
                color_mode = get_color_mode_from_data_stream(f)
            dji_files.append((f, color_mode))
    return dji_files


def get_filename_without_extension(file):
    return os.path.splitext(os.path.basename(file))[0]


def get_video_files(directory):
    if not os.path.exists(directory):
        raise FileNotFoundError(f"Directory '{directory}' not found.")

    file_paths = []
    for root, _, files in os.walk(directory):
        for file in files:
            if (file.lower().endswith(".mp4") or file.lower().endswith(
                    ".mov")) and video_preview_file_suffix not in file.lower():
                if regenerate_previews:
                    file_paths.append(os.path.join(root, file))
                elif not os.path.exists(os.path.join(root, get_preview_filename(file))):
                    file_paths.append(os.path.join(root, file))

    return file_paths


def get_preview_filename(file):
    return f"{get_filename_without_extension(file)}{video_preview_file_suffix}{output_extension}"


def get_video_metadata(file_path):
    ffmpeg_command = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_streams',
        '-show_format',
        '-i', file_path,
    ]
    result = subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def load_binary_file(file_path):
    with open(file_path, 'rb') as f:
        return f.read()


def process_video_files(directory, lut_file):
    files = get_video_files(directory)
    files = get_dji_videos_with_color_mode(files)
    total_files = len(files)
    print(f"Found {total_files} video files")
    for i, (input_file, color_mode) in enumerate(files, start=1):
        print(Fore.GREEN + f"Processing {i}/{total_files}. {input_file}" + Style.RESET_ALL)
        output_directory = os.path.dirname(input_file)
        print(f"\t\tColor mode: {color_mode}")
        output_filename = get_preview_filename(input_file)
        output_file = os.path.join(
            output_directory, output_filename)
        if color_mode is not None and color_mode.lower() in convertable_color_modes:
            intermediate_file = os.path.join(temp_video_dir, output_filename)
            try:
                resize(input_file, intermediate_file, intermediate_video_bitrate)
                apply_lut(intermediate_file, output_file, lut_file)
            except:
                pass
        else:
            print(f"\t\tSkipping...")
            # resize(input_file, output_file, final_video_bitrate)


def resize(input_file, output_file, bitrate):
    print(f"\t\tResizing...")
    ffmpeg_command = [
        'ffmpeg',
        '-y',
        '-vsync', '0',
        '-stats', '-loglevel', 'error',
        '-hwaccel', 'cuda',
        '-hwaccel_output_format', 'cuda',
        '-i', input_file,
        '-vf',
        f"scale_cuda=1920:-1",
        '-c:v', 'hevc_nvenc',
        '-preset', encoding_preset,
        '-b:v', bitrate,
        '-maxrate', max_video_bitrate,
        '-bufsize', video_buffer_size,
        '-an', '-sn', '-dn',
        output_file
    ]
    subprocess.run(ffmpeg_command, check=True)


def setup_args_parser():
    parser = argparse.ArgumentParser(description="Generate resized previews from DJI drone videos.")
    parser.add_argument("-l", "--lut_file", required=True,
                        help="Path to LUT file.")
    parser.add_argument("-rp", "--regenerate_previews", action="store_true",
                        help="If specified, the script will regenerate all previews. Default: false")
    parser.add_argument("input_directory", help="Directory with input video files.")
    return parser


if __name__ == "__main__":

    parser = setup_args_parser()
    args = parser.parse_args()
    if args.regenerate_previews:
        regenerate_previews = True

    input_directory = args.input_directory
    lut_file = copy_file_to_temp_dir(args.lut_file)

    # temp video encode dir
    temp_video_dir = os.path.join(input_directory, temp_dir)
    if os.path.exists(temp_video_dir):
        try:
            shutil.rmtree(temp_video_dir)
        except OSError as e:
            print(f"Error deleting temporary video directory: {e}")
            sys.exit(1)
    os.mkdir(temp_video_dir)

    process_video_files(input_directory, lut_file)

    try:
        shutil.rmtree(os.path.dirname(lut_file))
    except OSError as e:
        print(f"Error deleting temporary directory: {e}")
    try:
        shutil.rmtree(temp_video_dir)
    except OSError as e:
        print(f"Error deleting temporary video encode directory: {e}")

    print("Done!")
