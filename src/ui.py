"""
User interface components for YouTube Subscription Manager.
"""

import logging
import sys
import termios
import tty
import webbrowser
from datetime import datetime

from rich.console import Console
from rich.panel import Panel

from src.database import (
    get_subscription_stats,
    get_all_channels_with_metadata,
    search_channels_with_metadata,
    get_subscriptions_sorted_by_subscriber_count,
)

logger = logging.getLogger("youtube-unsubscriber")
console = Console()


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


def print_subscription_report(conn, quota_tracker=None):
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
    for status in ["SUBSCRIBED", "TO_BE_UNSUBSCRIBED", "UNSUBSCRIBED"]:
        count = stats["by_status"].get(status, 0)
        if status == "SUBSCRIBED":
            color = "green"
            icon = "✅"
        elif status == "TO_BE_UNSUBSCRIBED":
            color = "yellow"
            icon = "⚠️"
        elif status == "UNSUBSCRIBED":
            color = "red"
            icon = "❌"
        else:
            # Default fallback
            color = "white"
            icon = "❓"

        status_text += (
            "["
            + color
            + "]"
            + icon
            + " "
            + status
            + ": "
            + str(count)
            + "[/"
            + color
            + "]\n"
        )

    # Add quota information if available
    quota_text = ""
    if quota_tracker:
        quota_text = f"\n\n[bold]API Quota Status:[/bold]\n{quota_tracker.get_quota_summary_text()}"

    # Create the report panel
    report_panel = Panel(
        f"[bold blue]Total Subscriptions: {stats['total']}[/bold blue]\n\n"
        f"[bold]Status Breakdown:[/bold]\n"
        f"{status_text.strip()}{quota_text}",
        title="📊 Subscription Report",
        border_style="blue",
    )
    console.print(report_panel)


def print_instructions():
    """Prints the available commands."""
    commands_panel = Panel(
        "[bold cyan]Available Commands:[/bold cyan]\n\n"
        "[blue]f[/blue] - Force refetch all subscriptions from YouTube and update the database\n"
        "[red]r[/red] - Run the unsubscription process for channels marked 'TO_BE_UNSUBSCRIBED'\n"
        "[magenta]s[/magenta] - Show subscription statistics report\n"
        "[cyan]q[/cyan] - Show quota status and remaining capacity\n"
        "[green]e[/green] - Export all channels with metadata to file\n"
        "[purple]h[/purple] - Interactive search channels with live preview\n"
        "[orange]u[/orange] - Update channel metadata for channels missing it\n"
        "[bold red]d[/bold red] - Interactive decision: review each subscription one by one\n"
        "[yellow]x[/yellow] - Quit the program",
        title="[bold]Commands[/bold]",
        border_style="cyan",
    )
    console.print(commands_panel)


def print_welcome_banner():
    """Prints the welcome banner."""
    welcome_panel = Panel(
        "[bold blue]YouTube Subscription Manager[/bold blue]\n"
        "[dim]Manage your YouTube subscriptions with PostgreSQL database integration[/dim]",
        title="🎬 Welcome",
        border_style="blue",
    )
    console.print(welcome_panel)


def print_authentication_error():
    """Prints authentication error panel."""
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


def print_success_panel():
    """Prints the success panel after setup."""
    success_panel = Panel(
        "[green]✅ Setup Complete![/green]\n\n"
        "[blue]Next steps:[/blue]\n"
        "• Review your subscriptions in the database\n"
        "• Set 'status' column to 'TO_BE_UNSUBSCRIBED' for channels to remove\n"
        "• Use the commands below to manage subscriptions",
        title="[bold green]Ready[/bold green]",
        border_style="green",
    )
    console.print(success_panel)


