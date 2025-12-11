# YouTube Channel Transcript Downloader

A Python tool to download transcripts from all videos on a YouTube channel. Saves transcripts as Markdown files for easy reading and searching.

## Features

- 📺 **Download all transcripts** from any YouTube channel
- 📝 **Markdown output** with video title, URL, and clean transcript text
- 🎯 **Prioritizes manual transcripts** over auto-generated ones
- 🍪 **Cookie support** to bypass rate limiting
- ⏱️ **Rate limiting protection** with automatic retries
- 📁 **Skip existing files** - resume interrupted downloads

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/youtube_transcript_downloader.git
cd youtube_transcript_downloader

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
# Download all transcripts from a channel
python download_transcripts.py https://www.youtube.com/@ChannelName

# Or use the short @username format
python download_transcripts.py @ChannelName
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `-o, --output` | Output directory | `transcripts` |
| `-l, --limit` | Max videos to process | All |
| `-d, --delay` | Delay between requests (seconds) | `3` |
| `-c, --cookies` | Path to cookies.txt file | None |
| `--languages` | Preferred transcript languages | `en en-US en-GB` |

### Examples

```bash
# Save to custom folder
python download_transcripts.py @ChannelName -o my_transcripts

# Download only the 10 most recent videos
python download_transcripts.py @ChannelName --limit 10

# Use longer delay to avoid rate limiting
python download_transcripts.py @ChannelName --delay 5

# Use cookies for authenticated access
python download_transcripts.py @ChannelName --cookies cookies.txt

# Download Spanish transcripts
python download_transcripts.py @ChannelName --languages es es-ES
```

## Avoiding Rate Limiting

YouTube may rate limit requests. If you see "429 Too Many Requests" errors:

### Option 1: Use Cookies (Recommended)

1. Install browser extension: [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
2. Go to youtube.com while logged in
3. Export cookies in **Netscape format** as `cookies.txt`
4. Run with cookies:
   ```bash
   python download_transcripts.py @ChannelName --cookies cookies.txt
   ```

### Option 2: Increase Delay

```bash
python download_transcripts.py @ChannelName --delay 10
```

### Option 3: Wait and Retry

Wait 1-2 hours before trying again if heavily rate limited.

## Output Format

Transcripts are saved as Markdown files (`Title_VideoID.md`):

```markdown
# Video Title

**Video ID:** `abc123xyz`

**URL:** [Watch on YouTube](https://www.youtube.com/watch?v=abc123xyz)

---

## Transcript

This is the transcript content as continuous flowing text...
```

## Supported URL Formats

- `https://www.youtube.com/@ChannelName`
- `https://www.youtube.com/channel/UCxxxxxx`
- `https://www.youtube.com/c/CustomName`
- `https://www.youtube.com/user/Username`
- `@ChannelName` (shorthand)

## Requirements

- Python 3.10+
- youtube-transcript-api
- scrapetube

## License

MIT License
