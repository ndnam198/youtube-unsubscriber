"""
Database operations for YouTube Subscription Manager.
"""

import logging
from typing import Dict, List, Optional

import psycopg2
from rich.console import Console
from rich.panel import Panel

from src.config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT

logger = logging.getLogger("youtube-unsubscriber")
console = Console()


def connect_db():
    """Connect to the PostgreSQL database and return the connection object."""
    try:
        logger.info("Connecting to PostgreSQL database...")
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
        )
        logger.info("✅ Successfully connected to the database.")
        return conn
    except psycopg2.OperationalError as e:
        error_panel = Panel(
            f"[red]❌ Database Connection Failed[/red]\n\n"
            f"[yellow]Error:[/yellow] {e}\n\n"
            f"[blue]Please ensure:[/blue]\n"
            f"• PostgreSQL is running\n"
            f"• Database '{DB_NAME}' exists\n"
            f"• User '{DB_USER}' has proper permissions\n"
            f"• Connection details in .env are correct\n\n"
            f"[dim]Run: docker run --name youtube-postgres -e POSTGRES_PASSWORD=password -e POSTGRES_DB=youtube_subscriptions -p 5432:5432 -d postgres:15[/dim]",
            title="[bold red]Database Error[/bold red]",
            border_style="red",
        )
        console.print(error_panel)
        logger.error("Database connection failed. Exiting program.")
        raise


def is_db_empty(conn):
    """Checks if the subscriptions table in the database is empty."""
    if not conn:
        return True  # Assume empty if no DB connection
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM subscriptions;")
        count = cur.fetchone()[0]
        return count == 0


def insert_subscriptions_to_db(conn, subscriptions, quota_tracker=None):
    """Inserts or updates a list of subscriptions into the database."""
    if not conn:
        logger.warning(
            "Database connection not available. Skipping database insertion."
        )
        return

    logger.info(f"Inserting {len(subscriptions)} subscriptions into the database...")

    # Record quota usage for fetching subscriptions
    if quota_tracker:
        quota_tracker.record_api_call("subscriptions.list", 1)

    with conn.cursor() as cur:
        for sub in subscriptions:
            snippet = sub["snippet"]
            channel_id = snippet["resourceId"]["channelId"]
            subscription_id = sub["id"]
            channel_title = snippet["title"]
            published_at = snippet["publishedAt"]
            channel_link = f"https://www.youtube.com/channel/{channel_id}"

            # First, ensure the channel exists in the channels table (create placeholder if needed)
            cur.execute(
                """
                INSERT INTO channels (youtube_channel_id, channel_title, description, subscriber_count, video_count, view_count, country, custom_url, published_at, thumbnail_url, topic_ids, content_type, shorts_count, longs_count, shorts_percentage, content_analysis_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (youtube_channel_id) DO UPDATE SET
                    channel_title = EXCLUDED.channel_title;
                """,
                (
                    channel_id,
                    channel_title,
                    "No description available",  # placeholder description
                    None,  # subscriber_count - will be fetched later
                    None,  # video_count - will be fetched later
                    None,  # view_count - will be fetched later
                    None,  # country
                    None,  # custom_url
                    published_at,
                    None,  # thumbnail_url
                    None,  # topic_ids
                    "UNKNOWN",  # content_type - will be analyzed later
                    0,  # shorts_count
                    0,  # longs_count
                    0.0,  # shorts_percentage
                    None,  # content_analysis_date
                ),
            )

            # Then insert/update the subscription
            cur.execute(
                """
                INSERT INTO subscriptions (youtube_channel_id, youtube_subscription_id, channel_name, channel_link, subscription_date, status)
                VALUES (%s, %s, %s, %s, %s, 'SUBSCRIBED')
                ON CONFLICT (youtube_channel_id) DO UPDATE SET
                    channel_name = EXCLUDED.channel_name,
                    subscription_date = EXCLUDED.subscription_date,
                    status = 'SUBSCRIBED';
                """,
                (
                    channel_id,
                    subscription_id,
                    channel_title,
                    channel_link,
                    published_at,
                ),
            )
    conn.commit()
    logger.info("Database insertion complete.")


