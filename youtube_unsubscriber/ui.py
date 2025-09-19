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


def print_subscription_report(conn):
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


def print_welcome_banner():
    """Prints the welcome banner."""
    welcome_panel = Panel(
        "[bold blue]YouTube Subscription Manager[/bold blue]\n"
        "[dim]Manage your YouTube subscriptions with PostgreSQL database integration[/dim]",
        title="🎬 Welcome",
        border_style="blue"
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
        border_style="red"
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
        border_style="green"
    )
    console.print(success_panel)
