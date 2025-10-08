import subprocess
import logging
import os

logger = logging.getLogger(__name__)


def get_video_duration(video_path: str) -> float:
    """
    Get the duration of a video file using ffprobe

    Args:
        video_path: Path to video file

    Returns:
        Duration in seconds, or 5.0 as fallback
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip())
        logger.info(f"Video duration for {video_path}: {duration}s")
        return duration
    except Exception as e:
        logger.warning(f"Could not get duration for {video_path}: {e}")
        return 5.0


def format_time(seconds: float) -> str:
    """
    Format time in seconds to SRT timestamp format (HH:MM:SS,mmm)

    Args:
        seconds: Time in seconds

    Returns:
        Formatted timestamp string
    """
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    milliseconds = int((secs - int(secs)) * 1000)

    return f"{int(hours):02}:{int(minutes):02}:{int(secs):02},{milliseconds:03}"


def write_srt(subtitles, max_words_per_line: int = 3) -> str:
    """
    Convert Whisper segments to SRT format with word limiting
    Args:
        subtitles: List of subtitle segments from Whisper
        max_words_per_line: Maximum words per subtitle line
    Returns:
        SRT formatted string
    """
    srt_output = []
    counter = 1
    for seg in subtitles:
        start = seg["start"]
        end = seg["end"]
        text = seg["text"].strip()
        words = text.split()
        duration = end - start
        if len(words) <= max_words_per_line:
            chunks = [text]
        else:
            chunks = []
            for i in range(0, len(words), max_words_per_line):
                chunk = " ".join(words[i:i + max_words_per_line])
                chunks.append(chunk)
        chunk_duration = duration / len(chunks)
        for idx, chunk in enumerate(chunks):
            chunk_start = start + (idx * chunk_duration)
            chunk_end = start + ((idx + 1) * chunk_duration)
            srt_output.append(
                f"{counter}\n{format_time(chunk_start)} --> {format_time(chunk_end)}\n{chunk}\n"
            )
            counter += 1
    return "\n".join(srt_output)


def burn_subtitles(video_path: str, srt_text: str, output_path: str, settings: dict = None) -> None:
    """
    Burn subtitles into video using FFmpeg with custom styling
    Args:
        video_path: Path to input video
        srt_text: SRT formatted subtitles
        output_path: Path for output video
        settings: Caption styling settings
    Raises:
        subprocess.CalledProcessError: If FFmpeg fails
    """
    # Default settings
    if settings is None:
        settings = {
            "shadow-offset": 2,
            "shadow-color": "#000000",
            "max-words-per-line": 3,
            "font-size": 80,
            "outline-color": "#000000",
            "word-color": "#FFFFFF",
            "outline-width": 3,
            "x": 540,
            "y": 1400,
            "style": "classic",
            "font-family": "Nunito",
            "position": "custom",
            "line-color": "#FFFFFF"
        }
    
    srt_path = video_path.replace(".mp4", "_temp.srt")
    try:
        with open(srt_path, "w", encoding="utf-8") as srt_file:
            srt_file.write(srt_text)
        logger.info(f"Burning subtitles into video: {video_path}")
        srt_path_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
        
        # Convert hex colors to ASS format (&H00BBGGRR)
        def hex_to_ass_color(hex_color):
            hex_color = hex_color.lstrip('#')
            r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
            return f"&H00{b}{g}{r}"
        
        primary_color = hex_to_ass_color(settings["word-color"])
        outline_color = hex_to_ass_color(settings["outline-color"])
        shadow_color = hex_to_ass_color(settings["shadow-color"])
        
        # Build subtitle filter with custom styling
        subtitle_filter = (
            f"subtitles={srt_path_escaped}:force_style='"
            f"FontName={settings['font-family']},"
            f"FontSize={settings['font-size']},"
            f"PrimaryColour={primary_color},"
            f"OutlineColour={outline_color},"
            f"BackColour={shadow_color},"
            f"BorderStyle=1,"
            f"Outline={settings['outline-width']},"
            f"Shadow={settings['shadow-offset']},"
            f"Alignment=2,"
            f"MarginV={1920 - settings['y']}'"
        )
        
        cmd = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-vf", subtitle_filter,
            "-c:a", "copy",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Subtitles burned successfully: {output_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error: {e.stderr}")
        raise
    finally:
        if os.path.exists(srt_path):
            os.remove(srt_path)

def merge_video_audio(
    video_path: str,
    audio_path: str,
    output_path: str,
    video_volume: float = 0.2,
    audio_volume: float = 2.0,
    duration: float = 5.0,
    width: int = 1080,
    height: int = 1920,
    resize_mode: str = "cover"
) -> None:
    """
    Merge video with audio using FFmpeg

    Args:
        video_path: Path to video file
        audio_path: Path to audio file
        output_path: Path for output file
        video_volume: Volume level for video audio
        audio_volume: Volume level for added audio
        duration: Duration to trim
        width: Output width
        height: Output height
        resize_mode: "cover" or "contain"

    Raises:
        subprocess.CalledProcessError: If FFmpeg fails
    """
    try:
        logger.info(f"Merging video {video_path} with audio {audio_path}")

        if resize_mode == "cover":
            scale_filter = f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}[v]"
        else:
            scale_filter = f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2[v]"

        filter_complex = (
            f"{scale_filter};"
            f"[0:a]volume={video_volume}[va];"
            f"[1:a]volume={audio_volume},atrim=duration={duration},asetpts=PTS-STARTPTS[aa];"
            f"[va][aa]amix=inputs=2:duration=first[a]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-t", str(duration),
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "48000",
            "-ac", "2",
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Video and audio merged: {output_path}")

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg merge error: {e.stderr}")
        raise


def concat_videos(video_list_path: str, output_path: str) -> None:
    """
    Concatenate multiple videos using FFmpeg concat demuxer

    Args:
        video_list_path: Path to text file with list of videos
        output_path: Path for output video

    Raises:
        subprocess.CalledProcessError: If FFmpeg fails
    """
    try:
        logger.info(f"Concatenating videos from list: {video_list_path}")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", video_list_path,
            "-c", "copy",
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Videos concatenated: {output_path}")

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg concat error: {e.stderr}")
        raise


def add_background_music(
    video_path: str,
    music_path: str,
    output_path: str,
    music_volume: float = 0.3,
    video_volume: float = 1.0
) -> None:
    """
    Add background music to a video

    Args:
        video_path: Path to video file
        music_path: Path to music file
        output_path: Path for output video
        music_volume: Volume level for background music
        video_volume: Volume level for video audio

    Raises:
        subprocess.CalledProcessError: If FFmpeg fails
    """
    try:
        video_duration = get_video_duration(video_path)
        logger.info(f"Adding background music to video (duration: {video_duration}s)")

        filter_complex = (
            f"[0:a]volume={video_volume}[va];"
            f"[1:a]volume={music_volume},aloop=loop=-1:size=2e+09,atrim=duration={video_duration}[ma];"
            f"[va][ma]amix=inputs=2:duration=first:dropout_transition=2[a]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-shortest",
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Background music added: {output_path}")

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg background music error: {e.stderr}")
        raise