def print_quota_status(quota_tracker):
    """Prints detailed quota status information."""
    if not quota_tracker:
        console.print("[yellow]Quota tracker not available.[/yellow]")
        return

    status = quota_tracker.get_quota_status()
    max_unsubs = quota_tracker.calculate_max_unsubscriptions()
    warning_level = quota_tracker.get_quota_warning_level()

    # Determine panel color based on warning level
    if warning_level == "critical":
        border_color = "red"
        title_color = "red"
    elif warning_level == "warning":
        border_color = "yellow"
        title_color = "yellow"
    else:
        border_color = "blue"
        title_color = "blue"

    # Create detailed quota information
    quota_info = "[bold]Daily Quota Usage:[/bold]\n"
    quota_info += f"Used: {status['used']:,} / {status['limit']:,} units ({status['percentage_used']:.1f}%)\n"
    quota_info += f"Remaining: {status['remaining']:,} units\n\n"

    quota_info += "[bold]Unsubscription Capacity:[/bold]\n"
    quota_info += f"Max unsubscriptions today: {max_unsubs}\n"
    quota_info += "Cost per unsubscription: 50 units\n\n"

    # Add daily usage breakdown
    if status["daily_usage"]:
        quota_info += "[bold]Today's API Calls:[/bold]\n"
        for operation, count in status["daily_usage"].items():
            cost = count * (50 if "delete" in operation else 1)
            quota_info += f"• {operation}: {count} calls ({cost} units)\n"

    # Add warning if approaching limits
    if warning_level in ["warning", "critical"]:
        quota_info += f"\n[bold {warning_level}]{'⚠️ WARNING' if warning_level == 'warning' else '🚨 CRITICAL'}: "
        quota_info += f"You are using {status['percentage_used']:.1f}% of your daily quota![/bold {warning_level}]"

    quota_panel = Panel(
        quota_info,
        title=f"[bold {title_color}]📊 API Quota Status[/bold {title_color}]",
        border_style=border_color,
    )
    console.print(quota_panel)


def export_all_channels_to_file(conn):
    """Export all channels with metadata to a file."""
    if not conn:
        console.print("[yellow]Database connection not available.[/yellow]")
        return

    try:
        # Get all channels with metadata
        channels = get_all_channels_with_metadata(conn)

        if not channels:
            console.print("[yellow]No channels found in database.[/yellow]")
            return

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"subscription_export_{timestamp}.txt"

        # Write to file
        with open(filename, "w", encoding="utf-8") as f:
            f.write("YouTube Subscription Export\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Channels: {len(channels)}\n")
            f.write("=" * 80 + "\n\n")

            for channel in channels:
                f.write(f"Channel: {channel['channel_title']}\n")
                f.write(f"ID: {channel['youtube_channel_id']}\n")
                f.write(f"Status: {channel['status']}\n")
                f.write(f"Subscribers: {channel.get('subscriber_count', 'N/A'):,}\n")
                f.write(f"Videos: {channel.get('video_count', 'N/A'):,}\n")
                f.write(f"Views: {channel.get('view_count', 'N/A'):,}\n")
                f.write(f"Country: {channel.get('country', 'N/A')}\n")
                f.write(f"Description: {channel.get('description', 'N/A')[:200]}...\n")
                f.write(f"Topics: {', '.join(channel.get('topic_ids', []))}\n")
                f.write("-" * 80 + "\n\n")

        console.print(
            f"[green]✅ Exported {len(channels)} channels to {filename}[/green]"
        )

    except Exception as e:
        logger.error(f"Error exporting channels: {e}")
        console.print(f"[red]❌ Error exporting channels: {e}[/red]")


