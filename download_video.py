#!/usr/bin/env python3
"""
Video downloader script for Brownstone Research pages.

This script attempts to download videos from web pages using multiple methods.
Since many modern sites (including Brownstone Research) use JavaScript-heavy
single-page applications, direct extraction may not always work.

Usage:
    python download_video.py                    # Use default Brownstone URL
    python download_video.py <webpage_url>      # Extract from any webpage
    python download_video.py <video_url>        # Download video directly

If automatic extraction fails, follow the manual steps printed by the script
to extract the video URL from your browser's developer tools.
"""

import subprocess
import sys
import os
import re
from urllib.parse import urljoin, urlparse


def install_package(package):
    """Install a package if not already installed."""
    try:
        __import__(package.replace("-", "_").split()[0])
    except ImportError:
        print(f"Installing {package}...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            capture_output=True
        )


def ensure_dependencies():
    """Ensure all required dependencies are installed."""
    packages = ["requests", "beautifulsoup4", "yt-dlp"]
    for pkg in packages:
        install_package(pkg)


def is_direct_video_url(url):
    """Check if URL is a direct video file or known video service."""
    video_extensions = [".mp4", ".webm", ".m3u8", ".mov", ".avi", ".mkv", ".flv"]
    video_services = [
        "wistia.com", "wistia.net", "vimeo.com", "youtube.com", "youtu.be",
        "vidyard.com", "brightcove", "jwplatform", "loom.com", "sproutvideo"
    ]

    url_lower = url.lower()
    if any(ext in url_lower for ext in video_extensions):
        return True
    if any(service in url_lower for service in video_services):
        return True
    return False


def fetch_page(url):
    """Fetch a page with browser-like headers."""
    import requests

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def extract_video_urls(html, base_url):
    """Extract video URLs from HTML content using multiple detection methods."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    video_urls = []

    # Method 1: Direct video elements
    for video in soup.find_all("video"):
        src = video.get("src")
        if src:
            video_urls.append(("video_element", urljoin(base_url, src)))
        for source in video.find_all("source"):
            src = source.get("src")
            if src:
                video_urls.append(("video_source", urljoin(base_url, src)))

    # Method 2: Iframe embeds for known video hosts
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src") or iframe.get("data-src")
        if src:
            video_hosts = ["vimeo", "youtube", "wistia", "vidyard", "brightcove", "loom"]
            if any(host in src.lower() for host in video_hosts):
                video_urls.append(("iframe_embed", src))

    # Method 3: Wistia embeds (common on marketing pages)
    wistia_patterns = [
        r'wistia_async_([a-zA-Z0-9]+)',
        r'//fast\.wistia\.(?:com|net)/embed/(?:iframe|medias)/([a-zA-Z0-9]+)',
        r'"hashedId"\s*:\s*"([a-zA-Z0-9]+)"',
    ]
    for pattern in wistia_patterns:
        for vid_id in set(re.findall(pattern, html)):
            video_urls.append(("wistia", f"https://fast.wistia.net/embed/iframe/{vid_id}"))

    # Method 4: Vimeo embeds
    vimeo_patterns = [r'player\.vimeo\.com/video/(\d+)', r'vimeo\.com/(\d+)']
    for pattern in vimeo_patterns:
        for vid_id in set(re.findall(pattern, html)):
            video_urls.append(("vimeo", f"https://player.vimeo.com/video/{vid_id}"))

    # Method 5: YouTube embeds
    youtube_patterns = [
        r'youtube\.com/embed/([a-zA-Z0-9_-]+)',
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]+)',
        r'youtu\.be/([a-zA-Z0-9_-]+)',
    ]
    for pattern in youtube_patterns:
        for vid_id in set(re.findall(pattern, html)):
            video_urls.append(("youtube", f"https://www.youtube.com/watch?v={vid_id}"))

    # Method 6: Direct video file URLs in HTML/JS
    video_file_matches = re.findall(
        r'(https?://[^\s"\'<>]+\.(?:mp4|m3u8|webm)(?:\?[^\s"\'<>]*)?)',
        html,
        re.IGNORECASE
    )
    for url in set(video_file_matches):
        url = url.replace("\\u002F", "/").replace("\\/", "/")
        video_urls.append(("direct_file", url))

    # Deduplicate
    seen = set()
    unique_urls = []
    for source_type, url in video_urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append((source_type, url))

    return unique_urls


def download_with_yt_dlp(video_url, output_dir, verbose=False):
    """Download video using yt-dlp."""
    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        "yt-dlp",
        "--no-check-certificate",
        "--no-playlist",
        "-o", os.path.join(output_dir, "%(title)s.%(ext)s"),
    ]

    if verbose:
        cmd.append("--verbose")

    cmd.append(video_url)

    print(f"  Attempting: {video_url[:70]}...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print("  SUCCESS!")
        # Show destination file
        for line in result.stdout.split("\n"):
            if "Destination:" in line or "Merging" in line:
                print(f"  {line.strip()}")
            elif "has already been downloaded" in line:
                print(f"  {line.strip()}")
        return True
    return False


def download_direct(video_url, output_dir):
    """Download video directly using requests."""
    import requests

    os.makedirs(output_dir, exist_ok=True)

    parsed = urlparse(video_url)
    filename = os.path.basename(parsed.path)
    if not filename or "." not in filename:
        filename = "video.mp4"

    output_path = os.path.join(output_dir, filename)

    print(f"  Direct download to: {output_path}")

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(video_url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()

        total = int(response.headers.get("content-length", 0))
        downloaded = 0

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = (downloaded / total) * 100
                    mb = downloaded / (1024 * 1024)
                    print(f"\r  Progress: {pct:.1f}% ({mb:.1f} MB)", end="", flush=True)

        print(f"\n  SUCCESS: {output_path}")
        return True
    except Exception as e:
        print(f"\n  Failed: {e}")
        return False


def print_manual_instructions(page_url):
    """Print instructions for manual video extraction."""
    print("""
