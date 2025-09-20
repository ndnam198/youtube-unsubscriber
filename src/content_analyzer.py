"""
Content Type Analyzer for YouTube Channels

This module analyzes YouTube channels to determine if they primarily offer
short-form or long-form content by examining video durations.
"""

import re
import time
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime

from googleapiclient.errors import HttpError

from src.quota_tracker import QuotaTracker


class ProgressTracker:
    """Tracks and displays progress for content analysis operations."""

    def __init__(self):
        self.start_time = None
        self.current_step = ""
        self.step_start_time = None

    def start_analysis(self):
        """Start tracking overall analysis progress."""
        self.start_time = time.time()
        print(f"🚀 Starting content analysis at {datetime.now().strftime('%H:%M:%S')}")

    def start_step(self, step_name: str):
        """Start tracking a specific step."""
        if self.step_start_time:
            elapsed = time.time() - self.step_start_time
            print(f"  ✅ Completed in {elapsed:.1f}s")

        self.current_step = step_name
        self.step_start_time = time.time()
        print(f"📋 {step_name}...")

    def update_progress(self, current: int, total: int, item_type: str = "items"):
        """Update progress for current step."""
        if total == 0:
            return

        percentage = (current / total) * 100
        elapsed = time.time() - self.step_start_time if self.step_start_time else 0

        # Estimate remaining time
        if current > 0 and elapsed > 0:
            rate = current / elapsed
            remaining = (total - current) / rate if rate > 0 else 0
            eta = f" (ETA: {remaining:.0f}s)" if remaining > 0 else ""
        else:
            eta = ""

        print(
            f"  📊 {current:,}/{total:,} {item_type} ({percentage:.1f}%){eta}", end="\r"
        )

    def complete_step(self, result_count: Optional[int] = None):
        """Complete current step."""
        if self.step_start_time:
            elapsed = time.time() - self.step_start_time
            if result_count is not None:
                print(f"  ✅ Found {result_count:,} items in {elapsed:.1f}s")
            else:
                print(f"  ✅ Completed in {elapsed:.1f}s")

    def complete_analysis(self):
        """Complete overall analysis."""
        if self.start_time:
            total_elapsed = time.time() - self.start_time
            print(f"🎉 Analysis completed in {total_elapsed:.1f}s")


@dataclass
class ContentAnalysisResult:
    """Result of content type analysis for a channel."""

    channel_id: str
    total_videos: int
    shorts_count: int
    longs_count: int
    shorts_percentage: float
    content_type: str  # 'SHORTS', 'LONGS', or 'MIXED'
    analysis_date: str


