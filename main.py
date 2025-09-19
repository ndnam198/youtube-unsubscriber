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

# Load environment variables from .env file
load_dotenv()

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
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
        )
        print("Successfully connected to the database.")
        return conn
    except psycopg2.OperationalError as e:
        print(f"Warning: Could not connect to the database. {e}")
        print("Please ensure PostgreSQL is running and the connection details are correct.")
        print("The script will continue without database functionality.")
        return None


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
        with open(TOKEN_FILE, "rb") as token:
            credentials = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in.
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            print("Refreshing access token...")
            credentials.refresh(Request())
        else:
            print("Fetching new credentials...")
            if not os.path.exists(CLIENT_SECRETS_FILE):
                print(f"Error: The credentials file '{CLIENT_SECRETS_FILE}' was not found.")
                print("Please follow the setup instructions in README.md to download it.")
                return None
                
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(credentials, token)
            print(f"Credentials saved to '{TOKEN_FILE}' for future use.")

    try:
        youtube = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
        print("Authentication successful.")
        return youtube
    except HttpError as e:
        print(f"An error occurred during API build: {e}")
        return None


def get_all_subscriptions(youtube):
    """Fetches all YouTube subscriptions for the authenticated user."""
    all_subscriptions = []
    next_page_token = None
    print("\nFetching all your subscriptions... (this may take a moment)")

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
            
            print(f"Found {len(all_subscriptions)} subscriptions so far...")

            if not next_page_token:
                break
        except HttpError as e:
            print(f"An error occurred while fetching subscriptions: {e}")
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
    print("\nAvailable commands:")
    print("  p - Print all subscriptions from the database")
    print("  f - Force refetch all subscriptions from YouTube and update the database")
    print("  r - Run the unsubscription process for channels marked 'TO_BE_UNSUBSCRIBED'")
    print("  q - Quit the program")


def main():
    """Main function to run the script logic."""
    print("--- YouTube Subscription Manager ---")
    youtube = authenticate_youtube()
    if not youtube:
        print("Could not authenticate with YouTube. Exiting.")
        return

    conn = connect_db()

    if conn and is_db_empty(conn):
        print("Database is empty. Fetching subscriptions from YouTube...")
        subscriptions = get_all_subscriptions(youtube)
        if subscriptions:
            insert_subscriptions_to_db(conn, subscriptions)
        else:
            print("Could not find any subscriptions or an error occurred.")

    if conn:
        print("\nFetching complete. Please review your subscriptions in the database.")
        print("Set the 'status' column to 'TO_BE_UNSUBSCRIBED' for channels you wish to remove.")

    print_instructions()

    while True:
        print("\nEnter a command: ", end="", flush=True)
        char = get_char()
        print(char)  # Echo the character

        if char == "q":
            print("Exiting.")
            break
        elif char == "p":
            print_all_channels_from_db(conn)
        elif char == "f":
            print("Force refetching all subscriptions...")
            subscriptions = get_all_subscriptions(youtube)
            if subscriptions:
                insert_subscriptions_to_db(conn, subscriptions)
        elif char == "r":
            channels_to_remove = get_channels_to_unsubscribe_from_db(conn)
            unsubscribe_from_channels(youtube, conn, channels_to_remove)
        else:
            print("Unknown command.")
            print_instructions()

    if conn:
        conn.close()
        print("Database connection closed.")


if __name__ == "__main__":
    main()
