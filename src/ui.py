"""
User interface components for YouTube Subscription Manager.
"""

import sys
import termios
import tty
from rich.console import Console
from rich.panel import Panel
import logging

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

    from .database import get_subscription_stats

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
        "[green]p[/green] - Print all subscriptions from the database\n"
        "[blue]f[/blue] - Force refetch all subscriptions from YouTube and update the database\n"
        "[red]r[/red] - Run the unsubscription process for channels marked 'TO_BE_UNSUBSCRIBED'\n"
        "[magenta]s[/magenta] - Show subscription statistics report\n"
        "[cyan]q[/cyan] - Show quota status and remaining capacity\n"
        "[purple]m[/purple] - Show channels with detailed metadata (subscribers, videos, topics)\n"
        "[orange]u[/orange] - Update channel metadata for channels missing it\n"
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
    quota_info = f"[bold]Daily Quota Usage:[/bold]\n"
    quota_info += f"Used: {status['used']:,} / {status['limit']:,} units ({status['percentage_used']:.1f}%)\n"
    quota_info += f"Remaining: {status['remaining']:,} units\n\n"

    quota_info += f"[bold]Unsubscription Capacity:[/bold]\n"
    quota_info += f"Max unsubscriptions today: {max_unsubs}\n"
    quota_info += f"Cost per unsubscription: 50 units\n\n"

    # Add daily usage breakdown
    if status["daily_usage"]:
        quota_info += f"[bold]Today's API Calls:[/bold]\n"
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