============================================================
MANUAL VIDEO EXTRACTION INSTRUCTIONS
============================================================

The webpage uses JavaScript to load video content, which requires
a browser to extract. Follow these steps:

1. OPEN THE PAGE
   Open this URL in Chrome or Firefox:
   """ + page_url[:80] + """...

2. OPEN DEVELOPER TOOLS
   - Press F12 (or Ctrl+Shift+I / Cmd+Option+I on Mac)
   - Click on the "Network" tab

3. FILTER FOR VIDEO
   - In the filter box, type: mp4 OR m3u8 OR video
   - Or click "Media" filter if available

4. PLAY THE VIDEO
   - Click play on the video player
   - Watch the Network tab for new requests

5. FIND THE VIDEO URL
   - Look for requests to .mp4, .m3u8, or video domains
   - Common video hosts: wistia, vimeo, youtube, brightcove
   - Right-click the request → "Copy" → "Copy URL"

6. DOWNLOAD THE VIDEO
   Run this command with the copied URL:

   python download_video.py "PASTE_VIDEO_URL_HERE"

   Or use yt-dlp directly:

   yt-dlp "PASTE_VIDEO_URL_HERE" -P ./downloads

============================================================
""")


def download_video(url, output_dir="./downloads"):
    """
    Main function to download video from a webpage or direct URL.
    """
    ensure_dependencies()

    print("=" * 60)
    print("BROWNSTONE VIDEO DOWNLOADER")
    print("=" * 60)
    print(f"URL: {url[:70]}...")
    print(f"Output: {output_dir}/")
    print("=" * 60)

    # Check if this is already a direct video URL
    if is_direct_video_url(url):
        print("\n[Direct Video URL Detected]")
        if download_with_yt_dlp(url, output_dir, verbose=True):
            return True
        if any(ext in url.lower() for ext in [".mp4", ".webm", ".mov"]):
            if download_direct(url, output_dir):
                return True
        print("\nFailed to download video.")
        return False

    # Try yt-dlp on the page URL first
    print("\n[1/3] Trying yt-dlp extraction...")
    if download_with_yt_dlp(url, output_dir):
        return True
    print("  yt-dlp could not extract video from page")

    # Fetch and parse the page
    print("\n[2/3] Fetching page content...")
    try:
        html = fetch_page(url)
        print(f"  Fetched {len(html):,} bytes")
    except Exception as e:
        print(f"  Error: {e}")
        print_manual_instructions(url)
        return False

    # Check if it's a JavaScript SPA (minimal HTML content)
    if len(html) < 5000 and "<script" in html:
        print("  Page appears to be a JavaScript single-page application")
        print("  Video content is loaded dynamically via JavaScript")

    # Extract video URLs
    print("\n[3/3] Searching for video URLs in HTML...")
    video_urls = extract_video_urls(html, url)

    if video_urls:
        print(f"  Found {len(video_urls)} potential source(s)")
        for source_type, vid_url in video_urls:
            print(f"\n  Trying [{source_type}]: {vid_url[:60]}...")
            if download_with_yt_dlp(vid_url, output_dir):
                print("\n" + "=" * 60)
                print("VIDEO DOWNLOADED SUCCESSFULLY!")
                print("=" * 60)
                return True
            if ".mp4" in vid_url.lower() or ".webm" in vid_url.lower():
                if download_direct(vid_url, output_dir):
                    print("\n" + "=" * 60)
                    print("VIDEO DOWNLOADED SUCCESSFULLY!")
                    print("=" * 60)
                    return True

    # If all methods failed, print manual instructions
    print_manual_instructions(url)
    return False


if __name__ == "__main__":
    # Default Brownstone Research URL
    DEFAULT_URL = (
        "https://secure.brownstoneresearch.com/"
        "?cid=MKT859575"
        "&eid=MKT859927"
        "&encryptedSnaid=MWYxZGFhYjQyNGQxY2JhMRo9cEfps5Yycq6FQgdqk9o%3D"
        "&step=start"
        "&emailjobid=5668545"
        "&emailname=260128-Hotlist-BES-Biotech-Encore-9PM-Ded"
        "&assetId=AST387211"
        "&page=1"
    )

    # Use command line argument if provided
    target_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    output_directory = "./downloads"

    success = download_video(target_url, output_directory)
    sys.exit(0 if success else 1)
