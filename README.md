# YouTube Subscription Manager

A Python script to manage your YouTube subscriptions with PostgreSQL database integration. List all your subscriptions, review them in a database, and selectively unsubscribe from channels.

## ⚠️ Important Note on API Quotas

The YouTube Data API has a daily usage limit called a "quota."

- **Listing subscriptions** is very cheap (1 quota unit per page of 50 channels)
- **Unsubscribing** is very expensive (50 quota units per channel)

You have a free quota of 10,000 units per day. This means you can unsubscribe from a maximum of 200 channels per day (10000 / 50 = 200). If you have more than 200 channels to remove, you will need to run the script again the next day.

## Prerequisites

- **Python 3.8+** installed on your system
- **Docker** installed for running PostgreSQL
- **uv** (Python package manager) - install with: `pip install uv`

## Setup Instructions

### Step 1: Set Up PostgreSQL Database with Docker

1. **Start PostgreSQL container:**

   ```bash
   docker run --name youtube-postgres \
     -e POSTGRES_PASSWORD=password \
     -e POSTGRES_DB=youtube_subscriptions \
     -p 5432:5432 \
     -d postgres:15
   ```

2. **Run automated database setup:**

   ```bash
   python setup_database.py
   ```

   This script will:
   - Create the database if it doesn't exist
   - Set up the initial subscriptions table
   - Run migration to add the channels table
   - Create all necessary indexes and constraints
   - Verify the setup is complete

3. **Alternative: Manual setup (if automated setup fails):**

   ```bash
   # Copy schema file to container
   docker cp schema/schema.sql youtube-postgres:/schema.sql
   
   # Create complete database schema
   docker exec -it youtube-postgres psql -U postgres -d youtube_subscriptions -f /schema.sql
   ```

4. **Test the database connection:**

   ```bash
   # Connect to the database to verify it's working
   docker exec -it youtube-postgres psql -U postgres -d youtube_subscriptions
   
   # In the PostgreSQL prompt, run:
   \dt
   # You should see both 'subscriptions' and 'channels' tables
   
   # Exit with:
   \q
   ```

### Step 2: Get Your YouTube API Credentials

1. **Go to the Google Cloud Console:** <https://console.cloud.google.com/>

2. **Create a new project:**
   - Click the project selector at the top
   - Create a "New Project" named "YouTube Manager"

3. **Enable the YouTube API:**
   - Search for "YouTube Data API v3" in the search bar
   - Select it and click "ENABLE"

4. **Configure the OAuth Consent Screen:**
   - Go to APIs & Services > OAuth consent screen
   - Select "External" for User Type and click "CREATE"
   - Fill in required fields:
     - App name: YouTube Unsubscriber Script
     - User support email: Your email address
     - Developer contact information: Your email address
   - Click "SAVE AND CONTINUE" through all pages

5. **Create Credentials:**
   - Go to APIs & Services > Credentials
   - Click "+ CREATE CREDENTIALS" > "OAuth client ID"
   - Select "Desktop app" as Application type
   - Name it "Desktop Client 1"
   - Click "CREATE"

6. **Download the Credentials File:**
   - Click "DOWNLOAD JSON" in the popup
   - **Rename the file to `client_secret.json`**
   - Place it in the same directory as `main.py`

### Step 3: Install Project Dependencies

1. **Create and activate virtual environment:**

   ```bash
   # Create virtual environment
   uv venv
   
   # Activate it
   # On macOS/Linux:
   source .venv/bin/activate
   
   # On Windows:
   .venv\Scripts\activate
   ```

2. **Install dependencies:**

   ```bash
   uv pip install -e .
   ```

### Step 4: Configure Environment Variables

The application uses environment variables for configuration. A `.env` file is provided with default values:

```bash
# YouTube API Configuration
CLIENT_SECRETS_FILE=client_secret.json
SCOPES=https://www.googleapis.com/auth/youtube
API_SERVICE_NAME=youtube
API_VERSION=v3
TOKEN_FILE=token.pickle

# Database Configuration
DB_NAME=youtube_subscriptions
DB_USER=postgres
DB_PASSWORD=password
DB_HOST=localhost
DB_PORT=5432
```

