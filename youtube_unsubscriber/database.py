"""
Database operations for YouTube Subscription Manager.
"""

import psycopg2
from rich.console import Console
from rich.panel import Panel
import logging

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


def insert_subscriptions_to_db(conn, subscriptions):
    """Inserts or updates a list of subscriptions into the database."""
    if not conn:
        logger.warning("Database connection not available. Skipping database insertion.")
        return

    logger.info(f"Inserting {len(subscriptions)} subscriptions into the database...")
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
