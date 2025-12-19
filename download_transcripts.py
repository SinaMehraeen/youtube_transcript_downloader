"""
YouTube Channel Transcript Downloader
======================================

This script downloads transcripts from all videos on a YouTube channel,
fetches video statistics, cleans the content, and saves everything as
clean formatted text files.

HOW IT WORKS:
1. Takes a YouTube channel URL as input
2. Uses 'scrapetube' library to get a list of all videos on the channel
3. For each video, uses 'youtube-transcript-api' to fetch the transcript
4. Uses 'yt-dlp' to fetch video statistics (views, likes, comments)
5. Cleans the transcript (removes [Music], [Applause], etc.)
6. Saves each transcript as a clean formatted file

OUTPUT FORMAT:
    Title: Video Title Here
    Video ID: abc123xyz
    URL: https://www.youtube.com/watch?v=abc123xyz
    View Count: 1234567
    Like Count: 12345
    Favorite Count: 0
    Comment Count: 234

    ========================================

    Cleaned transcript text here...
"""

# =============================================================================
# IMPORTS
# =============================================================================

import os
import re
import sys
import time
import random
import argparse
import itertools
from pathlib import Path

# Third-party library imports
import scrapetube
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False
    print("⚠️  yt-dlp not installed. Video statistics will not be fetched.")
    print("   Install with: pip install yt-dlp")


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

DEFAULT_DELAY = 3         # Seconds to wait between processing each video
MAX_RETRIES = 5           # How many times to retry if we get rate limited
INITIAL_RETRY_DELAY = 15  # Seconds to wait after first rate limit error

# Common YouTube annotations to remove (case-insensitive)
ANNOTATIONS_TO_REMOVE = [
    r'\[music\]',
    r'\[applause\]', 
    r'\[laughter\]',
    r'\[cheering\]',
    r'\[audience\]',
    r'\[inaudible\]',
    r'\[silence\]',
    r'\[background music\]',
    r'\[background noise\]',
    r'\[intro music\]',
    r'\[outro music\]',
    r'\[theme music\]',
    r'\[upbeat music\]',
    r'\[soft music\]',
    r'\[dramatic music\]',
    r'\[foreign\]',
    r'\[speaking foreign language\]',
    r'\[♪\]',
    r'\[♪♪\]',
    r'\[♪♪♪\]',
    r'♪',
]


# =============================================================================
# PROXY MANAGEMENT
# =============================================================================

_proxy_cycle = None
_proxy_list = []


def load_proxies(proxy_file: str) -> list:
    """Load proxies from a text file (one proxy per line)."""
    proxies = []
    path = Path(proxy_file)
    
    if not path.exists():
        print(f"⚠️  Proxy file not found: {proxy_file}")
        return proxies
    
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                if not line.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
                    line = f'http://{line}'
                proxies.append(line)
    
    print(f"🔄 Loaded {len(proxies)} proxies from: {path.absolute()}")
    return proxies


def init_proxy_rotation(proxies: list):
    """Initialize the global proxy rotator."""
    global _proxy_cycle, _proxy_list
    _proxy_list = proxies
    if proxies:
        _proxy_cycle = itertools.cycle(proxies)


def get_next_proxy() -> str | None:
    """Get the next proxy in the rotation."""
    global _proxy_cycle
    if _proxy_cycle:
        return next(_proxy_cycle)
    return None


