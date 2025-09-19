#!/usr/bin/env python3
"""
Database setup and migration script.
This script handles the complete database setup including migration to add channels table.
"""

import os
import sys
import subprocess
import psycopg2
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT

console = Console()


def run_sql_file(conn, sql_file):
    """Run a SQL file against the database."""
    try:
        with open(sql_file, 'r') as f:
            sql_content = f.read()
        
        with conn.cursor() as cur:
            cur.execute(sql_content)
        conn.commit()
        return True
    except Exception as e:
        console.print(f"[red]Error running {sql_file}: {e}[/red]")
        return False


def check_database_exists():
    """Check if the database exists."""
    try:
        # Connect to default postgres database to check if our database exists
        conn = psycopg2.connect(
            dbname="postgres",
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
        )
        
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (DB_NAME,))
            exists = cur.fetchone() is not None
        
        conn.close()
        return exists
    except Exception as e:
        console.print(f"[red]Error checking database: {e}[/red]")
        return False


def create_database():
    """Create the database if it doesn't exist."""
    try:
        # Connect to default postgres database
        conn = psycopg2.connect(
            dbname="postgres",
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
        )
        conn.autocommit = True
        
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE {DB_NAME};")
        
        conn.close()
        return True
    except psycopg2.errors.DuplicateDatabase:
        # Database already exists, that's fine
        return True
    except Exception as e:
        console.print(f"[red]Error creating database: {e}[/red]")
        return False


def check_tables_exist(conn):
    """Check if the required tables exist."""
    try:
        with conn.cursor() as cur:
            # Check for subscriptions table
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'subscriptions'
                );
            """)
            subscriptions_exists = cur.fetchone()[0]
            
            # Check for channels table
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'channels'
                );
            """)
            channels_exists = cur.fetchone()[0]
            
            return subscriptions_exists, channels_exists
    except Exception as e:
        console.print(f"[red]Error checking tables: {e}[/red]")
        return False, False


def main():
    """Main setup function."""
    
    # Display welcome banner
    welcome_panel = Panel(
        "[bold blue]Database Setup & Migration[/bold blue]\n"
        "[dim]Setting up PostgreSQL database with channels table[/dim]",
        title="🗄️ Database Setup",
        border_style="blue"
    )
    console.print(welcome_panel)
    
    # Step 1: Check if database exists
    console.print("\n[bold]Step 1:[/bold] Checking database...")
    if not check_database_exists():
        console.print("[yellow]Database doesn't exist. Creating...[/yellow]")
        if not create_database():
            console.print("[red]Failed to create database. Exiting.[/red]")
            return False
        console.print("[green]✅ Database created successfully![/green]")
    else:
        console.print("[green]✅ Database exists![/green]")
    
    # Step 2: Connect to the database
    console.print("\n[bold]Step 2:[/bold] Connecting to database...")
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
        )
        console.print("[green]✅ Connected to database![/green]")
    except Exception as e:
        console.print(f"[red]Failed to connect to database: {e}[/red]")
        return False
    
    # Step 3: Check existing tables
    console.print("\n[bold]Step 3:[/bold] Checking existing tables...")
    subscriptions_exists, channels_exists = check_tables_exist(conn)
    
    if subscriptions_exists:
        console.print("[green]✅ Subscriptions table exists![/green]")
    else:
        console.print("[yellow]⚠️ Subscriptions table doesn't exist![/yellow]")
    
    if channels_exists:
        console.print("[green]✅ Channels table exists![/green]")
    else:
        console.print("[yellow]⚠️ Channels table doesn't exist![/yellow]")
    
    # Step 4: Create complete schema if tables don't exist
    if not subscriptions_exists or not channels_exists:
        console.print("\n[bold]Step 4:[/bold] Creating complete database schema...")
        if not run_sql_file(conn, "schema/schema.sql"):
            console.print("[red]Failed to create database schema. Exiting.[/red]")
            conn.close()
            return False
        console.print("[green]✅ Database schema created![/green]")
    else:
        console.print("\n[bold]Step 4:[/bold] All tables already exist. Skipping schema creation.")
    
    # Step 5: Verify setup
    console.print("\n[bold]Step 6:[/bold] Verifying setup...")
    subscriptions_exists, channels_exists = check_tables_exist(conn)
    
    if subscriptions_exists and channels_exists:
        # Check migration status
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM check_migration_status();")
                result = cur.fetchone()
                
                if result:
                    total_subs, channels_with_metadata, channels_without_metadata, migration_complete = result
                    
                    status_panel = Panel(
                        f"[bold]Database Status:[/bold]\n"
                        f"Total subscriptions: {total_subs}\n"
                        f"Channels with metadata: {channels_with_metadata}\n"
                        f"Channels without metadata: {channels_without_metadata}\n"
                        f"Migration complete: {'✅ Yes' if migration_complete else '⚠️ No'}\n\n"
                        f"[blue]Next steps:[/blue]\n"
                        f"• Run 'python fetch_channel_metadata.py' to fetch channel metadata\n"
                        f"• Run 'python run.py' to start the main application",
                        title="[bold green]Setup Complete[/bold green]",
                        border_style="green"
                    )
                    console.print(status_panel)
        except Exception as e:
            console.print(f"[yellow]Could not check migration status: {e}[/yellow]")
    
    conn.close()
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Setup cancelled by user.[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        sys.exit(1)
