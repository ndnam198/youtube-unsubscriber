import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError

# --- CONFIGURATION ---
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/youtube"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"
TOKEN_FILE = "token.pickle" # Using pickle for storing credentials

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


def select_channels_to_unsubscribe(subscriptions):
    """Prompts the user to select which channels to unsubscribe from."""
    channels_to_remove = []
    print("\n--- Review Your Subscriptions ---")
    print("Enter 'y' to unsubscribe, 'n' to keep, or 'q' to quit and proceed.")

    for i, sub in enumerate(subscriptions):
        channel_title = sub["snippet"]["title"]
        prompt = f"({i+1}/{len(subscriptions)}) Unsubscribe from '{channel_title}'? (y/n/q): "
        
        while True:
            user_input = input(prompt).lower()
            if user_input in ['y', 'n', 'q']:
                break
            else:
                print("Invalid input. Please enter 'y', 'n', or 'q'.")

        if user_input == 'y':
            channels_to_remove.append(sub)
        elif user_input == 'q':
            print("Quitting selection...")
            break
            
    return channels_to_remove


def unsubscribe_from_channels(youtube, channels):
    """Unsubscribes from the list of selected channels."""
    if not channels:
        print("\nNo channels were selected for unsubscription.")
        return

    print(f"\n--- Preparing to unsubscribe from {len(channels)} channels ---")
    confirm = input("Are you sure you want to proceed? This action cannot be undone. (yes/no): ").lower()

    if confirm != 'yes':
        print("Unsubscription process aborted by user.")
        return
        
    for channel in channels:
        subscription_id = channel["id"]
        channel_title = channel["snippet"]["title"]
        try:
            print(f"Unsubscribing from '{channel_title}'...")
            youtube.subscriptions().delete(id=subscription_id).execute()
        except HttpError as e:
            print(f"Failed to unsubscribe from '{channel_title}': {e}")
            print("This could be due to reaching your daily API quota.")
            break # Stop the process if an error occurs

    print("\nUnsubscription process complete.")


def main():
    """Main function to run the script logic."""
    print("--- YouTube Subscription Manager ---")
    youtube = authenticate_youtube()
    
    if not youtube:
        print("Could not authenticate. Exiting.")
        return

    subscriptions = get_all_subscriptions(youtube)

    if not subscriptions:
        print("Could not find any subscriptions or an error occurred.")
        return
        
    print(f"\nTotal subscriptions found: {len(subscriptions)}")
    
    channels_to_remove = select_channels_to_unsubscribe(subscriptions)
    unsubscribe_from_channels(youtube, channels_to_remove)

    print("\nScript finished.")


if __name__ == "__main__":
    main()