def get_proxy_config(proxy_url: str) -> GenericProxyConfig:
    """Convert a proxy URL to a GenericProxyConfig."""
    return GenericProxyConfig(
        http_url=proxy_url,
        https_url=proxy_url
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def sanitize_filename(title: str) -> str:
    """Remove characters that aren't allowed in filenames."""
    sanitized = re.sub(r'[<>:"/\\|?*]', '', title)
    sanitized = re.sub(r'\s+', ' ', sanitized)
    return sanitized[:100].strip()


def extract_channel_identifier(url: str) -> tuple[str, str]:
    """Parse a YouTube channel URL and extract the channel identifier."""
    url = url.strip()
    
    if match := re.search(r'youtube\.com/@([\w-]+)', url):
        return ('username', match.group(1))
    
    if match := re.search(r'youtube\.com/channel/(UC[\w-]+)', url):
        return ('channel_id', match.group(1))
    
    if match := re.search(r'youtube\.com/c/([\w-]+)', url):
        return ('custom', match.group(1))
    
    if match := re.search(r'youtube\.com/user/([\w-]+)', url):
        return ('user', match.group(1))
    
    if url.startswith('@'):
        return ('username', url[1:])
    
    raise ValueError(
        f"Could not parse channel URL: {url}\n"
        "Supported formats:\n"
        "  - https://www.youtube.com/@ChannelName\n"
        "  - https://www.youtube.com/channel/UCxxxxxx\n"
        "  - https://www.youtube.com/c/CustomName\n"
        "  - https://www.youtube.com/user/Username\n"
        "  - @ChannelName"
    )


def get_channel_videos(channel_url: str, limit: int = None):
    """Get a list of all videos from a YouTube channel."""
    import json
    
    id_type, identifier = extract_channel_identifier(channel_url)
    
    print(f"📺 Fetching videos from channel: {identifier}")
    
    try:
        if id_type == 'channel_id':
            videos = scrapetube.get_channel(channel_id=identifier, limit=limit)
        elif id_type == 'username':
            videos = scrapetube.get_channel(channel_username=identifier, limit=limit)
        else:
            videos = scrapetube.get_channel(channel_url=channel_url, limit=limit)
        
        return videos
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Failed to fetch channel data (JSON error: {e})\n"
            "This usually means:\n"
            "  1. The channel URL or username is incorrect\n"
            "  2. The channel doesn't exist or was deleted\n"
            "  3. YouTube is rate-limiting your requests\n"
            "  4. Network connectivity issues\n\n"
            f"Please verify the channel exists: https://www.youtube.com/@{identifier}"
        )




# =============================================================================
# TEXT CLEANING FUNCTIONS
# =============================================================================

def clean_transcript_text(text: str) -> str:
    """
    Clean transcript text by removing annotations and fixing formatting.
    Returns a single continuous paragraph of text.
    """
    cleaned = text
    
    # Remove YouTube annotations (case-insensitive)
    for annotation in ANNOTATIONS_TO_REMOVE:
        cleaned = re.sub(annotation, '', cleaned, flags=re.IGNORECASE)
    
    # Remove any other bracketed annotations
    cleaned = re.sub(r'\[[^\]]*\]', '', cleaned)
    
    # Replace all newlines and carriage returns with spaces
    cleaned = re.sub(r'[\r\n]+', ' ', cleaned)
    
    # Fix multiple spaces
    cleaned = re.sub(r'  +', ' ', cleaned)
    
    # Remove spaces before punctuation
    cleaned = re.sub(r'\s+([.,!?;:])', r'\1', cleaned)
    
    # Ensure space after punctuation (if followed by letter)
    cleaned = re.sub(r'([.,!?;:])([A-Za-z])', r'\1 \2', cleaned)
    
    # Remove leading/trailing whitespace
    cleaned = cleaned.strip()
    
    return cleaned


# =============================================================================
# VIDEO STATISTICS FUNCTIONS
# =============================================================================

def get_video_statistics(video_id: str) -> dict | None:
    """
    Fetch statistics for a video using yt-dlp.
    
    Returns:
        Dictionary with video statistics, or None if failed
    """
    if not YT_DLP_AVAILABLE:
        return None
    
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            return {
                'view_count': info.get('view_count', 0) or 0,
                'like_count': info.get('like_count', 0) or 0,
                'favorite_count': 0,  # YouTube doesn't expose this anymore
                'comment_count': info.get('comment_count', 0) or 0,
            }
    except Exception:
        return None


# =============================================================================
# OUTPUT FORMATTING
# =============================================================================

def format_output_file(title: str, video_id: str, transcript: str, stats: dict | None) -> str:
    """
    Format the cleaned transcript with metadata header in the clean output format.
    
    Output format:
        Title: Video Title Here
        Video ID: abc123xyz
        URL: https://www.youtube.com/watch?v=abc123xyz
        View Count: 1234567
        Like Count: 12345
        Favorite Count: 0
        Comment Count: 234

        ========================================

        Cleaned transcript text here...
    """
    output = []
    
    # Add metadata section
    output.append(f"Title: {title}")
    output.append(f"Video ID: {video_id}")
    output.append(f"URL: https://www.youtube.com/watch?v={video_id}")
    
    # Add video stats if available
    if stats:
        output.append(f"View Count: {stats['view_count']}")
        output.append(f"Like Count: {stats['like_count']}")
        output.append(f"Favorite Count: {stats['favorite_count']}")
        output.append(f"Comment Count: {stats['comment_count']}")
    
    # Add separator
    output.append('')
    output.append('=' * 40)
    output.append('')
    
    # Add cleaned transcript
    cleaned_transcript = clean_transcript_text(transcript)
    output.append(cleaned_transcript)
    
    return '\n'.join(output)