**Important:** The `.env` file is already created with default values. You can modify these values as needed for your setup. The `.env` file is excluded from version control for security.

## How to Run the Script

1. **Activate the virtual environment:**

   ```bash
   source .venv/bin/activate  # macOS/Linux
   # or
   .venv\Scripts\activate     # Windows
   ```

2. **Run the script:**

   ```bash
   # Option 1: Using the run script
   python run.py
   
   # Option 2: As a module
   python -m youtube_unsubscriber.main
   
   # Option 3: After installation (if installed with pip)
   youtube-unsubscriber
   ```

3. **Fetch channel metadata (optional but recommended):**

   ```bash
   # Fetch detailed metadata for all channels
   python fetch_channel_metadata.py
   ```

4. **First-time Authorization:**
   - A browser tab will open for Google authentication
   - Log in to your Google Account
   - Click "Advanced" > "Go to [Your App Name] (unsafe)" when prompted
   - Grant permission to manage your YouTube account
   - Close the browser tab after approval

5. **Initial Setup:**
   - The script will automatically fetch all your subscriptions
   - Data will be stored in the PostgreSQL database
   - You'll see a message when fetching is complete

## Using the Application

The script runs in an interactive mode with the following commands:

- **`p`** - Print all subscriptions from the database
- **`f`** - Force refetch all subscriptions from YouTube and update the database
- **`r`** - Run unsubscription process for channels marked as 'TO_BE_UNSUBSCRIBED'
- **`q`** - Quit the program

### Workflow

1. **Review subscriptions:** Use `p` to see all your subscriptions
2. **Mark for removal:** Use a database client (like pgAdmin, DBeaver, or psql) to change the `status` column to `TO_BE_UNSUBSCRIBED` for channels you want to remove
3. **Execute removal:** Use `r` to unsubscribe from all marked channels

### Database Schema

The `subscriptions` table includes:

- `id` - Primary key
- `youtube_channel_id` - YouTube channel ID
- `youtube_subscription_id` - Subscription ID (used for unsubscribing)
- `channel_name` - Display name of the channel
- `channel_link` - Direct link to the channel
- `subscription_date` - When you subscribed
- `status` - Current status: `SUBSCRIBED`, `TO_BE_UNSUBSCRIBED`, or `UNSUBSCRIBED`

## Troubleshooting

### Database Connection Issues

- Ensure Docker container is running: `docker ps`
- Check if PostgreSQL is accessible: `docker exec -it youtube-postgres psql -U postgres -d youtube_subscriptions`

### API Quota Exceeded

- Wait 24 hours for quota reset
- Check your quota usage in Google Cloud Console

### Authentication Issues

- Delete `token.pickle` and re-run the script
- Ensure `client_secret.json` is in the correct location

## Package Structure

The project has been refactored into a clean, modular structure:

```bash
youtube_unsubscriber/
├── __init__.py          # Package initialization
├── main.py              # Main application logic
├── config.py            # Configuration management
├── database.py          # Database operations
├── youtube_api.py       # YouTube API operations
├── ui.py               # User interface components
├── quota_tracker.py    # API quota tracking and management
└── channel_fetcher.py  # Channel metadata fetching and processing
```

### Module Responsibilities

- **`config.py`**: Manages all configuration settings and environment variables
- **`database.py`**: Handles all PostgreSQL database operations
- **`youtube_api.py`**: YouTube API authentication and operations
- **`ui.py`**: User interface components and Rich console formatting
- **`quota_tracker.py`**: YouTube API quota tracking and management
- **`channel_fetcher.py`**: Channel metadata fetching and processing
- **`main.py`**: Main application entry point and orchestration

## API Quota Tracking

The application now includes intelligent quota tracking to help you manage your YouTube API usage:

### Features

- **Real-time quota monitoring** - Tracks your daily API usage
- **Smart calculations** - Shows exactly how many channels you can unsubscribe from
- **Warning system** - Alerts when approaching quota limits
- **Persistent tracking** - Remembers usage across sessions

### Quota Costs