class ContentAnalyzer:
    """Analyzes YouTube channel content to determine short vs long-form content ratio."""

    def __init__(
        self, quota_tracker: Optional[QuotaTracker] = None, youtube_service=None
    ):
        """Initialize the content analyzer."""
        self.youtube = (
            youtube_service  # Will be set by caller using authenticated service
        )
        self.quota_tracker = quota_tracker
        self.SHORTS_THRESHOLD = 60  # seconds - YouTube Shorts are 60s or less
        self.progress = ProgressTracker()

    def parse_duration(self, duration_str: str) -> int:
        """
        Parse ISO 8601 duration string to total seconds.

        Args:
            duration_str: ISO 8601 duration (e.g., 'PT1M30S', 'PT45S', 'PT2H15M30S')

        Returns:
            Total duration in seconds
        """
        if not duration_str or not duration_str.startswith("PT"):
            return 0

        # Remove 'PT' prefix
        duration = duration_str[2:]

        # Parse hours, minutes, seconds
        hours = 0
        minutes = 0
        seconds = 0

        # Extract hours
        if "H" in duration:
            hours_match = re.search(r"(\d+)H", duration)
            if hours_match:
                hours = int(hours_match.group(1))

        # Extract minutes
        if "M" in duration:
            minutes_match = re.search(r"(\d+)M", duration)
            if minutes_match:
                minutes = int(minutes_match.group(1))

        # Extract seconds
        if "S" in duration:
            seconds_match = re.search(r"(\d+)S", duration)
            if seconds_match:
                seconds = int(seconds_match.group(1))

        return hours * 3600 + minutes * 60 + seconds

    def get_uploads_playlist_id(self, channel_id: str) -> Optional[str]:
        """
        Get the uploads playlist ID for a channel.

        Args:
            channel_id: YouTube channel ID

        Returns:
            Uploads playlist ID or None if not found
        """
        try:
            print(f"  🔍 Fetching channel details...", end=" ")
            request = self.youtube.channels().list(part="contentDetails", id=channel_id)
            response = request.execute()

            if self.quota_tracker:
                self.quota_tracker.record_api_call("channels.list", 1)

            if "items" in response and response["items"]:
                uploads_playlist_id = response["items"][0]["contentDetails"][
                    "relatedPlaylists"
                ]["uploads"]
                print("✅ Found")
                return uploads_playlist_id
            else:
                print("❌ No channel found")
                return None

        except HttpError as e:
            print(f"❌ Error: {e}")
            return None

    def get_all_video_ids(self, playlist_id: str) -> List[str]:
        """
        Get all video IDs from a playlist with pagination.

        Args:
            playlist_id: YouTube playlist ID

        Returns:
            List of video IDs
        """
        video_ids = []
        next_page_token = None
        page_count = 0
        max_pages = 200  # Safety limit to prevent infinite loops

        while page_count < max_pages:
            try:
                page_count += 1
                print(f"  📄 Fetching page {page_count}...", end=" ")

                request = self.youtube.playlistItems().list(
                    part="contentDetails",
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=next_page_token,
                )
                response = request.execute()

                if self.quota_tracker:
                    self.quota_tracker.record_api_call("playlistItems.list", 1)

                # Extract video IDs
                page_video_count = 0
                for item in response.get("items", []):
                    video_id = item["contentDetails"]["videoId"]
                    video_ids.append(video_id)
                    page_video_count += 1

                print(f"found {page_video_count} videos (total: {len(video_ids):,})")

                # Check for next page
                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    print(f"  ✅ Reached end of playlist")
                    break

                # Small delay to avoid rate limiting
                time.sleep(0.2)

            except HttpError as e:
                print(f"  ❌ Error fetching playlist items: {e}")
                break
            except Exception as e:
                print(f"  ❌ Unexpected error: {e}")
                break

        if page_count >= max_pages:
            print(f"  ⚠️  Reached maximum page limit ({max_pages}), stopping")

        return video_ids

    def get_video_durations(
        self, video_ids: List[str], batch_num: int = 0, total_batches: int = 0
    ) -> List[int]:
        """
        Get durations for a batch of videos.

        Args:
            video_ids: List of video IDs (max 50)
            batch_num: Current batch number for progress display
            total_batches: Total number of batches for progress display

        Returns:
            List of durations in seconds
        """
        if not video_ids:
            return []

        try:
            # Join video IDs with commas
            video_ids_str = ",".join(video_ids)

            if batch_num > 0 and total_batches > 0:
                print(
                    f"  🔄 Processing batch {batch_num}/{total_batches} ({len(video_ids)} videos)...",
                    end=" ",
                )

            request = self.youtube.videos().list(
                part="contentDetails", id=video_ids_str
            )
            response = request.execute()

            if self.quota_tracker:
                self.quota_tracker.record_api_call("videos.list", 1)

            durations = []
            missing_duration_count = 0
            for item in response.get("items", []):
                try:
                    duration_str = item["contentDetails"]["duration"]
                    duration_seconds = self.parse_duration(duration_str)
                    durations.append(duration_seconds)
                except KeyError:
                    # Some videos might not have duration (e.g., live streams, premieres)
                    missing_duration_count += 1
                    durations.append(0)  # Treat as 0 seconds

            if batch_num > 0 and total_batches > 0:
                if missing_duration_count > 0:
                    print(
                        f"✅ {len(durations)} durations ({missing_duration_count} missing)"
                    )
                else:
                    print(f"✅ {len(durations)} durations")
            elif missing_duration_count > 0:
                print(f"  ⚠️  {missing_duration_count} videos have no duration")

            return durations

        except HttpError as e:
            if batch_num > 0 and total_batches > 0:
                print(f"❌ Error: {e}")
            else:
                print(f"Error fetching video durations: {e}")
            return []

    def analyze_channel_content(
        self, channel_id: str
    ) -> Optional[ContentAnalysisResult]:
        """
        Analyze a channel's content to determine short vs long-form ratio.

        Args:
            channel_id: YouTube channel ID

        Returns:
            ContentAnalysisResult or None if analysis failed
        """
        # Initialize progress tracking
        self.progress = ProgressTracker()
        self.progress.start_analysis()

        print(f"🎯 Analyzing channel: {channel_id}")

        # Step 1: Get uploads playlist ID
        self.progress.start_step("Getting uploads playlist ID")
        uploads_playlist_id = self.get_uploads_playlist_id(channel_id)
        if not uploads_playlist_id:
            print("  ❌ Failed to get uploads playlist ID")
            return None

        self.progress.complete_step()
        print(f"  📋 Uploads playlist ID: {uploads_playlist_id}")

        # Step 2: Get all video IDs
        self.progress.start_step("Fetching all video IDs")
        video_ids = self.get_all_video_ids(uploads_playlist_id)
        self.progress.complete_step(len(video_ids))

        if not video_ids:
            print("  ❌ No videos found in uploads playlist")
            return None

        # Step 3: Get durations in batches
        self.progress.start_step("Fetching video durations")
        all_durations = []
        batch_size = 50
        total_batches = (len(video_ids) + batch_size - 1) // batch_size

        print(
            f"  📊 Processing {len(video_ids):,} videos in {total_batches} batches..."
        )

        for i in range(0, len(video_ids), batch_size):
            batch = video_ids[i : i + batch_size]
            batch_num = i // batch_size + 1

            durations = self.get_video_durations(batch, batch_num, total_batches)
            all_durations.extend(durations)

            # Small delay to avoid rate limiting
            time.sleep(0.1)

        self.progress.complete_step(len(all_durations))

        # Step 4: Analyze durations
        self.progress.start_step("Analyzing content types")
        shorts_count = 0
        longs_count = 0

        for duration in all_durations:
            if duration <= self.SHORTS_THRESHOLD:
                shorts_count += 1
            else:
                longs_count += 1

        total_videos = len(all_durations)
        shorts_percentage = (
            (shorts_count / total_videos * 100) if total_videos > 0 else 0
        )

        # Determine content type
        if total_videos == 0:
            content_type = "UNKNOWN"
        elif shorts_percentage >= 70:
            content_type = "SHORTS"
        elif shorts_percentage <= 30:
            content_type = "LONGS"
        else:
            content_type = "MIXED"

        result = ContentAnalysisResult(
            channel_id=channel_id,
            total_videos=total_videos,
            shorts_count=shorts_count,
            longs_count=longs_count,
            shorts_percentage=shorts_percentage,
            content_type=content_type,
            analysis_date=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        self.progress.complete_step()

        # Display results
        print(f"\n📊 Analysis Results:")
        print(f"  📺 Total videos: {result.total_videos:,}")
        print(
            f"  🎬 Shorts (≤{self.SHORTS_THRESHOLD}s): {result.shorts_count:,} ({result.shorts_percentage:.1f}%)"
        )
        print(
            f"  📺 Longs (>{self.SHORTS_THRESHOLD}s): {result.longs_count:,} ({100-result.shorts_percentage:.1f}%)"
        )
        print(f"  🏷️  Content type: {result.content_type}")

        self.progress.complete_analysis()
        return result


def test_content_analyzer():
    """Test the content analyzer on a single channel."""
    from src.quota_tracker import QuotaTracker
    from src.youtube_api import authenticate_youtube

    # Authenticate with YouTube
    print("Authenticating with YouTube API...")
    youtube = authenticate_youtube()
    if not youtube:
        print("❌ Failed to authenticate with YouTube API")
        return

    print("✅ Successfully authenticated with YouTube API")

    # Initialize quota tracker
    quota_tracker = QuotaTracker()

    # Initialize analyzer with authenticated service
    analyzer = ContentAnalyzer(quota_tracker, youtube)

    # Test with a known channel (3Blue1Brown as mentioned in instructions)
    test_channel_id = "UCYO_jab_esuFRV4b17AJtAw"  # 3Blue1Brown

    print("=" * 60)
    print("TESTING CONTENT ANALYZER")
    print("=" * 60)
    print(f"Testing channel: {test_channel_id}")
    print()

    # Analyze the channel
    result = analyzer.analyze_channel_content(test_channel_id)

    if result:
        print("\n" + "=" * 60)
        print("ANALYSIS RESULT")
        print("=" * 60)
        print(f"Channel ID: {result.channel_id}")
        print(f"Total Videos: {result.total_videos}")
        print(f"Shorts Count: {result.shorts_count} ({result.shorts_percentage:.1f}%)")
        print(
            f"Longs Count: {result.longs_count} ({100-result.shorts_percentage:.1f}%)"
        )
        print(f"Content Type: {result.content_type}")
        print(f"Analysis Date: {result.analysis_date}")

        # Show quota usage
        print(f"\nQuota Usage:")
        quota_status = quota_tracker.get_quota_status()
        print(f"  Remaining: {quota_status['remaining']}")
        print(f"  Used: {quota_status['used']}")
        print(f"  Warning Level: {quota_tracker.get_quota_warning_level()}")
    else:
        print("Analysis failed!")


if __name__ == "__main__":
    test_content_analyzer()