def get_subscription_stats(conn):
    """Gets subscription statistics from the database."""
    if not conn:
        return None

    with conn.cursor() as cur:
        # Get total count
        cur.execute("SELECT COUNT(*) FROM subscriptions;")
        total = cur.fetchone()[0]

        # Get count by status
        cur.execute(
            "SELECT status, COUNT(*) FROM subscriptions GROUP BY status ORDER BY status;"
        )
        status_counts = dict(cur.fetchall())

        return {"total": total, "by_status": status_counts}


def print_all_channels_from_db(conn):
    """Fetches and prints all channels from the database."""
    if not conn:
        logger.warning("Database connection not available.")
        return
    logger.info("--- Subscriptions from Database ---")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT channel_name, status, subscription_date FROM subscriptions ORDER BY channel_name;"
        )
        records = cur.fetchall()
        if not records:
            logger.info("No subscriptions found in the database.")
            return

        for record in records:
            name, status, date = record
            logger.info(
                f"- {name:<50} Status: {status:<20} Subscribed On: {date.strftime('%Y-%m-%d')}"
            )
    logger.info("-" * 33)


def get_channels_to_unsubscribe_from_db(conn):
    """Fetches channels marked 'TO_BE_UNSUBSCRIBED' from the database."""
    if not conn:
        logger.warning("Database connection not available.")
        return []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT youtube_subscription_id, channel_name FROM subscriptions WHERE status = 'TO_BE_UNSUBSCRIBED';"
        )
        channels = cur.fetchall()
        # Returning as a list of dicts to match the old format for unsubscribe_from_channels
        return [{"id": ch[0], "title": ch[1]} for ch in channels]


def update_subscription_status_in_db(conn, subscription_id, new_status):
    """Updates the status of a specific subscription in the database."""
    if not conn:
        return
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE subscriptions SET status = %s WHERE youtube_subscription_id = %s;",
            (new_status, subscription_id),
        )
    conn.commit()


def insert_channel_metadata(conn, channel_data, quota_tracker=None):
    """Inserts or updates channel metadata in the channels table."""
    if not conn:
        logger.warning(
            "Database connection not available. Skipping channel metadata insertion."
        )
        return

    logger.info(
        f"Inserting/updating channel metadata for {channel_data['youtube_channel_id']}..."
    )

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO channels (
                youtube_channel_id, channel_title, description, subscriber_count,
                video_count, view_count, country, custom_url, published_at,
                thumbnail_url, topic_ids, last_updated
            ) VALUES (
                %(youtube_channel_id)s, %(channel_title)s, %(description)s, %(subscriber_count)s,
                %(video_count)s, %(view_count)s, %(country)s, %(custom_url)s, %(published_at)s,
                %(thumbnail_url)s, %(topic_ids)s, CURRENT_TIMESTAMP
            )
            ON CONFLICT (youtube_channel_id) DO UPDATE SET
                channel_title = EXCLUDED.channel_title,
                description = EXCLUDED.description,
                subscriber_count = EXCLUDED.subscriber_count,
                video_count = EXCLUDED.video_count,
                view_count = EXCLUDED.view_count,
                country = EXCLUDED.country,
                custom_url = EXCLUDED.custom_url,
                published_at = EXCLUDED.published_at,
                thumbnail_url = EXCLUDED.thumbnail_url,
                topic_ids = EXCLUDED.topic_ids,
                last_updated = CURRENT_TIMESTAMP;
            """,
            channel_data,
        )
    conn.commit()
    logger.info("Channel metadata insertion/update complete.")


def get_channels_without_metadata(conn) -> List[str]:
    """Get channel IDs that don't have metadata in the channels table."""
    if not conn:
        return []

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.youtube_channel_id 
            FROM subscriptions s 
            LEFT JOIN channels c ON s.youtube_channel_id = c.youtube_channel_id 
            WHERE c.youtube_channel_id IS NULL 
            OR c.subscriber_count IS NULL 
            OR c.video_count IS NULL;
        """
        )
        results = cur.fetchall()
        return [row[0] for row in results]


def get_channel_metadata(conn, channel_id: str) -> Optional[Dict]:
    """Get metadata for a specific channel."""
    if not conn:
        return None

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT youtube_channel_id, channel_title, description, subscriber_count,
                   video_count, view_count, country, custom_url, published_at,
                   thumbnail_url, topic_ids, last_updated, created_at
            FROM channels 
            WHERE youtube_channel_id = %s;
        """,
            (channel_id,),
        )

        result = cur.fetchone()
        if result:
            return {
                "youtube_channel_id": result[0],
                "channel_title": result[1],
                "description": result[2],
                "subscriber_count": result[3],
                "video_count": result[4],
                "view_count": result[5],
                "country": result[6],
                "custom_url": result[7],
                "published_at": result[8],
                "thumbnail_url": result[9],
                "topic_ids": result[10],
                "last_updated": result[11],
                "created_at": result[12],
            }
        return None


