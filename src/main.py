"""
Main application entry point for YouTube Subscription Manager.
"""

import logging
from rich.console import Console
from rich.logging import RichHandler

from .config import *
from .database import connect_db, is_db_empty, insert_subscriptions_to_db, print_all_channels_from_db, get_channels_to_unsubscribe_from_db, get_channels_without_metadata, insert_channel_metadata, print_channels_with_metadata
from .youtube_api import authenticate_youtube, get_all_subscriptions, unsubscribe_from_channels
from .ui import print_welcome_banner, print_authentication_error, print_success_panel, print_instructions, print_subscription_report, print_quota_status, get_char
from .quota_tracker import QuotaTracker
from .channel_fetcher import fetch_channel_metadata, process_channel_data

# Initialize Rich console and logging
console = Console()

# Setup logging with Rich
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)]
)
logger = logging.getLogger("youtube-unsubscriber")


def fetch_and_store_channel_metadata(youtube, conn, quota_tracker):
    """Fetch and store channel metadata for channels that don't have it."""
    if not conn:
        logger.warning("Database connection not available.")
        return
    
    # Get channel IDs that don't have metadata
    channel_ids = get_channels_without_metadata(conn)
    
    if not channel_ids:
        logger.info("All channels already have metadata.")
        return
    
    logger.info(f"Fetching metadata for {len(channel_ids)} channels...")
    
    # Fetch metadata in batches
    batch_size = 50  # YouTube API limit
    for i in range(0, len(channel_ids), batch_size):
        batch_ids = channel_ids[i:i + batch_size]
        
        try:
            # Fetch channel metadata
            raw_channels = fetch_channel_metadata(youtube, batch_ids, quota_tracker)
            
            # Process and store each channel
            for channel_data in raw_channels:
                processed_data = process_channel_data(channel_data)
                insert_channel_metadata(conn, processed_data, quota_tracker)
            
            logger.info(f"Processed batch {i//batch_size + 1}/{(len(channel_ids) + batch_size - 1)//batch_size}")
            
        except Exception as e:
            logger.error(f"Error processing channel metadata batch: {e}")
            continue
    
    logger.info("Channel metadata fetching complete.")


def main():
    """Main function to run the script logic."""
    # Display welcome banner
    print_welcome_banner()
    
    # Initialize quota tracker
    quota_tracker = QuotaTracker()
    
    # Authenticate with YouTube
    logger.info("Authenticating with YouTube API...")
    youtube = authenticate_youtube()
    if not youtube:
        print_authentication_error()
        logger.error("Could not authenticate with YouTube. Exiting.")
        return

    # Connect to database (will exit if fails)
    conn = connect_db()

    # Fetch subscriptions if database is empty
    if conn and is_db_empty(conn):
        logger.info("Database is empty. Fetching subscriptions from YouTube...")
        subscriptions = get_all_subscriptions(youtube, quota_tracker)
        if subscriptions:
            insert_subscriptions_to_db(conn, subscriptions, quota_tracker)
        else:
            logger.warning("Could not find any subscriptions or an error occurred.")
    
    # Fetch channel metadata for channels that don't have it
    if conn:
        fetch_and_store_channel_metadata(youtube, conn, quota_tracker)

    # Display subscription report
    if conn:
        print_subscription_report(conn, quota_tracker)
        print_success_panel()

    print_instructions()

    while True:
        console.print("\n[bold cyan]Enter a command:[/bold cyan] ", end="")
        char = get_char()
        console.print(char)  # Echo the character

        if char == "q":
            print_quota_status(quota_tracker)
        elif char == "x":
            logger.info("Exiting program.")
            break
        elif char == "p":
            print_all_channels_from_db(conn)
        elif char == "f":
            logger.info("Force refetching all subscriptions...")
            subscriptions = get_all_subscriptions(youtube, quota_tracker)
            if subscriptions:
                insert_subscriptions_to_db(conn, subscriptions, quota_tracker)
        elif char == "r":
            channels_to_remove = get_channels_to_unsubscribe_from_db(conn)
            unsubscribe_from_channels(youtube, conn, channels_to_remove, quota_tracker)
        elif char == "s":
            print_subscription_report(conn, quota_tracker)
        elif char == "m":
            print_channels_with_metadata(conn)
        elif char == "u":
            logger.info("Updating channel metadata...")
            fetch_and_store_channel_metadata(youtube, conn, quota_tracker)
        else:
            console.print("[yellow]Unknown command.[/yellow]")
            print_instructions()

    if conn:
        conn.close()
        logger.info("Database connection closed.")


if __name__ == "__main__":
    main()
