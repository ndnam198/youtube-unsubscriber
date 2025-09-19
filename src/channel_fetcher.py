"""
Channel metadata fetching and management.
"""

import logging
from typing import List, Dict, Optional, Tuple
from googleapiclient.errors import HttpError

logger = logging.getLogger("youtube-unsubscriber")


def fetch_channel_metadata(
    youtube, channel_ids: List[str], quota_tracker=None
) -> List[Dict]:
    """
    Fetch detailed metadata for a list of channel IDs.

    Args:
        youtube: Authenticated YouTube API service
        channel_ids: List of YouTube channel IDs
        quota_tracker: Optional quota tracker instance

    Returns:
        List of channel metadata dictionaries
    """
    if not channel_ids:
        return []

    logger.info(f"Fetching metadata for {len(channel_ids)} channels...")

    # YouTube API allows up to 50 channel IDs per request
    batch_size = 50
    all_channels = []

    for i in range(0, len(channel_ids), batch_size):
        batch_ids = channel_ids[i : i + batch_size]

        try:
            # Record quota usage
            if quota_tracker:
                quota_tracker.record_api_call("channels.list", 1)

            # Fetch channel details
            request = youtube.channels().list(
                part="snippet,statistics,contentDetails,topicDetails",
                id=",".join(batch_ids),
            )
            response = request.execute()

            channels = response.get("items", [])
            all_channels.extend(channels)

            logger.info(
                f"Fetched metadata for {len(channels)} channels in batch {i//batch_size + 1}"
            )

        except HttpError as e:
            logger.error(f"Error fetching channel metadata for batch: {e}")
            continue

    return all_channels


def process_channel_data(channel_data: Dict) -> Dict:
    """
    Process raw channel data from YouTube API into our database format.

    Args:
        channel_data: Raw channel data from YouTube API

    Returns:
        Processed channel data for database insertion
    """
    channel_id = channel_data["id"]
    snippet = channel_data.get("snippet", {})
    statistics = channel_data.get("statistics", {})
    topic_details = channel_data.get("topicDetails", {})

    # Extract thumbnail URL (prefer high quality)
    thumbnails = snippet.get("thumbnails", {})
    thumbnail_url = None
    if "high" in thumbnails:
        thumbnail_url = thumbnails["high"].get("url")
    elif "medium" in thumbnails:
        thumbnail_url = thumbnails["medium"].get("url")
    elif "default" in thumbnails:
        thumbnail_url = thumbnails["default"].get("url")

    # Process topic IDs
    topic_ids = topic_details.get("topicIds", [])

    # Convert string numbers to integers for counts
    subscriber_count = _safe_int(statistics.get("subscriberCount"))
    video_count = _safe_int(statistics.get("videoCount"))
    view_count = _safe_int(statistics.get("viewCount"))

    processed_data = {
        "youtube_channel_id": channel_id,
        "channel_title": snippet.get("title", ""),
        "description": snippet.get("description", ""),
        "subscriber_count": subscriber_count,
        "video_count": video_count,
        "view_count": view_count,
        "country": snippet.get("country"),
        "custom_url": snippet.get("customUrl"),
        "published_at": snippet.get("publishedAt"),
        "thumbnail_url": thumbnail_url,
        "topic_ids": topic_ids,
    }

    return processed_data


def _safe_int(value: Optional[str]) -> Optional[int]:
    """Safely convert string to integer, returning None for invalid values."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def get_topic_categories() -> Dict[str, str]:
    """
    Get a mapping of YouTube topic IDs to human-readable categories.
    This is a subset of common topics - YouTube has many more.
    """
    return {
        # Entertainment
        "/m/02jjt": "Entertainment",
        "/m/09x0r": "Comedy",
        "/m/02vxn": "Music",
        "/m/01k8wb": "Movies",
        "/m/02jjt": "TV Shows",
        # Education
        "/m/01k8wb": "Education",
        "/m/02jjt": "Science",
        "/m/01k8wb": "Technology",
        "/m/02jjt": "Howto & Style",
        # Gaming
        "/m/0bzvm2": "Gaming",
        "/m/06ntj": "Video Games",
        # Lifestyle
        "/m/019_rr": "Food",
        "/m/01k8wb": "Cooking",
        "/m/02jjt": "Travel",
        "/m/01k8wb": "Fashion",
        "/m/02jjt": "Beauty",
        # News & Politics
        "/m/05qt0": "News",
        "/m/02jjt": "Politics",
        # Sports
        "/m/06ntj": "Sports",
        "/m/01k8wb": "Fitness",
        # Other
        "/m/02jjt": "People & Blogs",
        "/m/01k8wb": "Autos & Vehicles",
        "/m/02jjt": "Pets & Animals",
        "/m/01k8wb": "Nonprofits & Activism",
    }


def categorize_channel_topics(topic_ids: List[str]) -> List[str]:
    """
    Convert YouTube topic IDs to human-readable categories.

    Args:
        topic_ids: List of YouTube topic IDs

    Returns:
        List of human-readable category names
    """
    topic_categories = get_topic_categories()
    categories = []

    for topic_id in topic_ids:
        if topic_id in topic_categories:
            category = topic_categories[topic_id]
            if category not in categories:  # Avoid duplicates
                categories.append(category)

    return categories