def print_channels_with_metadata(conn):
    """Print all channels with their metadata from the database."""
    if not conn:
        logger.warning("Database connection not available.")
        return

    logger.info("--- Channels with Metadata ---")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.channel_name, s.status, s.subscription_date,
                   c.subscriber_count, c.video_count, c.description, c.topic_ids
            FROM subscriptions s
            LEFT JOIN channels c ON s.youtube_channel_id = c.youtube_channel_id
            ORDER BY s.channel_name;
        """
        )
        records = cur.fetchall()

        if not records:
            logger.info("No channels found in the database.")
            return

        for record in records:
            name, status, sub_date, sub_count, vid_count, description, topic_ids = (
                record
            )

            # Format subscriber count
            sub_count_str = f"{sub_count:,}" if sub_count else "N/A"
            vid_count_str = f"{vid_count:,}" if vid_count else "N/A"

            # Truncate description for display
            desc_short = (
                (description[:100] + "...")
                if description and len(description) > 100
                else description or "No description"
            )

            logger.info(f"- {name:<50} Status: {status:<20}")
            logger.info(
                f"  Subscribers: {sub_count_str:<10} Videos: {vid_count_str:<10} Subscribed: {sub_date.strftime('%Y-%m-%d')}"
            )
            logger.info(f"  Description: {desc_short}")
            if topic_ids:
                logger.info(
                    f"  Topics: {', '.join(topic_ids[:5])}{'...' if len(topic_ids) > 5 else ''}"
                )
            logger.info("")

    logger.info("-" * 50)


def get_all_channels_with_metadata(conn):
    """Get all channels with their metadata from the database."""
    if not conn:
        return []

    try:
        cursor = conn.cursor()

        query = """
        SELECT 
            s.youtube_channel_id,
            s.channel_name,
            s.status,
            s.subscription_date,
            c.channel_title,
            c.description,
            c.subscriber_count,
            c.video_count,
            c.view_count,
            c.country,
            c.custom_url,
            c.published_at,
            c.thumbnail_url,
            c.topic_ids
        FROM subscriptions s
        LEFT JOIN channels c ON s.youtube_channel_id = c.youtube_channel_id
        ORDER BY s.channel_name
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        channels = []
        for row in rows:
            channel = {
                "youtube_channel_id": row[0],
                "channel_name": row[1],
                "status": row[2],
                "subscription_date": row[3],
                "channel_title": row[4] or row[1],  # Fallback to channel_name
                "description": row[5] or "No description available",
                "subscriber_count": row[6],
                "video_count": row[7],
                "view_count": row[8],
                "country": row[9],
                "custom_url": row[10],
                "published_at": row[11],
                "thumbnail_url": row[12],
                "topic_ids": row[13] or [],
            }
            channels.append(channel)

        cursor.close()
        return channels

    except Exception as e:
        logger.error(f"Error getting all channels with metadata: {e}")
        return []