# =============================================================================
# CORE TRANSCRIPT DOWNLOAD FUNCTION
# =============================================================================

def download_transcript(
    video_id: str, 
    languages: list = None, 
    retries: int = MAX_RETRIES, 
    manual_only: bool = False,
    use_proxies: bool = False
) -> tuple[str | None, str]:
    """
    Download the transcript for a single YouTube video.
    
    Returns:
        A tuple of (transcript_text, status)
    """
    if languages is None:
        languages = ['en', 'en-US', 'en-GB']
    
    for attempt in range(retries):
        try:
            current_proxy = None
            proxy_config = None
            if use_proxies:
                current_proxy = get_next_proxy()
                if current_proxy:
                    proxy_config = get_proxy_config(current_proxy)
            
            ytt_api = YouTubeTranscriptApi(proxy_config=proxy_config)
            transcript_list = ytt_api.list(video_id)
            
            transcript = None
            
            try:
                transcript = transcript_list.find_manually_created_transcript(languages)
            except NoTranscriptFound:
                if manual_only:
                    return None, "no_manual_transcript"
                
                try:
                    transcript = transcript_list.find_generated_transcript(languages)
                except NoTranscriptFound:
                    return None, "no_transcript_in_language"
            
            if transcript:
                transcript_data = transcript.fetch()
                full_text = ' '.join([snippet.text for snippet in transcript_data])
                return full_text, "success"
            
            return None, "no_transcript"
        
        except TranscriptsDisabled:
            return None, "transcripts_disabled"
        
        except NoTranscriptFound:
            return None, "no_transcript"
        
        except VideoUnavailable:
            return None, "video_unavailable"
        
        except Exception as e:
            error_msg = str(e)
            
            is_rate_limited = "429" in error_msg or "Too Many Requests" in error_msg
            is_proxy_error = "proxy" in error_msg.lower() or "connect" in error_msg.lower()
            
            if is_rate_limited or is_proxy_error:
                if attempt < retries - 1:
                    if use_proxies and current_proxy:
                        error_type = "Rate limited" if is_rate_limited else "Proxy failed"
                        print(f"    🔄 {error_type}. Trying next proxy (retry {attempt + 2}/{retries})...")
                        time.sleep(1)
                    else:
                        wait_time = INITIAL_RETRY_DELAY * (2 ** attempt) + random.uniform(1, 10)
                        print(f"    ⏳ Rate limited. Waiting {wait_time:.0f}s (retry {attempt + 2}/{retries})...")
                        time.sleep(wait_time)
                    continue
                else:
                    return None, "rate_limited"
            
            return None, f"error: {error_msg[:80]}"
    
    return None, "max_retries_exceeded"


# =============================================================================
# MAIN PROCESSING FUNCTION
# =============================================================================

