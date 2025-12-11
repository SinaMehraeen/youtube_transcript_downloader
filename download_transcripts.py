"""
YouTube Channel Transcript Downloader
======================================

This script downloads transcripts from all videos on a YouTube channel and
saves them as Markdown files. It's useful for research, content analysis,
or creating searchable archives of video content.

HOW IT WORKS:
1. Takes a YouTube channel URL as input
2. Uses 'scrapetube' library to get a list of all videos on the channel
3. For each video, uses 'youtube-transcript-api' to fetch the transcript
4. Saves each transcript as a Markdown file

RATE LIMITING:
YouTube limits how many requests you can make. If you get blocked (429 errors),
you can use cookies from your browser to authenticate:
1. Install the 'Get cookies.txt LOCALLY' browser extension
2. Go to youtube.com while logged in
3. Export cookies to a file (e.g., cookies.txt)
4. Run: python download_transcripts.py @channel --cookies cookies.txt
"""

# =============================================================================
# IMPORTS
# =============================================================================

# Standard library imports (built into Python)
import os          # Operating system interface (not used directly, but good to have)
import re          # Regular expressions - for pattern matching in URLs and text
import sys         # System-specific parameters - for exiting with error codes
import time        # Time functions - for adding delays between requests
import random      # Random number generation - for adding randomness to delays
import argparse    # Command-line argument parsing - handles --limit, --delay, etc.
from pathlib import Path  # Object-oriented filesystem paths - easier file handling

# Third-party library imports (installed via pip)
import scrapetube  # Scrapes YouTube channel pages to get video IDs without API key
from youtube_transcript_api import YouTubeTranscriptApi  # Fetches video transcripts
from youtube_transcript_api._errors import (
    TranscriptsDisabled,  # Error when video owner has disabled transcripts
    NoTranscriptFound,    # Error when no transcript exists for the video
    VideoUnavailable,     # Error when video is private, deleted, or region-locked
)


# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# These values control how the script handles rate limiting from YouTube

DEFAULT_DELAY = 3         # Seconds to wait between processing each video
                          # Higher = slower but less likely to get rate limited

MAX_RETRIES = 5           # How many times to retry if we get rate limited
                          # Each retry waits longer (exponential backoff)

INITIAL_RETRY_DELAY = 15  # Seconds to wait after first rate limit error
                          # Doubles each retry: 15s, 30s, 60s, 120s, 240s


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def sanitize_filename(title: str) -> str:
    """
    Remove characters that aren't allowed in filenames on Windows/Mac/Linux.
    
    Args:
        title: The video title (may contain special characters)
    
    Returns:
        A clean string safe to use as a filename
    
    Example:
        "What is 2+2? A Video: Test" -> "What is 2+2 A Video Test"
    """
    # Remove characters not allowed in filenames: < > : " / \ | ? *
    sanitized = re.sub(r'[<>:"/\\|?*]', '', title)
    
    # Replace multiple spaces with a single space (cleanup)
    sanitized = re.sub(r'\s+', ' ', sanitized)
    
    # Limit length to 100 characters (some systems have filename limits)
    return sanitized[:100].strip()