def search_channels_with_metadata(conn, search_term, count_only=False):
    """Search channels with metadata based on search term."""
    if not conn:
        return 0 if count_only else []

    try:
        cursor = conn.cursor()

        # Escape special characters for LIKE
        search_pattern = f"%{search_term}%"

        if count_only:
            query = """
            SELECT COUNT(*)
            FROM subscriptions s
            LEFT JOIN channels c ON s.youtube_channel_id = c.youtube_channel_id
            WHERE s.status = 'SUBSCRIBED'
            AND (
                LOWER(s.channel_name) LIKE LOWER(%s)
                OR LOWER(COALESCE(c.channel_title, '')) LIKE LOWER(%s)
                OR LOWER(COALESCE(c.description, '')) LIKE LOWER(%s)
            )
            """
            cursor.execute(query, (search_pattern, search_pattern, search_pattern))
            result = cursor.fetchone()
            cursor.close()
            return result[0] if result else 0

        query = """
            SELECT 
                s.youtube_channel_id,
                s.channel_name,
                s.status,
                s.subscription_date,
                c.channel_title,
                c.description,
                c.subscriber_count,
                c.video_count,
                c.view_count,
                c.country,
                c.custom_url,
                c.published_at,
                c.thumbnail_url,
                c.topic_ids
            FROM subscriptions s
            LEFT JOIN channels c ON s.youtube_channel_id = c.youtube_channel_id
            WHERE s.status = 'SUBSCRIBED'
            AND (
                LOWER(s.channel_name) LIKE LOWER(%s)
                OR LOWER(COALESCE(c.channel_title, '')) LIKE LOWER(%s)
                OR LOWER(COALESCE(c.description, '')) LIKE LOWER(%s)
            )
            ORDER BY s.channel_name
            """

        cursor.execute(query, (search_pattern, search_pattern, search_pattern))
        rows = cursor.fetchall()

        channels = []
        for row in rows:
            channel = {
                "youtube_channel_id": row[0],
                "channel_name": row[1],
                "status": row[2],
                "subscription_date": row[3],
                "channel_title": row[4] or row[1],  # Fallback to channel_name
                "description": row[5] or "No description available",
                "subscriber_count": row[6],
                "video_count": row[7],
                "view_count": row[8],
                "country": row[9],
                "custom_url": row[10],
                "published_at": row[11],
                "thumbnail_url": row[12],
                "topic_ids": row[13] or [],
            }
            channels.append(channel)

        cursor.close()
        return channels

    except Exception as e:
        logger.error(f"Error searching channels: {e}")
        return 0 if count_only else []


