#!/usr/bin/env python3
"""
Standalone script to fetch channel metadata and populate the channels table.
This can be run independently to update channel metadata without running the main application.
"""

import sys
import os
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
)

# Add the current directory to Python path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import *
from src.database import (
    connect_db,
    get_channels_without_metadata,
    insert_channel_metadata,
)
from src.youtube_api import authenticate_youtube
from src.channel_fetcher import process_channel_data
from src.quota_tracker import QuotaTracker

# Initialize Rich console and logging
console = Console()

# Setup logging with Rich
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
logger = logging.getLogger("channel-metadata-fetcher")

# Configuration for parallel processing
BATCH_SIZE = 50  # YouTube API limit per request
MAX_PARALLEL_BATCHES = 3  # Number of batches to process simultaneously
RATE_LIMIT_DELAY = 1  # Seconds to wait between batch groups
MAX_WORKERS = 3  # Thread pool max workers


def fetch_channel_metadata_batch(
    youtube, batch_ids, quota_tracker, batch_num, total_batches
):
    """Fetch metadata for a single batch of channels."""
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
        logger.info(
            f"✅ Batch {batch_num}/{total_batches} - Fetched {len(channels)} channels"
        )

        return channels, None

    except Exception as e:
        logger.error(f"❌ Error in batch {batch_num}: {e}")
        return [], e


