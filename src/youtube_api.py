"""
YouTube API operations for YouTube Subscription Manager.
"""

import logging
import os
import pickle

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.config import (
    CLIENT_SECRETS_FILE,
    SCOPES,
    API_SERVICE_NAME,
    API_VERSION,
    TOKEN_FILE,
)
from src.database import update_subscription_status_in_db

logger = logging.getLogger("youtube-unsubscriber")


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
                logger.error(
                    f"The credentials file '{CLIENT_SECRETS_FILE}' was not found."
                )
                logger.error(
                    "Please follow the setup instructions in README.md to download it."
                )
                return None

            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE, SCOPES
            )
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


def get_all_subscriptions(youtube, quota_tracker=None):
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
                pageToken=next_page_token,
            )
            response = request.execute()

            # Record quota usage for each API call
            if quota_tracker:
                quota_tracker.record_api_call("subscriptions.list", 1)

            all_subscriptions.extend(response.get("items", []))
            next_page_token = response.get("nextPageToken")

            logger.info(f"Found {len(all_subscriptions)} subscriptions so far...")

            if not next_page_token:
                break
        except HttpError as e:
            logger.error(f"An error occurred while fetching subscriptions: {e}")
            return []

    return all_subscriptions


def unsubscribe_from_channels(youtube, conn, channels, quota_tracker=None):
    """Unsubscribes from the list of selected channels and updates the database."""
    if not channels:
        logger.info("No channels found to unsubscribe.")
        return

    # Check quota before proceeding
    if quota_tracker:
        if not quota_tracker.can_perform_operation(
            "subscriptions.delete", len(channels)
        ):
            logger.error("Insufficient quota to perform all unsubscriptions.")
            max_possible = quota_tracker.calculate_max_unsubscriptions()
            logger.error(f"Maximum unsubscriptions possible today: {max_possible}")
            return

    logger.info(f"--- Found {len(channels)} channels marked for unsubscription ---")
    confirm = input(
        "Are you sure you want to proceed? This action cannot be undone. (yes/no): "
    ).lower()

    if confirm != "yes":
        logger.info("Unsubscription process aborted by user.")
        return

    successful_unsubs = 0
    for channel in channels:
        subscription_id = channel["id"]
        channel_title = channel["title"]
        try:
            logger.info(f"Unsubscribing from '{channel_title}'...")
            youtube.subscriptions().delete(id=subscription_id).execute()

            # Record quota usage for successful unsubscription
            if quota_tracker:
                quota_tracker.record_api_call("subscriptions.delete", 1)

            # On success, update the database
            update_subscription_status_in_db(conn, subscription_id, "UNSUBSCRIBED")
            successful_unsubs += 1
            logger.info(f"Successfully unsubscribed from '{channel_title}'.")
        except HttpError as e:
            logger.error(f"Failed to unsubscribe from '{channel_title}': {e}")
            logger.error("This could be due to reaching your daily API quota.")
            break  # Stop the process if an error occurs

    logger.info(
        f"Unsubscription process complete. Successfully unsubscribed from {successful_unsubs} channels."
    )