def extract_channel_identifier(url: str) -> tuple[str, str]:
    """
    Parse a YouTube channel URL and extract the channel identifier.
    
    YouTube has multiple URL formats for channels:
    - @username format: youtube.com/@mkbhd
    - Channel ID format: youtube.com/channel/UCBcRF18a7Qf58cCRy5xuWwQ
    - Custom URL format: youtube.com/c/LinusTechTips
    - Legacy user format: youtube.com/user/marquesbrownlee
    
    Args:
        url: The YouTube channel URL or @username
    
    Returns:
        A tuple of (identifier_type, identifier_value)
        Example: ('username', 'mkbhd') or ('channel_id', 'UCBcRF18a7Qf58cCRy5xuWwQ')
    
    Raises:
        ValueError: If the URL format is not recognized
    """
    url = url.strip()  # Remove whitespace from beginning/end
    
    # Match @username format: youtube.com/@ChannelName
    # The [\w-]+ pattern matches letters, numbers, underscores, and hyphens
    if match := re.search(r'youtube\.com/@([\w-]+)', url):
        return ('username', match.group(1))
    
    # Match channel ID format: youtube.com/channel/UCxxxxxxxxxx
    # Channel IDs always start with "UC" followed by 22 characters
    if match := re.search(r'youtube\.com/channel/(UC[\w-]+)', url):
        return ('channel_id', match.group(1))
    
    # Match custom URL format: youtube.com/c/CustomName
    if match := re.search(r'youtube\.com/c/([\w-]+)', url):
        return ('custom', match.group(1))
    
    # Match legacy user format: youtube.com/user/Username
    if match := re.search(r'youtube\.com/user/([\w-]+)', url):
        return ('user', match.group(1))
    
    # Allow shorthand: just @ChannelName without the full URL
    if url.startswith('@'):
        return ('username', url[1:])  # Remove the @ and return the rest
    
    # If none of the patterns matched, raise an error with helpful message
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
    """
    Get a list of all videos from a YouTube channel.
    
    Uses the 'scrapetube' library which scrapes YouTube's website directly.
    This doesn't require an API key (unlike the official YouTube API).
    
    Args:
        channel_url: YouTube channel URL or @username
        limit: Maximum number of videos to fetch (None = all videos)
    
    Returns:
        A generator that yields video dictionaries containing:
        - videoId: The unique 11-character video ID
        - title: Nested dict containing the video title
        - And other metadata we don't use
    """
    # Parse the URL to determine how to fetch the channel
    id_type, identifier = extract_channel_identifier(channel_url)
    
    print(f"📺 Fetching videos from channel: {identifier}")
    
    # Call scrapetube with the appropriate parameter based on URL type
    if id_type == 'channel_id':
        # Direct channel ID (starts with UC)
        videos = scrapetube.get_channel(channel_id=identifier, limit=limit)
    elif id_type == 'username':
        # @username format
        videos = scrapetube.get_channel(channel_username=identifier, limit=limit)
    else:
        # Custom or legacy URLs - let scrapetube figure it out
        videos = scrapetube.get_channel(channel_url=channel_url, limit=limit)
    
    return videos


def validate_cookie_file(cookie_file: str) -> str | None:
    """
    Check if the cookie file exists and return its absolute path.
    
    Cookies help bypass rate limiting by authenticating as a logged-in user.
    YouTube is more lenient with authenticated requests.
    
    Args:
        cookie_file: Path to the cookies.txt file
    
    Returns:
        Absolute path to the file if it exists, None otherwise
    """
    from pathlib import Path
    path = Path(cookie_file)
    
    if path.exists():
        print(f"🍪 Using cookies from: {path.absolute()}")
        return str(path.absolute())
    else:
        print(f"⚠️  Cookie file not found: {cookie_file}")
        return None


# =============================================================================
# CORE TRANSCRIPT DOWNLOAD FUNCTION
# =============================================================================