def get_subscriptions_sorted_by_subscriber_count(conn):
    """Get all SUBSCRIBED subscriptions sorted by subscriber count (lowest first). Excludes KEPT, TO_BE_UNSUBSCRIBED, and UNSUBSCRIBED channels."""
    if not conn:
        return []

    try:
        cursor = conn.cursor()

        query = """
        SELECT 
            s.youtube_channel_id,
            s.youtube_subscription_id,
            s.channel_name,
            s.channel_link,
            s.status,
            s.subscription_date,
            c.channel_title,
            c.description,
            c.subscriber_count,
            c.video_count,
            c.view_count,
            c.country,
            c.custom_url,
            c.published_at,
            c.thumbnail_url,
            c.topic_ids,
            c.content_type,
            c.shorts_count,
            c.longs_count,
            c.shorts_percentage
        FROM subscriptions s
        LEFT JOIN channels c ON s.youtube_channel_id = c.youtube_channel_id
        WHERE s.status = 'SUBSCRIBED'
        ORDER BY COALESCE(c.subscriber_count, 0) ASC, s.channel_name ASC
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        subscriptions = []
        for row in rows:
            subscription = {
                "youtube_channel_id": row[0],
                "youtube_subscription_id": row[1],
                "channel_name": row[2],
                "channel_link": row[3],
                "status": row[4],
                "subscription_date": row[5],
                "channel_title": row[6] or row[2],  # Fallback to channel_name
                "description": row[7] or "No description available",
                "subscriber_count": row[8] or 0,
                "video_count": row[9] or 0,
                "view_count": row[10] or 0,
                "country": row[11] or "Unknown",
                "custom_url": row[12],
                "published_at": row[13],
                "thumbnail_url": row[14],
                "topic_ids": row[15] or [],
                "content_type": row[16] or "UNKNOWN",
                "shorts_count": row[17] or 0,
                "longs_count": row[18] or 0,
                "shorts_percentage": float(row[19]) if row[19] is not None else 0.0,
            }
            subscriptions.append(subscription)

        cursor.close()
        return subscriptions

    except Exception as e:
        logger.error(f"Error getting subscriptions sorted by subscriber count: {e}")
        return []


def save_content_analysis_result(conn, analysis_result):
    """
    Save content analysis result to the database.

    Args:
        conn: Database connection
        analysis_result: ContentAnalysisResult object
    """
    if not conn or not analysis_result:
        return False

    try:
        cursor = conn.cursor()

        query = """
        UPDATE channels 
        SET 
            content_type = %s,
            shorts_count = %s,
            longs_count = %s,
            shorts_percentage = %s,
            content_analysis_date = %s,
            last_updated = CURRENT_TIMESTAMP
        WHERE youtube_channel_id = %s
        """

        cursor.execute(
            query,
            (
                analysis_result.content_type,
                analysis_result.shorts_count,
                analysis_result.longs_count,
                analysis_result.shorts_percentage,
                analysis_result.analysis_date,
                analysis_result.channel_id,  # This is the youtube_channel_id
            ),
        )

        conn.commit()
        cursor.close()

        logger.info(
            f"Content analysis result saved for channel {analysis_result.channel_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error saving content analysis result: {e}")
        return False


def get_channels_needing_content_analysis(conn, limit=None):
    """
    Get channels that need content analysis (content_type = 'UNKNOWN').

    Args:
        conn: Database connection
        limit: Maximum number of channels to return (optional)

    Returns:
        List of channel dictionaries
    """
    if not conn:
        return []

    try:
        cursor = conn.cursor()

        query = """
        SELECT 
            youtube_channel_id,
            channel_title,
            subscriber_count,
            video_count
        FROM channels 
        WHERE content_type = 'UNKNOWN'
        ORDER BY subscriber_count DESC NULLS LAST, channel_title ASC
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        rows = cursor.fetchall()

        channels = []
        for row in rows:
            channel = {
                "youtube_channel_id": row[0],
                "channel_title": row[1],
                "subscriber_count": row[2] or 0,
                "video_count": row[3] or 0,
            }
            channels.append(channel)

        cursor.close()
        return channels

    except Exception as e:
        logger.error(f"Error getting channels needing content analysis: {e}")
        return []


def get_content_analysis_stats(conn):
    """
    Get statistics about content analysis status.

    Args:
        conn: Database connection

    Returns:
        Dictionary with analysis statistics
    """
    if not conn:
        return {}

    try:
        cursor = conn.cursor()

        query = """
        SELECT 
            content_type,
            COUNT(*) as count
        FROM channels 
        GROUP BY content_type
        ORDER BY count DESC
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        stats = {
            "by_content_type": {},
            "total_channels": 0,
            "analyzed_channels": 0,
            "unknown_channels": 0,
        }

        for row in rows:
            content_type = row[0] or "UNKNOWN"
            count = row[1]
            stats["by_content_type"][content_type] = count
            stats["total_channels"] += count

            if content_type != "UNKNOWN":
                stats["analyzed_channels"] += count
            else:
                stats["unknown_channels"] += count

        cursor.close()
        return stats

    except Exception as e:
        logger.error(f"Error getting content analysis stats: {e}")
        return {}
