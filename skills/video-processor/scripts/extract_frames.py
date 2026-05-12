import sys
import os
import subprocess

def extract_frames(input_path, output_dir, interval=5):
    """
    Extract frames from video at specified interval using ffmpeg.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    # ffmpeg command: -vf "fps=1/interval" extracts 1 frame every 'interval' seconds
    # %04d.jpg will name files 0001.jpg, 0002.jpg, etc.
    command = [
        'ffmpeg',
        '-i', input_path,
        '-vf', f'fps=1/{interval}',
        os.path.join(output_dir, 'frame_%04d.jpg')
    ]
    
    try:
        print(f"Executing: {' '.join(command)}")
        subprocess.run(command, check=True)
        print(f"Successfully extracted frames to {output_dir}")
    except subprocess.CalledProcessError as e:
        print(f"Error during ffmpeg execution: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python extract_frames.py <input_video> <output_dir> [interval_seconds]")
        sys.exit(1)
        
    video_path = sys.argv[1]
    out_dir = sys.argv[2]
    interval_sec = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    
    extract_frames(video_path, out_dir, interval_sec)