def interactive_search_channels(conn):
    """Interactive search with live preview count."""
    if not conn:
        console.print("[yellow]Database connection not available.[/yellow]")
        return

    console.print("\n[bold cyan]🔍 Interactive Channel Search[/bold cyan]")
    console.print("[dim]Enter search term and press Enter to view results[/dim]")

    # Get search term from user input
    console.print("\n[bold]Enter search term:[/bold] ", end="")
    search_term = input().strip()

    try:
        # Get count first
        count = search_channels_with_metadata(conn, search_term, count_only=True)
        console.print(
            f"[green]Found {count} SUBSCRIBED channels matching '{search_term}'[/green]"
        )

        if count == 0:
            console.print("[yellow]No channels found matching your search.[/yellow]")
            return

        # Get actual results
        results = search_channels_with_metadata(conn, search_term, count_only=False)

        # Display results
        console.print(f"\n[bold green]Found {len(results)} channels:[/bold green]")
        console.print("=" * 80)

        for i, channel in enumerate(results, 1):
            console.print(f"\n[bold]{i}. {channel['channel_title']}[/bold]")
            console.print(f"   ID: {channel['youtube_channel_id']}")
            console.print(f"   Status: {channel['status']}")
            console.print(f"   Subscribers: {channel.get('subscriber_count', 'N/A'):,}")
            console.print(f"   Videos: {channel.get('video_count', 'N/A'):,}")
            console.print(f"   Views: {channel.get('view_count', 'N/A'):,}")
            console.print(f"   Country: {channel.get('country', 'N/A')}")
            console.print(
                f"   Description: {channel.get('description', 'N/A')[:100]}..."
            )

        # Ask if user wants to save results
        console.print(
            f"\n[bold cyan]Save these {len(results)} results to file? (y/n):[/bold cyan] ",
            end="",
        )
        save_choice = input().strip().lower()

        if save_choice == "y":
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"search_result_{timestamp}.txt"

            # Write to file
            with open(filename, "w", encoding="utf-8") as f:
                f.write("YouTube Channel Search Results\n")
                f.write(f"Search Term: '{search_term}'\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total Results: {len(results)}\n")
                f.write("=" * 80 + "\n\n")

                for i, channel in enumerate(results, 1):
                    f.write(f"{i}. {channel['channel_title']}\n")
                    f.write(f"   ID: {channel['youtube_channel_id']}\n")
                    f.write(f"   Status: {channel['status']}\n")
                    f.write(
                        f"   Subscribers: {channel.get('subscriber_count', 'N/A'):,}\n"
                    )
                    f.write(f"   Videos: {channel.get('video_count', 'N/A'):,}\n")
                    f.write(f"   Views: {channel.get('view_count', 'N/A'):,}\n")
                    f.write(f"   Country: {channel.get('country', 'N/A')}\n")
                    f.write(f"   Description: {channel.get('description', 'N/A')}\n")
                    f.write("-" * 80 + "\n\n")

            console.print(f"[green]✅ Search results saved to {filename}[/green]")
        else:
            console.print("[yellow]Results not saved.[/yellow]")

    except Exception as e:
        logger.error(f"Error searching channels: {e}")
        console.print(f"[red]❌ Error searching channels: {e}[/red]")


