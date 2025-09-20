#!/usr/bin/env python3
"""
Fetch content types for all channels with unknown content type.

This script analyzes YouTube channels to determine if they primarily offer
short-form or long-form content by examining video durations.
"""

import sys
import os
import time
from typing import List, Dict

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database import (
    connect_db,
    get_channels_needing_content_analysis,
    save_content_analysis_result,
    get_content_analysis_stats,
)
from src.youtube_api import authenticate_youtube
from src.content_analyzer import ContentAnalyzer
from src.quota_tracker import QuotaTracker
from src.ui import console


def estimate_quota_consumption(
    channel_count: int, avg_videos_per_channel: int = 200
) -> Dict:
    """
    Estimate API quota consumption for content analysis.

    Args:
        channel_count: Number of channels to analyze
        avg_videos_per_channel: Average number of videos per channel

    Returns:
        Dictionary with quota estimates
    """
    # API calls per channel:
    # 1. channels.list (get uploads playlist) = 1 unit
    # 2. playlistItems.list (get video IDs) = ceil(videos/50) units
    # 3. videos.list (get durations) = ceil(videos/50) units

    calls_per_channel = 1 + 2 * ((avg_videos_per_channel + 49) // 50)  # Round up
    total_calls = channel_count * calls_per_channel

    return {
        "channels": channel_count,
        "avg_videos_per_channel": avg_videos_per_channel,
        "calls_per_channel": calls_per_channel,
        "total_calls": total_calls,
        "estimated_hours": total_calls / 10000,  # Assuming 10k units per hour
    }


def fetch_content_types_for_all_channels(
    limit: int = 5, batch_size: int = 10, auto_confirm: bool = False
):
    """
    Fetch content types for all channels with unknown content type.

    Args:
        limit: Maximum number of channels to process (None for all)
        batch_size: Number of channels to process in each batch
        auto_confirm: Skip interactive prompts (useful for automation)
    """
    console.print("\n[bold cyan]🎬 Content Type Analysis Tool[/bold cyan]")
    console.print("=" * 60)

    # Connect to database
    conn = connect_db()
    if not conn:
        console.print("[red]❌ Failed to connect to database[/red]")
        return

    # Get channels needing analysis
    console.print("📊 Getting channels needing content analysis...")
    channels = get_channels_needing_content_analysis(conn, limit)

    if not channels:
        console.print("[green]✅ All channels already have content analysis![/green]")
        conn.close()
        return

    console.print(f"Found [yellow]{len(channels)}[/yellow] channels needing analysis")

    # Show quota estimate
    estimate = estimate_quota_consumption(len(channels))
    console.print(f"\n[bold yellow]⚠️  Quota Estimate:[/bold yellow]")
    console.print(f"  • Channels to analyze: {estimate['channels']}")
    console.print(f"  • Avg videos per channel: {estimate['avg_videos_per_channel']}")
    console.print(f"  • API calls per channel: {estimate['calls_per_channel']}")
    console.print(f"  • Total API calls: {estimate['total_calls']}")
    console.print(f"  • Estimated time: {estimate['estimated_hours']:.1f} hours")

    # Ask for confirmation
    console.print(f"\n[bold red]This will consume significant API quota![/bold red]")

    if auto_confirm:
        console.print("[yellow]Auto-confirming due to --auto-confirm flag[/yellow]")
        response = "y"
    else:
        try:
            response = input("Continue? (y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Operation cancelled (no input available)[/yellow]")
            conn.close()
            return

    if response != "y":
        console.print("[yellow]Operation cancelled[/yellow]")
        conn.close()
        return

    # Authenticate with YouTube
    console.print("\n🔐 Authenticating with YouTube API...")
    youtube = authenticate_youtube()
    if not youtube:
        console.print("[red]❌ Failed to authenticate with YouTube API[/red]")
        conn.close()
        return

    console.print("[green]✅ Successfully authenticated[/green]")

    # Initialize analyzer and quota tracker
    quota_tracker = QuotaTracker()
    analyzer = ContentAnalyzer(quota_tracker, youtube)

    # Process channels in batches
    total_channels = len(channels)
    processed = 0
    successful = 0
    failed = 0

    console.print(f"\n🚀 Starting analysis of {total_channels} channels...")
    console.print(f"Processing in batches of {batch_size}")

    start_time = time.time()

    for i in range(0, total_channels, batch_size):
        batch = channels[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_channels + batch_size - 1) // batch_size

        console.print(f"\n[bold blue]📦 Batch {batch_num}/{total_batches}[/bold blue]")
        console.print(f"Processing channels {i+1}-{min(i+batch_size, total_channels)}")

        for j, channel in enumerate(batch):
            channel_num = i + j + 1
            console.print(
                f"\n[{channel_num}/{total_channels}] Analyzing: {channel['channel_title']}"
            )
            console.print(f"  Channel ID: {channel['youtube_channel_id']}")
            console.print(f"  Subscribers: {channel['subscriber_count']:,}")
            console.print(f"  Videos: {channel['video_count']:,}")

            try:
                # Analyze the channel
                result = analyzer.analyze_channel_content(channel["youtube_channel_id"])

                if result:
                    # Save to database
                    if save_content_analysis_result(conn, result):
                        console.print(
                            f"  [green]✅ {result.content_type} ({result.shorts_percentage:.1f}% shorts)[/green]"
                        )
                        successful += 1
                    else:
                        console.print(f"  [red]❌ Failed to save to database[/red]")
                        failed += 1
                else:
                    console.print(f"  [red]❌ Analysis failed[/red]")
                    failed += 1

            except Exception as e:
                console.print(f"  [red]❌ Error: {str(e)}[/red]")
                failed += 1

            processed += 1

            # Show progress
            progress = (processed / total_channels) * 100
            console.print(f"  Progress: {progress:.1f}% ({processed}/{total_channels})")

            # Small delay to avoid rate limiting
            time.sleep(0.5)

        # Show batch summary
        console.print(f"\n[bold green]✅ Batch {batch_num} completed[/bold green]")
        console.print(f"  Successful: {successful}")
        console.print(f"  Failed: {failed}")

        # Show quota status
        quota_status = quota_tracker.get_quota_status()
        console.print(f"  Quota used: {quota_status['used']}/{quota_status['limit']}")

        # Check if we should continue
        if quota_status["remaining"] < 1000:  # Less than 1000 units remaining
            console.print(
                f"\n[bold red]⚠️  Low quota remaining ({quota_status['remaining']} units)[/bold red]"
            )
            if auto_confirm:
                console.print(
                    "[yellow]Auto-stopping due to low quota and --auto-confirm flag[/yellow]"
                )
                break
            else:
                try:
                    response = (
                        input("Continue with remaining channels? (y/N): ")
                        .strip()
                        .lower()
                    )
                    if response != "y":
                        console.print(
                            "[yellow]Stopping analysis due to low quota[/yellow]"
                        )
                        break
                except (EOFError, KeyboardInterrupt):
                    console.print(
                        "\n[yellow]Stopping analysis due to low quota (no input available)[/yellow]"
                    )
                    break

    # Final summary
    end_time = time.time()
    duration = end_time - start_time

    console.print(f"\n[bold cyan]🎉 Analysis Complete![/bold cyan]")
    console.print("=" * 60)
    console.print(f"Total channels processed: {processed}")
    console.print(f"Successful analyses: {successful}")
    console.print(f"Failed analyses: {failed}")
    console.print(f"Duration: {duration/60:.1f} minutes")

    # Show final quota status
    quota_status = quota_tracker.get_quota_status()
    console.print(f"\nQuota Usage:")
    console.print(f"  Used: {quota_status['used']}")
    console.print(f"  Remaining: {quota_status['remaining']}")
    console.print(f"  Warning Level: {quota_tracker.get_quota_warning_level()}")

    # Show updated stats
    console.print(f"\nUpdated Content Analysis Stats:")
    stats = get_content_analysis_stats(conn)
    console.print(f"  Total channels: {stats.get('total_channels', 0)}")
    console.print(f"  Analyzed channels: {stats.get('analyzed_channels', 0)}")
    console.print(f"  Unknown channels: {stats.get('unknown_channels', 0)}")

    by_type = stats.get("by_content_type", {})
    for content_type, count in by_type.items():
        console.print(f"  {content_type}: {count}")

    conn.close()


def main():
    """Main function with command line argument support."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch content types for YouTube channels"
    )
    parser.add_argument(
        "--limit", type=int, help="Maximum number of channels to process"
    )
    parser.add_argument(
        "--batch-size", type=int, default=10, help="Number of channels per batch"
    )
    parser.add_argument(
        "--auto-confirm",
        action="store_true",
        help="Skip interactive prompts (useful for automation)",
    )

    args = parser.parse_args()

    try:
        fetch_content_types_for_all_channels(
            args.limit, args.batch_size, args.auto_confirm
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Analysis interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]❌ Unexpected error: {e}[/red]")


if __name__ == "__main__":
    main()
