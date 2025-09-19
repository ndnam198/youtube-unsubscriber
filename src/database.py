"""
Database operations for YouTube Subscription Manager.
"""

import psycopg2
from rich.console import Console
from rich.panel import Panel
import logging
from typing import List, Dict, Optional

from .config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT

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
            border_style="red"
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
        logger.warning("Database connection not available. Skipping database insertion.")
        return

    logger.info(f"Inserting {len(subscriptions)} subscriptions into the database...")
    
    # Record quota usage for fetching subscriptions
    if quota_tracker:
        quota_tracker.record_api_call('subscriptions.list', 1)
    
    with conn.cursor() as cur:
        for sub in subscriptions:
            snippet = sub["snippet"]
            channel_id = snippet["resourceId"]["channelId"]
            subscription_id = sub["id"]
            channel_title = snippet["title"]
            published_at = snippet["publishedAt"]
            channel_link = f"https://www.youtube.com/channel/{channel_id}"

            cur.execute(
                """
                INSERT INTO subscriptions (youtube_channel_id, youtube_subscription_id, channel_name, channel_link, subscription_date, status)
                VALUES (%s, %s, %s, %s, %s, 'SUBSCRIBED')
                ON CONFLICT (youtube_channel_id) DO UPDATE SET
                    channel_name = EXCLUDED.channel_name,
                    subscription_date = EXCLUDED.subscription_date,
                    status = 'SUBSCRIBED';
                """,
                (channel_id, subscription_id, channel_title, channel_link, published_at),
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
        cur.execute("SELECT status, COUNT(*) FROM subscriptions GROUP BY status ORDER BY status;")
        status_counts = dict(cur.fetchall())
        
        return {
            'total': total,
            'by_status': status_counts
        }


def print_all_channels_from_db(conn):
    """Fetches and prints all channels from the database."""
    if not conn:
        logger.warning("Database connection not available.")
        return
    logger.info("--- Subscriptions from Database ---")
    with conn.cursor() as cur:
        cur.execute("SELECT channel_name, status, subscription_date FROM subscriptions ORDER BY channel_name;")
        records = cur.fetchall()
        if not records:
            logger.info("No subscriptions found in the database.")
            return

        for record in records:
            name, status, date = record
            logger.info(f"- {name:<50} Status: {status:<20} Subscribed On: {date.strftime('%Y-%m-%d')}")
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
        logger.warning("Database connection not available. Skipping channel metadata insertion.")
        return

    logger.info(f"Inserting/updating channel metadata for {channel_data['youtube_channel_id']}...")
    
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
            channel_data
        )
    conn.commit()
    logger.info("Channel metadata insertion/update complete.")


def get_channels_without_metadata(conn) -> List[str]:
    """Get channel IDs that don't have metadata in the channels table."""
    if not conn:
        return []
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT s.youtube_channel_id 
            FROM subscriptions s 
            LEFT JOIN channels c ON s.youtube_channel_id = c.youtube_channel_id 
            WHERE c.youtube_channel_id IS NULL 
            OR c.subscriber_count IS NULL 
            OR c.video_count IS NULL;
        """)
        results = cur.fetchall()
        return [row[0] for row in results]


def get_channel_metadata(conn, channel_id: str) -> Optional[Dict]:
    """Get metadata for a specific channel."""
    if not conn:
        return None
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT youtube_channel_id, channel_title, description, subscriber_count,
                   video_count, view_count, country, custom_url, published_at,
                   thumbnail_url, topic_ids, last_updated, created_at
            FROM channels 
            WHERE youtube_channel_id = %s;
        """, (channel_id,))
        
        result = cur.fetchone()
        if result:
            return {
                'youtube_channel_id': result[0],
                'channel_title': result[1],
                'description': result[2],
                'subscriber_count': result[3],
                'video_count': result[4],
                'view_count': result[5],
                'country': result[6],
                'custom_url': result[7],
                'published_at': result[8],
                'thumbnail_url': result[9],
                'topic_ids': result[10],
                'last_updated': result[11],
                'created_at': result[12]
            }
        return None


def print_channels_with_metadata(conn):
    """Print all channels with their metadata from the database."""
    if not conn:
        logger.warning("Database connection not available.")
        return
    
    logger.info("--- Channels with Metadata ---")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT s.channel_name, s.status, s.subscription_date,
                   c.subscriber_count, c.video_count, c.description, c.topic_ids
            FROM subscriptions s
            LEFT JOIN channels c ON s.youtube_channel_id = c.youtube_channel_id
            ORDER BY s.channel_name;
        """)
        records = cur.fetchall()
        
        if not records:
            logger.info("No channels found in the database.")
            return

        for record in records:
            name, status, sub_date, sub_count, vid_count, description, topic_ids = record
            
            # Format subscriber count
            sub_count_str = f"{sub_count:,}" if sub_count else "N/A"
            vid_count_str = f"{vid_count:,}" if vid_count else "N/A"
            
            # Truncate description for display
            desc_short = (description[:100] + "...") if description and len(description) > 100 else description or "No description"
            
            logger.info(f"- {name:<50} Status: {status:<20}")
            logger.info(f"  Subscribers: {sub_count_str:<10} Videos: {vid_count_str:<10} Subscribed: {sub_date.strftime('%Y-%m-%d')}")
            logger.info(f"  Description: {desc_short}")
            if topic_ids:
                logger.info(f"  Topics: {', '.join(topic_ids[:5])}{'...' if len(topic_ids) > 5 else ''}")
            logger.info("")
    
    logger.info("-" * 50)