def interactive_subscription_decision(conn, youtube, quota_tracker):
    """Interactive decision making for each subscription, sorted by subscriber count."""
    if not conn:
        console.print("[yellow]Database connection not available.[/yellow]")
        return

    from src.database import update_subscription_status_in_db

    try:
        # Get all subscriptions sorted by subscriber count
        subscriptions = get_subscriptions_sorted_by_subscriber_count(conn)

        if not subscriptions:
            console.print("[yellow]No subscriptions found in database.[/yellow]")
            return

        console.print(f"\n[bold cyan]🎯 Interactive Subscription Decision[/bold cyan]")
        console.print(
            f"[dim]Reviewing {len(subscriptions)} subscriptions (sorted by subscriber count)[/dim]"
        )
        console.print("\n[bold]Commands:[/bold]")
        console.print("[green]y[/green] - Unsubscribe from this channel")
        console.print("[blue]s[/blue] - Skip (keep subscription)")
        console.print("[purple]o[/purple] - Open channel in browser")
        console.print("[yellow]q[/yellow] - Quit decision process")
        console.print("\n" + "=" * 80)

        unsubscribed_count = 0
        skipped_count = 0

        for i, subscription in enumerate(subscriptions, 1):
            # Display subscription details
            console.print(
                f"\n[bold cyan]📺 Channel {i}/{len(subscriptions)}[/bold cyan]"
            )
            console.print("=" * 60)

            # Channel info
            console.print(f"[bold]Name:[/bold] {subscription['channel_title']}")
            console.print(f"[bold]ID:[/bold] {subscription['youtube_channel_id']}")
            console.print(f"[bold]Status:[/bold] {subscription['status']}")

            # Metadata
            console.print(
                f"[bold]Subscribers:[/bold] {subscription['subscriber_count']:,}"
            )
            console.print(f"[bold]Videos:[/bold] {subscription['video_count']:,}")
            console.print(f"[bold]Views:[/bold] {subscription['view_count']:,}")
            console.print(f"[bold]Country:[/bold] {subscription['country']}")

            # Description (truncated)
            desc = subscription["description"]
            if len(desc) > 200:
                desc = desc[:200] + "..."
            console.print(f"[bold]Description:[/bold] {desc}")

            # Topics
            if subscription["topic_ids"]:
                topics_str = ", ".join(subscription["topic_ids"][:5])
                if len(subscription["topic_ids"]) > 5:
                    topics_str += "..."
                console.print(f"[bold]Topics:[/bold] {topics_str}")

            # Channel link
            if subscription["channel_link"]:
                console.print(f"[bold]Link:[/bold] {subscription['channel_link']}")

            console.print("\n[bold]Decision:[/bold] ", end="")

            # Get user decision
            while True:
                char = get_char()
                console.print(char)

                if char.lower() == "y":
                    # Unsubscribe
                    console.print("[red]Unsubscribing...[/red]")

                    # Update database status first
                    update_subscription_status_in_db(
                        conn,
                        subscription["youtube_subscription_id"],
                        "TO_BE_UNSUBSCRIBED",
                    )

                    # Actually unsubscribe via API
                    from src.youtube_api import unsubscribe_from_channel

                    success = unsubscribe_from_channel(
                        youtube, subscription["youtube_subscription_id"], quota_tracker
                    )

                    if success:
                        update_subscription_status_in_db(
                            conn,
                            subscription["youtube_subscription_id"],
                            "UNSUBSCRIBED",
                        )
                        console.print("[green]✅ Unsubscribed successfully![/green]")
                        unsubscribed_count += 1
                    else:
                        # Revert database status if API call failed
                        update_subscription_status_in_db(
                            conn, subscription["youtube_subscription_id"], "SUBSCRIBED"
                        )
                        console.print(
                            "[red]❌ Failed to unsubscribe. Status reverted.[/red]"
                        )
                    break

                elif char.lower() == "s":
                    # Skip (keep subscription)
                    console.print("[blue]Skipped - keeping subscription[/blue]")
                    skipped_count += 1
                    break

                elif char.lower() == "o":
                    # Open in browser
                    if subscription["channel_link"]:
                        console.print("[purple]Opening channel in browser...[/purple]")
                        webbrowser.open(subscription["channel_link"])
                        console.print("[dim]Press any key to continue...[/dim]")
                        get_char()  # Wait for user to press any key
                    else:
                        console.print("[yellow]No channel link available[/yellow]")
                    console.print("\n[bold]Decision:[/bold] ", end="")
                    continue

                elif char.lower() == "q":
                    # Quit
                    console.print(
                        "\n[yellow]Decision process cancelled by user.[/yellow]"
                    )
                    console.print(
                        f"[dim]Processed {i-1}/{len(subscriptions)} channels[/dim]"
                    )
                    console.print(
                        f"[dim]Unsubscribed: {unsubscribed_count}, Skipped: {skipped_count}[/dim]"
                    )
                    return

                else:
                    console.print(
                        "[yellow]Invalid choice. Use y/s/o/q:[/yellow] ", end=""
                    )
                    continue

        # Summary
        console.print(f"\n[bold green]🎉 Decision process completed![/bold green]")
        console.print(f"[green]Unsubscribed: {unsubscribed_count} channels[/green]")
        console.print(f"[blue]Skipped: {skipped_count} channels[/blue]")
        console.print(f"[dim]Total processed: {len(subscriptions)} channels[/dim]")

    except Exception as e:
        logger.error(f"Error in interactive subscription decision: {e}")
        console.print(f"[red]❌ Error in decision process: {e}[/red]")