- **Fetching subscriptions**: 1 unit per request
- **Unsubscribing from channel**: 50 units per request
- **Daily limit**: 10,000 units

### Commands

- **`q`** - Show detailed quota status and remaining capacity
- **`s`** - Show subscription report with quota information

### Quota Warnings

- **🟢 OK** (0-50%): Normal usage
- **🔵 INFO** (50-75%): Moderate usage
- **🟡 WARNING** (75-90%): High usage - be careful
- **🔴 CRITICAL** (90%+): Very high usage - consider stopping

## Channel Metadata Enhancement

The application now fetches and stores detailed channel metadata to help you make better decisions about which channels to unsubscribe from:

### Available Information

#### ✅ **Retrievable Data:**

- **`subscriber_count`** - Number of subscribers
- **`video_count`** - Total videos uploaded
- **`view_count`** - Total views across all videos
- **`description`** - Channel description text
- **`country`** - Channel's country
- **`custom_url`** - Channel's custom URL (e.g., @channelname)
- **`published_at`** - When the channel was created
- **`thumbnail_url`** - Channel thumbnail image
- **`topic_ids`** - YouTube topic categories (e.g., Education, Gaming, Music)

#### ❌ **Not Available:**

- **`last_action_time`** - YouTube API doesn't provide last activity time
- **Custom content tags** - Only YouTube's topic IDs are available, not descriptive tags

### Database Schema Changes

The new `channels` table stores this metadata with a foreign key relationship to the `subscriptions` table:

```sql
-- The complete schema is now in schema/schema.sql
\i schema/schema.sql
```

### New Commands

- **`m`** - Show channels with detailed metadata (subscribers, videos, topics)
- **`u`** - Update channel metadata for channels missing it

### Quota Impact

- **Fetching channel metadata**: 1 unit per request (up to 50 channels per request)
- **Automatic fetching**: Happens on first run and when using the `u` command

## Available Scripts

### Main Application

- **`run.py`** - Main application entry point
- **`python -m src.main`** - Run as module
- **`youtube-unsubscriber`** - Run as installed command

### Database Management

- **`setup_database.py`** - Automated database setup
- **`schema/schema.sql`** - Complete database schema (subscriptions + channels tables)

### Channel Metadata

- **`fetch_channel_metadata.py`** - Standalone script to fetch channel metadata

### Development Tools

- **`scripts/lint.py`** - Development tools runner (format, lint, check)
- **`scripts/setup-dev.py`** - Complete development environment setup
- **`.black`** - Black code formatter configuration
- **`pylintrc`** - Pylint code quality checker configuration

## Development

### Prerequisites for Development

- Python 3.9+
- uv package manager

### Setup Development Environment

#### Quick Setup (Recommended)

```bash
# Complete development environment setup
python scripts/setup-dev.py
```

#### Manual Setup

```bash
# Install dependencies including dev tools
uv sync --dev

# Install pre-commit hooks
uv run pre-commit install

# Test configuration
uv run black --config=.black --check src/
uv run pylint --rcfile=.pylintrc --version
```

### Development Tools Runner

```bash
# Format code
python scripts/lint.py format

# Check formatting
python scripts/lint.py check

# Run linting
python scripts/lint.py lint

# Run all checks
python scripts/lint.py all

# Or use uv directly with config files
uv run black --config=.black src/
uv run pylint --rcfile=pylintrc src/

# Pre-commit hooks (runs automatically on git commit)
uv run pre-commit run --all-files
```

### Code Quality

- **Black**: Code formatting (line length: 88) - configured in `.black`
- **Pylint**: Code analysis and quality checks - configured in `.pylintrc`
- **Pre-commit**: Automatic formatting and linting on git commit
- **Configuration**: Separate config files for better isolation

### Usage Examples

```bash
# Complete setup from scratch
python setup_database.py
python fetch_channel_metadata.py
python run.py

# Just fetch metadata for existing setup
python fetch_channel_metadata.py

# Run main application
python run.py
```

## Stopping the Database

When you're done, stop the PostgreSQL container:

```bash
docker stop youtube-postgres
docker rm youtube-postgres
```
