import os
import pickle
import sys
import termios
import tty

import psycopg2
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text
import logging

# Load environment variables from .env file
load_dotenv()

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

# --- CONFIGURATION ---
CLIENT_SECRETS_FILE = os.getenv("CLIENT_SECRETS_FILE", "client_secret.json")
SCOPES = [os.getenv("SCOPES", "https://www.googleapis.com/auth/youtube")]
API_SERVICE_NAME = os.getenv("API_SERVICE_NAME", "youtube")
API_VERSION = os.getenv("API_VERSION", "v3")
TOKEN_FILE = os.getenv("TOKEN_FILE", "token.pickle")

# --- DATABASE CONFIGURATION ---
DB_NAME = os.getenv("DB_NAME", "youtube_subscriptions")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")


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
        sys.exit(1)


def get_char():
    """Reads a single character from stdin."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


def authenticate_youtube():
    """Handles user authentication and returns an authorized YouTube API service object."""
    credentials = None

    # Check if a token file already exists from a previous run
    if os.path.exists(TOKEN_FILE):
        logger.info("Loading existing credentials...")
        with open(TOKEN_FILE, "rb") as token:
            credentials = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in.
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            logger.info("Refreshing access token...")
            credentials.refresh(Request())
        else:
            logger.info("Fetching new credentials...")
            if not os.path.exists(CLIENT_SECRETS_FILE):
                logger.error(f"The credentials file '{CLIENT_SECRETS_FILE}' was not found.")
                logger.error("Please follow the setup instructions in README.md to download it.")
                return None
                
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(credentials, token)
            logger.info(f"Credentials saved to '{TOKEN_FILE}' for future use.")

    try:
        youtube = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
        logger.info("✅ Authentication successful.")
        return youtube
    except HttpError as e:
        logger.error(f"An error occurred during API build: {e}")
        return None


def get_all_subscriptions(youtube):
    """Fetches all YouTube subscriptions for the authenticated user."""
    all_subscriptions = []
    next_page_token = None
    logger.info("Fetching all your subscriptions... (this may take a moment)")

    while True:
        try:
            request = youtube.subscriptions().list(
                part="snippet",
                mine=True,
                maxResults=50,  # Max allowed per page
                pageToken=next_page_token
            )
            response = request.execute()
            
            all_subscriptions.extend(response.get("items", []))
            next_page_token = response.get("nextPageToken")
            
            logger.info(f"Found {len(all_subscriptions)} subscriptions so far...")

            if not next_page_token:
                break
        except HttpError as e:
            logger.error(f"An error occurred while fetching subscriptions: {e}")
            return []

    return all_subscriptions


def insert_subscriptions_to_db(conn, subscriptions):
    """Inserts or updates a list of subscriptions into the database."""
    if not conn:
        print("Database connection not available. Skipping database insertion.")
        return

    print(f"\nInserting {len(subscriptions)} subscriptions into the database...")
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
    print("Database insertion complete.")


def is_db_empty(conn):
    """Checks if the subscriptions table in the database is empty."""
    if not conn:
        return True  # Assume empty if no DB connection
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM subscriptions;")
        count = cur.fetchone()[0]
        return count == 0


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


def print_subscription_report(conn):
    """Prints a detailed subscription report."""
    if not conn:
        console.print("[yellow]Database connection not available.[/yellow]")
        return
    
    stats = get_subscription_stats(conn)
    if not stats:
        console.print("[yellow]No subscription data available.[/yellow]")
        return
    
    # Create status breakdown text
    status_text = ""
    for status in ['SUBSCRIBED', 'TO_BE_UNSUBSCRIBED', 'UNSUBSCRIBED']:
        count = stats['by_status'].get(status, 0)
        if status == 'SUBSCRIBED':
            color = "green"
            icon = "✅"
        elif status == 'TO_BE_UNSUBSCRIBED':
            color = "yellow"
            icon = "⚠️"
        elif status == 'UNSUBSCRIBED':
            color = "red"
            icon = "❌"
        
        status_text += "[" + color + "]" + icon + " " + status + ": " + str(count) + "[/" + color + "]\n"
    
    # Create the report panel
    report_panel = Panel(
        f"[bold blue]Total Subscriptions: {stats['total']}[/bold blue]\n\n"
        f"[bold]Status Breakdown:[/bold]\n"
        f"{status_text.strip()}",
        title="📊 Subscription Report",
        border_style="blue"
    )
    console.print(report_panel)


def print_all_channels_from_db(conn):
    """Fetches and prints all channels from the database."""
    if not conn:
        print("Database connection not available.")
        return
    print("\n--- Subscriptions from Database ---")
    with conn.cursor() as cur:
        cur.execute("SELECT channel_name, status, subscription_date FROM subscriptions ORDER BY channel_name;")
        records = cur.fetchall()
        if not records:
            print("No subscriptions found in the database.")
            return

        for record in records:
            name, status, date = record
            print(f"- {name:<50} Status: {status:<20} Subscribed On: {date.strftime('%Y-%m-%d')}")
    print("-" * 33)


def get_channels_to_unsubscribe_from_db(conn):
    """Fetches channels marked 'TO_BE_UNSUBSCRIBED' from the database."""
    if not conn:
        print("Database connection not available.")
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


def unsubscribe_from_channels(youtube, conn, channels):
    """Unsubscribes from the list of selected channels and updates the database."""
    if not channels:
        print("\nNo channels found to unsubscribe.")
        return

    print(f"\n--- Found {len(channels)} channels marked for unsubscription ---")
    confirm = input("Are you sure you want to proceed? This action cannot be undone. (yes/no): ").lower()

    if confirm != 'yes':
        print("Unsubscription process aborted by user.")
        return

    for channel in channels:
        subscription_id = channel["id"]
        channel_title = channel["title"]
        try:
            print(f"Unsubscribing from '{channel_title}'...")
            youtube.subscriptions().delete(id=subscription_id).execute()
            # On success, update the database
            update_subscription_status_in_db(conn, subscription_id, "UNSUBSCRIBED")
            print(f"Successfully unsubscribed from '{channel_title}'.")
        except HttpError as e:
            print(f"Failed to unsubscribe from '{channel_title}': {e}")
            print("This could be due to reaching your daily API quota.")
            break  # Stop the process if an error occurs

    print("\nUnsubscription process complete.")


def print_instructions():
    """Prints the available commands."""
    commands_panel = Panel(
        "[bold cyan]Available Commands:[/bold cyan]\n\n"
        "[green]p[/green] - Print all subscriptions from the database\n"
        "[blue]f[/blue] - Force refetch all subscriptions from YouTube and update the database\n"
        "[red]r[/red] - Run the unsubscription process for channels marked 'TO_BE_UNSUBSCRIBED'\n"
        "[magenta]s[/magenta] - Show subscription statistics report\n"
        "[yellow]q[/yellow] - Quit the program",
        title="[bold]Commands[/bold]",
        border_style="cyan"
    )
    console.print(commands_panel)


def main():
    """Main function to run the script logic."""
    # Display welcome banner
    welcome_panel = Panel(
        "[bold blue]YouTube Subscription Manager[/bold blue]\n"
        "[dim]Manage your YouTube subscriptions with PostgreSQL database integration[/dim]",
        title="🎬 Welcome",
        border_style="blue"
    )
    console.print(welcome_panel)
    
    # Authenticate with YouTube
    logger.info("Authenticating with YouTube API...")
    youtube = authenticate_youtube()
    if not youtube:
        error_panel = Panel(
            "[red]❌ YouTube Authentication Failed[/red]\n\n"
            "[yellow]Please check:[/yellow]\n"
            "• client_secret.json file exists\n"
            "• Google Cloud Console credentials are correct\n"
            "• YouTube Data API v3 is enabled",
            title="[bold red]Authentication Error[/bold red]",
            border_style="red"
        )
        console.print(error_panel)
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
        
        success_panel = Panel(
            "[green]✅ Setup Complete![/green]\n\n"
            "[blue]Next steps:[/blue]\n"
            "• Review your subscriptions in the database\n"
            "• Set 'status' column to 'TO_BE_UNSUBSCRIBED' for channels to remove\n"
            "• Use the commands below to manage subscriptions",
            title="[bold green]Ready[/bold green]",
            border_style="green"
        )
        console.print(success_panel)

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