def fetch_all_channel_metadata():
    """Fetch metadata for all channels that don't have it."""

    # Display welcome banner
    welcome_panel = Panel(
        "[bold blue]Channel Metadata Fetcher[/bold blue]\n"
        "[dim]Fetch detailed metadata for all your subscribed channels with parallel processing[/dim]",
        title="📊 Channel Metadata",
        border_style="blue",
    )
    console.print(welcome_panel)

    # Initialize quota tracker
    quota_tracker = QuotaTracker()

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
            border_style="red",
        )
        console.print(error_panel)
        return False

    # Connect to database
    logger.info("Connecting to database...")
    try:
        conn = connect_db()
    except Exception as e:
        error_panel = Panel(
            f"[red]❌ Database Connection Failed[/red]\n\n"
            f"[yellow]Error:[/yellow] {e}\n\n"
            f"[blue]Please ensure:[/blue]\n"
            f"• PostgreSQL is running\n"
            f"• Database '{DB_NAME}' exists\n"
            f"• Database schema has been created (schema/schema.sql)\n"
            f"• Connection details in .env are correct",
            title="[bold red]Database Error[/bold red]",
            border_style="red",
        )
        console.print(error_panel)
        return False

    # Get channels that need metadata
    channel_ids = get_channels_without_metadata(conn)

    # Display startup report
    startup_panel = Panel(
        f"[bold]Startup Report:[/bold]\n"
        f"Channels without metadata: {len(channel_ids)}\n"
        f"Total subscriptions: {len(channel_ids) + len([c for c in get_channels_without_metadata(conn) if c not in channel_ids])}\n\n"
        f"[blue]Configuration:[/blue]\n"
        f"Batch size: {BATCH_SIZE} channels per request\n"
        f"Max parallel batches: {MAX_PARALLEL_BATCHES} (rate limited)\n"
        f"Rate limit delay: {RATE_LIMIT_DELAY} second(s) between groups\n"
        f"Estimated API calls needed: {(len(channel_ids) + BATCH_SIZE - 1) // BATCH_SIZE}",
        title="📊 Startup Report",
        border_style="blue",
    )
    console.print(startup_panel)

    if not channel_ids:
        success_panel = Panel(
            "[green]✅ All channels already have metadata![/green]\n\n"
            "No channels need metadata fetching.",
            title="[bold green]Complete[/bold green]",
            border_style="green",
        )
        console.print(success_panel)
        conn.close()
        return True

    # Display quota status
    quota_status = quota_tracker.get_quota_status()
    max_unsubs = quota_tracker.calculate_max_unsubscriptions()

    quota_panel = Panel(
        f"[bold]Current Quota Status:[/bold]\n"
        f"Used: {quota_status['used']:,} / {quota_status['limit']:,} units ({quota_status['percentage_used']:.1f}%)\n"
        f"Remaining: {quota_status['remaining']:,} units\n"
        f"Channels to process: {len(channel_ids)}\n"
        f"Estimated cost: {(len(channel_ids) + 49) // 50} units",
        title="📊 Quota Information",
        border_style="blue",
    )
    console.print(quota_panel)

    # Get user input for number of channels to process
    console.print(
        f"\n[bold cyan]How many channels would you like to process?[/bold cyan]"
    )
    console.print(f"[dim]Available: {len(channel_ids)} channels without metadata[/dim]")
    console.print(f"[dim]Enter 'all' or '0' to process all remaining channels[/dim]")

    while True:
        try:
            user_input = (
                input(f"\nNumber of channels to process (0-{len(channel_ids)}): ")
                .strip()
                .lower()
            )

            if user_input in ["all", "0", ""]:
                channels_to_process = len(channel_ids)
                break
            else:
                channels_to_process = int(user_input)
                if 0 < channels_to_process <= len(channel_ids):
                    break
                else:
                    console.print(
                        f"[red]Please enter a number between 1 and {len(channel_ids)}[/red]"
                    )
        except ValueError:
            console.print("[red]Please enter a valid number or 'all'[/red]")

    # Limit channels to process
    if channels_to_process < len(channel_ids):
        channel_ids = channel_ids[:channels_to_process]
        console.print(
            f"[yellow]Limited to processing {channels_to_process} channels[/yellow]"
        )

    # Check quota before proceeding
    required_quota = (len(channel_ids) + BATCH_SIZE - 1) // BATCH_SIZE
    if quota_status["remaining"] < required_quota:
        warning_panel = Panel(
            "[yellow]⚠️ Insufficient Quota[/yellow]\n\n"
            f"You don't have enough quota to fetch channel metadata.\n"
            f"Required: {required_quota} units\n"
            f"Available: {quota_status['remaining']} units\n\n"
            f"Consider running this script tomorrow when quota resets.",
            title="[bold yellow]Warning[/bold yellow]",
            border_style="yellow",
        )
        console.print(warning_panel)
        conn.close()
        return False

    confirm = input(
        f"\nProceed with fetching metadata for {len(channel_ids)} channels? (yes/no): "
    ).lower()
    if confirm != "yes":
        logger.info("Operation cancelled by user.")
        conn.close()
        return False

    # Fetch metadata in parallel batches with rate limiting
    total_batches = (len(channel_ids) + BATCH_SIZE - 1) // BATCH_SIZE

    # Create batches
    batches = []
    for i in range(0, len(channel_ids), BATCH_SIZE):
        batch_ids = channel_ids[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        batches.append((batch_num, batch_ids))

    console.print(f"\n[bold]Processing Configuration:[/bold]")
    console.print(f"• Total batches: {total_batches}")
    console.print(f"• Max parallel batches: {MAX_PARALLEL_BATCHES}")
    console.print(
        f"• Rate limiting: {RATE_LIMIT_DELAY} second(s) delay between batch groups"
    )
    console.print(f"• Batch size: {BATCH_SIZE} channels per request")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:

        task = progress.add_task("Fetching channel metadata...", total=total_batches)

        # Process batches in parallel groups with rate limiting
        for group_start in range(0, len(batches), MAX_PARALLEL_BATCHES):
            group_batches = batches[group_start : group_start + MAX_PARALLEL_BATCHES]

            # Update progress description
            progress.update(
                task,
                description=f"Processing batch group {group_start // MAX_PARALLEL_BATCHES + 1}/{(len(batches) + MAX_PARALLEL_BATCHES - 1) // MAX_PARALLEL_BATCHES}",
            )

            # Process this group of batches in parallel
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                # Submit all batches in this group
                future_to_batch = {
                    executor.submit(
                        fetch_channel_metadata_batch,
                        youtube,
                        batch_ids,
                        quota_tracker,
                        batch_num,
                        total_batches,
                    ): (batch_num, batch_ids)
                    for batch_num, batch_ids in group_batches
                }

                # Process completed batches
                for future in as_completed(future_to_batch):
                    batch_num, batch_ids = future_to_batch[future]
                    try:
                        raw_channels, error = future.result()

                        if error:
                            logger.error(f"❌ Batch {batch_num} failed: {error}")
                        else:
                            # Process and store each channel
                            for channel_data in raw_channels:
                                processed_data = process_channel_data(channel_data)
                                insert_channel_metadata(
                                    conn, processed_data, quota_tracker
                                )

                            logger.info(
                                f"✅ Batch {batch_num}/{total_batches} - Processed {len(raw_channels)} channels"
                            )

                        # Update progress
                        progress.advance(task)

                    except Exception as e:
                        logger.error(f"❌ Error processing batch {batch_num}: {e}")
                        progress.advance(task)

            # Rate limiting: wait between batch groups to avoid hitting Google's rate limits
            if group_start + MAX_PARALLEL_BATCHES < len(batches):
                logger.info(
                    f"⏳ Rate limiting: waiting {RATE_LIMIT_DELAY} second(s) before next batch group..."
                )
                time.sleep(RATE_LIMIT_DELAY)

    # Display completion status
    final_quota_status = quota_tracker.get_quota_status()
    final_channels_needing_metadata = get_channels_without_metadata(conn)

    channels_processed = len(channel_ids) - len(final_channels_needing_metadata)
    quota_used = final_quota_status["used"] - quota_status["used"]

    completion_panel = Panel(
        f"[green]✅ Channel metadata fetching complete![/green]\n\n"
        f"[bold]Results:[/bold]\n"
        f"• Channels processed: {channels_processed}\n"
        f"• Channels still needing metadata: {len(final_channels_needing_metadata)}\n"
        f"• Quota used: {quota_used} units\n"
        f"• Remaining quota: {final_quota_status['remaining']:,} units\n"
        f"• Processing efficiency: {channels_processed / max(1, quota_used):.1f} channels per unit\n\n"
        f"[blue]Performance:[/blue]\n"
        f"• Parallel processing: {MAX_PARALLEL_BATCHES} batches simultaneously\n"
        f"• Rate limiting: {RATE_LIMIT_DELAY} second(s) between batch groups\n"
        f"• Total batches processed: {total_batches}\n\n"
        f"[blue]Next steps:[/blue]\n"
        f"• Run the main application to view channels with metadata\n"
        f"• Use command 'm' to see detailed channel information",
        title="[bold green]Complete[/bold green]",
        border_style="green",
    )
    console.print(completion_panel)

    conn.close()
    return True


def main():
    """Main function."""
    try:
        success = fetch_all_channel_metadata()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