def download_all_transcripts(
    channel_url: str,
    output_dir: str = "transcripts",
    limit: int = None,
    languages: list = None,
    delay: float = DEFAULT_DELAY,
    proxy_file: str = None,
    skip_stats: bool = False
):
    """
    Download transcripts for all videos on a YouTube channel.
    
    This function:
    1. Gets the list of videos from the channel
    2. Downloads each transcript
    3. Fetches video statistics (views, likes, comments)
    4. Cleans and formats the output
    5. Saves as clean formatted files
    """
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Load proxies if provided
    use_proxies = False
    if proxy_file:
        proxies = load_proxies(proxy_file)
        if proxies:
            init_proxy_rotation(proxies)
            use_proxies = True
    
    # Print initial status
    print(f"📁 Saving transcripts to: {output_path.absolute()}")
    print(f"⏱️  Delay between requests: {delay}s")
    if use_proxies:
        print(f"🔄 Proxy rotation enabled ({len(_proxy_list)} proxies)")
    if skip_stats:
        print("📊 Skipping video statistics")
    elif not YT_DLP_AVAILABLE:
        print("📊 Video statistics disabled (yt-dlp not installed)")
    print()
    
    # Get the list of videos
    videos = get_channel_videos(channel_url, limit)
    video_list = list(videos)
    total_videos = len(video_list)
    print(f"📊 Found {total_videos} videos to process\n")
    
    if total_videos == 0:
        print("❌ No videos found. Check the channel URL.")
        return
    
    # Initialize counters
    success_count = 0
    fail_count = 0
    skipped_count = 0
    rate_limit_count = 0
    
    # Process each video
    for idx, video in enumerate(video_list, 1):
        video_id = video['videoId']
        title = video.get('title', {}).get('runs', [{}])[0].get('text', video_id)
        
        safe_title = sanitize_filename(title)
        filename = f"{safe_title}_{video_id}.md"
        filepath = output_path / filename
        
        # Skip if already downloaded
        if filepath.exists():
            safe_name = title.encode('ascii', errors='replace').decode('ascii')[:50]
            print(f"[{idx}/{total_videos}] ⏭️  Skipping (exists): {safe_name}...")
            skipped_count += 1
            continue
        
        # Show progress (with safe filename for console)
        safe_name = title.encode('ascii', errors='replace').decode('ascii')[:50]
        print(f"[{idx}/{total_videos}] 📄 Processing: {safe_name}...")
        
        # Download transcript
        transcript, status = download_transcript(
            video_id, 
            languages, 
            use_proxies=use_proxies
        )
        
        if transcript:
            # Fetch video statistics (unless disabled)
            stats = None
            if not skip_stats and YT_DLP_AVAILABLE:
                stats = get_video_statistics(video_id)
            
            # Format and save the output
            output_content = format_output_file(title, video_id, transcript, stats)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(output_content)
            
            stats_info = ""
            if stats:
                stats_info = f" (Views: {stats['view_count']:,})"
            print(f"    ✅ Saved: {filename[:60]}...{stats_info}")
            success_count += 1
        else:
            status_messages = {
                "no_transcript": "No transcript available",
                "no_manual_transcript": "Only auto-generated (skipped)",
                "no_transcript_in_language": "No transcript in preferred language",
                "transcripts_disabled": "Transcripts disabled",
                "video_unavailable": "Video unavailable",
                "rate_limited": "Rate limited (try again later)",
                "max_retries_exceeded": "Max retries exceeded",
            }
            msg = status_messages.get(status, status)
            print(f"    ❌ {msg}")
            fail_count += 1
            
            if status == "rate_limited":
                rate_limit_count += 1
                if rate_limit_count >= 3:
                    print("\n⚠️  Too many rate limits. Consider:")
                    print("   1. Wait 1-2 hours before trying again")
                    print("   2. Use a VPN to change your IP address")
                    break
        
        # Wait before next video
        if idx < total_videos:
            actual_delay = delay + random.uniform(1, 3)
            time.sleep(actual_delay)
    
    # Print final summary
    print(f"\n{'='*50}")
    print(f"✨ Done! Results:")
    print(f"    ✅ Downloaded: {success_count}")
    print(f"    ⏭️  Skipped (existing): {skipped_count}")
    print(f"    ❌ Failed: {fail_count}")
    print(f"📁 Files saved to: {output_path.absolute()}")


# =============================================================================
# COMMAND-LINE INTERFACE
# =============================================================================

def main():
    """Entry point for the command-line interface."""
    
    parser = argparse.ArgumentParser(
        description="Download YouTube channel transcripts with statistics (cleaned output).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python download_transcripts.py https://www.youtube.com/@ChannelName
  python download_transcripts.py @ChannelName -o my_transcripts
  python download_transcripts.py @ChannelName --limit 10 --delay 5
  python download_transcripts.py @ChannelName --skip-stats

Output format:
  Title: Video Title
  Video ID: abc123xyz
  URL: https://www.youtube.com/watch?v=abc123xyz
  View Count: 1234567
  Like Count: 12345
  Favorite Count: 0
  Comment Count: 234

  ========================================

  Cleaned transcript text...
        """
    )
    
    parser.add_argument(
        "channel_url",
        help="YouTube channel URL or @username"
    )
    
    parser.add_argument(
        "-o", "--output",
        default="transcripts",
        help="Output directory for transcripts (default: transcripts)"
    )
    
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=None,
        help="Maximum number of videos to process (default: all)"
    )
    
    parser.add_argument(
        "--languages",
        nargs="+",
        default=['en', 'en-US', 'en-GB'],
        help="Preferred transcript languages (default: en en-US en-GB)"
    )
    
    parser.add_argument(
        "-d", "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Delay between requests in seconds (default: {DEFAULT_DELAY})"
    )
    
    parser.add_argument(
        "-p", "--proxies",
        type=str,
        default=None,
        help="Path to proxy list file (one proxy per line) for IP rotation"
    )
    
    parser.add_argument(
        "--skip-stats",
        action="store_true",
        help="Skip fetching video statistics (faster, but no view/like counts)"
    )
    
    args = parser.parse_args()
    
    try:
        download_all_transcripts(
            channel_url=args.channel_url,
            output_dir=args.output,
            limit=args.limit,
            languages=args.languages,
            delay=args.delay,
            proxy_file=args.proxies,
            skip_stats=args.skip_stats
        )
    except ValueError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⏹️  Cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
