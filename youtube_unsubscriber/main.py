"""
Main application entry point for YouTube Subscription Manager.
"""

import logging
from rich.console import Console
from rich.logging import RichHandler

from .config import *
from .database import connect_db, is_db_empty, insert_subscriptions_to_db, print_all_channels_from_db, get_channels_to_unsubscribe_from_db
from .youtube_api import authenticate_youtube, get_all_subscriptions, unsubscribe_from_channels
from .ui import print_welcome_banner, print_authentication_error, print_success_panel, print_instructions, print_subscription_report, get_char

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


def main():
    """Main function to run the script logic."""
    # Display welcome banner
    print_welcome_banner()
    
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
        subscriptions = get_all_subscriptions(youtube)
        if subscriptions:
            insert_subscriptions_to_db(conn, subscriptions)
        else:
            logger.warning("Could not find any subscriptions or an error occurred.")

    # Display subscription report
    if conn:
        print_subscription_report(conn)
        print_success_panel()

    print_instructions()

    while True:
        console.print("\n[bold cyan]Enter a command:[/bold cyan] ", end="")
        char = get_char()
        console.print(char)  # Echo the character

        if char == "q":
            logger.info("Exiting program.")
            break
        elif char == "p":
            print_all_channels_from_db(conn)
        elif char == "f":
            logger.info("Force refetching all subscriptions...")
            subscriptions = get_all_subscriptions(youtube)
            if subscriptions:
                insert_subscriptions_to_db(conn, subscriptions)
        elif char == "r":
            channels_to_remove = get_channels_to_unsubscribe_from_db(conn)
            unsubscribe_from_channels(youtube, conn, channels_to_remove)
        elif char == "s":
            print_subscription_report(conn)
        else:
            console.print("[yellow]Unknown command.[/yellow]")
            print_instructions()

    if conn:
        conn.close()
        logger.info("Database connection closed.")


if __name__ == "__main__":
    main()