def download_transcript(
    video_id: str, 
    languages: list = None, 
    retries: int = MAX_RETRIES, 
    manual_only: bool = False,
    cookies: str = None
) -> tuple[str | None, str]:
    """
    Download the transcript for a single YouTube video.
    
    This function tries to get the best available transcript:
    1. First, look for a manually-created transcript (higher quality)
    2. If not found, fall back to auto-generated captions
    
    Args:
        video_id: The 11-character YouTube video ID (e.g., "dQw4w9WgXcQ")
        languages: List of language codes to try ['en', 'en-US', 'en-GB']
        retries: Number of times to retry if rate limited
        manual_only: If True, skip videos that only have auto-generated captions
        cookies: Path to cookies.txt file for authentication
    
    Returns:
        A tuple of (transcript_text, status):
        - On success: ("Full transcript text...", "success")
        - On failure: (None, "error_code")
        
        Possible status codes:
        - "success": Transcript downloaded successfully
        - "no_manual_transcript": Only auto-generated available (when manual_only=True)
        - "no_transcript_in_language": No transcript in preferred languages
        - "transcripts_disabled": Video owner disabled transcripts
        - "video_unavailable": Video is private/deleted
        - "rate_limited": Too many requests, YouTube blocked us
    """
    # Default to English variants if no languages specified
    if languages is None:
        languages = ['en', 'en-US', 'en-GB']
    
    # Retry loop - will attempt up to 'retries' times if rate limited
    for attempt in range(retries):
        try:
            # Step 1: Get list of available transcripts for this video
            # This returns a TranscriptList object we can query
            transcript_list = YouTubeTranscriptApi.list_transcripts(
                video_id, 
                cookies=cookies  # Pass cookie file path for authentication
            )
            
            # Step 2: Try to find the best transcript
            transcript = None
            
            # First, try to find a manually-created transcript (human-made, higher quality)
            try:
                transcript = transcript_list.find_manually_created_transcript(languages)
            except NoTranscriptFound:
                # No manual transcript found in our preferred languages
                
                if manual_only:
                    # User only wants manual transcripts, skip this video
                    return None, "no_manual_transcript"
                
                # Try auto-generated captions as a fallback
                try:
                    transcript = transcript_list.find_generated_transcript(languages)
                except NoTranscriptFound:
                    # No transcript at all in our preferred languages
                    return None, "no_transcript_in_language"
            
            # Step 3: Fetch the actual transcript text
            if transcript:
                # transcript.fetch() returns a list of dictionaries:
                # [{'text': 'Hello', 'start': 0.0, 'duration': 1.5}, ...]
                transcript_data = transcript.fetch()
                
                # Extract just the text and join into a single string
                # We use spaces (not newlines) for continuous flowing text
                full_text = ' '.join([entry['text'] for entry in transcript_data])
                return full_text, "success"
            
            return None, "no_transcript"
        
        # Handle specific error types
        except TranscriptsDisabled:
            # Video owner has turned off transcripts for this video
            return None, "transcripts_disabled"
        
        except NoTranscriptFound:
            # No transcripts exist for this video at all
            return None, "no_transcript"
        
        except VideoUnavailable:
            # Video is private, deleted, or region-locked
            return None, "video_unavailable"
        
        except Exception as e:
            # Catch-all for other errors (network issues, rate limiting, etc.)
            error_msg = str(e)
            
            # Check if this is a rate limiting error (HTTP 429)
            if "429" in error_msg or "Too Many Requests" in error_msg:
                if attempt < retries - 1:
                    # Calculate wait time using exponential backoff
                    # Each retry waits longer: 15s, 30s, 60s, 120s...
                    wait_time = INITIAL_RETRY_DELAY * (2 ** attempt) + random.uniform(1, 10)
                    print(f"    ⏳ Rate limited. Waiting {wait_time:.0f}s (retry {attempt + 2}/{retries})...")
                    time.sleep(wait_time)
                    continue  # Go to next iteration of retry loop
                else:
                    # Used all retries, give up
                    return None, "rate_limited"
            
            # Some other error - return it truncated
            return None, f"error: {error_msg[:80]}"
    
    # Should only reach here if all retries exhausted
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
    cookies: dict = None
):
    """
    Download transcripts for all videos on a YouTube channel.
    
    This is the main orchestration function that:
    1. Gets the list of videos from the channel
    2. Loops through each video
    3. Downloads and saves each transcript
    4. Handles errors and displays progress
    
    Args:
        channel_url: YouTube channel URL or @username
        output_dir: Folder to save transcript files (created if doesn't exist)
        limit: Maximum videos to process (None = all)
        languages: Preferred transcript languages
        delay: Seconds to wait between each video
        cookies: Path to cookies.txt for authentication
    """
    
    # Create the output directory if it doesn't exist
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Print initial status information
    print(f"📁 Saving transcripts to: {output_path.absolute()}")
    print(f"⏱️  Delay between requests: {delay}s")
    if cookies:
        print("🍪 Using cookies for authentication")
    print()
    
    # Get the list of videos from the channel
    videos = get_channel_videos(channel_url, limit)
    
    # Convert the generator to a list so we can count total videos
    # (generators can only be iterated once, so we need a list)
    video_list = list(videos)
    total_videos = len(video_list)
    print(f"📊 Found {total_videos} videos to process\n")
    
    # Check if we found any videos
    if total_videos == 0:
        print("❌ No videos found. Check the channel URL.")
        return
    
    # Initialize counters for the final summary
    success_count = 0       # Successfully downloaded transcripts
    fail_count = 0          # Failed to download (various reasons)
    skipped_count = 0       # Skipped because file already exists
    rate_limit_count = 0    # Track consecutive rate limits
    
    # Process each video
    for idx, video in enumerate(video_list, 1):  # enumerate with start=1 for display
        # Extract video ID and title from the video data
        video_id = video['videoId']
        
        # Title is nested in a complex structure, use safe navigation with defaults
        title = video.get('title', {}).get('runs', [{}])[0].get('text', video_id)
        
        # Create a safe filename for this video
        safe_title = sanitize_filename(title)
        filename = f"{safe_title}_{video_id}.md"  # Include video ID to ensure uniqueness
        filepath = output_path / filename
        
        # Skip if we already downloaded this video
        if filepath.exists():
            print(f"[{idx}/{total_videos}] ⏭️  Skipping (exists): {title[:50]}...")
            skipped_count += 1
            continue
        
        # Show progress
        print(f"[{idx}/{total_videos}] 📄 Processing: {title[:50]}...")
        
        # Attempt to download the transcript
        transcript, status = download_transcript(video_id, languages, cookies=cookies)
        
        if transcript:
            # Success! Write the transcript to a Markdown file
            with open(filepath, 'w', encoding='utf-8') as f:
                # Write Markdown header with video info
                f.write(f"# {title}\n\n")
                f.write(f"**Video ID:** `{video_id}`\n\n")
                f.write(f"**URL:** [Watch on YouTube](https://www.youtube.com/watch?v={video_id})\n\n")
                f.write("---\n\n")
                f.write("## Transcript\n\n")
                f.write(transcript)
            
            print(f"    ✅ Saved: {filename}")
            success_count += 1
        else:
            # Failed - translate status code to human-readable message
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
            
            # If we're getting rate limited repeatedly, stop and give advice
            if status == "rate_limited":
                rate_limit_count += 1
                if rate_limit_count >= 3:
                    print("\n⚠️  Too many rate limits. Consider:")
                    print("   1. Wait 1-2 hours before trying again")
                    print("   2. Use --cookies with a cookie file from your browser")
                    print("   3. Use a VPN to change your IP address")
                    break  # Stop processing more videos
        
        # Wait before processing the next video to avoid rate limiting
        # Only wait if there are more videos to process
        if idx < total_videos:
            # Add some randomness to the delay to appear more human-like
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
    """
    Entry point for the command-line interface.
    
    Parses command-line arguments and calls download_all_transcripts().
    
    Usage examples:
        python download_transcripts.py @ChannelName
        python download_transcripts.py @ChannelName --limit 10
        python download_transcripts.py @ChannelName --cookies cookies.txt
    """
    
    # Create an argument parser with a description and examples
    parser = argparse.ArgumentParser(
        description="Download all transcripts from a YouTube channel.",
        formatter_class=argparse.RawDescriptionHelpFormatter,  # Preserve formatting
        epilog="""
Examples:
  python download_transcripts.py https://www.youtube.com/@ChannelName
  python download_transcripts.py @ChannelName -o my_transcripts
  python download_transcripts.py @ChannelName --limit 10 --delay 5
  python download_transcripts.py @ChannelName --cookies cookies.txt

To avoid rate limiting, export cookies from your browser:
  1. Install 'Get cookies.txt LOCALLY' browser extension
  2. Go to youtube.com (logged in)
  3. Export cookies to cookies.txt
  4. Use --cookies cookies.txt
        """
    )
    
    # Define command-line arguments
    
    # Required: The channel URL (positional argument, no flag needed)
    parser.add_argument(
        "channel_url",
        help="YouTube channel URL or @username"
    )
    
    # Optional: Output directory
    parser.add_argument(
        "-o", "--output",
        default="transcripts",
        help="Output directory for transcripts (default: transcripts)"
    )
    
    # Optional: Limit number of videos
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=None,
        help="Maximum number of videos to process (default: all)"
    )
    
    # Optional: Preferred languages
    parser.add_argument(
        "--languages",
        nargs="+",  # Accept multiple values: --languages en es de
        default=['en', 'en-US', 'en-GB'],
        help="Preferred transcript languages (default: en en-US en-GB)"
    )
    
    # Optional: Delay between requests
    parser.add_argument(
        "-d", "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Delay between requests in seconds (default: {DEFAULT_DELAY})"
    )
    
    # Optional: Cookie file for authentication
    parser.add_argument(
        "-c", "--cookies",
        type=str,
        default=None,
        help="Path to cookies.txt file (Netscape format) to avoid rate limiting"
    )
    
    # Parse the command-line arguments
    args = parser.parse_args()
    
    # Validate cookie file if one was provided
    cookies = None
    if args.cookies:
        cookies = validate_cookie_file(args.cookies)
    
    # Run the main download function with error handling
    try:
        download_all_transcripts(
            channel_url=args.channel_url,
            output_dir=args.output,
            limit=args.limit,
            languages=args.languages,
            delay=args.delay,
            cookies=cookies
        )
    except ValueError as e:
        # Handle invalid channel URL errors
        print(f"❌ Error: {e}")
        sys.exit(1)  # Exit with error code 1
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        print("\n\n⏹️  Cancelled by user.")
        sys.exit(0)  # Exit cleanly


# =============================================================================
# SCRIPT ENTRY POINT
# =============================================================================

# This block only runs when the script is executed directly (not imported)
# Example: python download_transcripts.py @ChannelName
if __name__ == "__main__":
    main()
