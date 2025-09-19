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

2. **Create the database schema:**
   ```bash
   # Copy the schema to the container
   docker cp schema.sql youtube-postgres:/schema.sql
   
   # Execute the schema to create tables
   docker exec -it youtube-postgres psql -U postgres -d youtube_subscriptions -f /schema.sql
   ```

3. **Test the database connection:**
   ```bash
   # Connect to the database to verify it's working
   docker exec -it youtube-postgres psql -U postgres -d youtube_subscriptions
   
   # In the PostgreSQL prompt, run:
   \dt
   # You should see the 'subscriptions' table
   
   # Exit with:
   \q
   ```

### Step 2: Get Your YouTube API Credentials

1. **Go to the Google Cloud Console:** https://console.cloud.google.com/

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
   python main.py
   ```

3. **First-time Authorization:**
   - A browser tab will open for Google authentication
   - Log in to your Google Account
   - Click "Advanced" > "Go to [Your App Name] (unsafe)" when prompted
   - Grant permission to manage your YouTube account
   - Close the browser tab after approval

4. **Initial Setup:**
   - The script will automatically fetch all your subscriptions
   - Data will be stored in the PostgreSQL database
   - You'll see a message when fetching is complete

## Using the Application

The script runs in an interactive mode with the following commands:

- **`p`** - Print all subscriptions from the database
- **`f`** - Force refetch all subscriptions from YouTube and update the database
- **`r`** - Run unsubscription process for channels marked as 'TO_BE_UNSUBSCRIBED'
- **`q`** - Quit the program

### Workflow:

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

## Stopping the Database

When you're done, stop the PostgreSQL container:

```bash
docker stop youtube-postgres
docker rm youtube-postgres
```