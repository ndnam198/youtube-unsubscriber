YouTube Subscription Manager
A Python script to list all your YouTube subscriptions and selectively unsubscribe from channels.

⚠️ Important Note on API Quotas
The YouTube Data API has a daily usage limit called a "quota."

Listing subscriptions is very cheap (1 quota unit per page of 50 channels).

Unsubscribing is very expensive (50 quota units per channel).

You have a free quota of 10,000 units per day. This means you can unsubscribe from a maximum of 200 channels per day (10000 / 50 = 200). If you have more than 200 channels to remove, you will need to run the script again the next day.

Setup Instructions
Step 1: Prerequisites
Install Python: Ensure you have Python 3.8 or newer installed.

Install uv: uv is a very fast Python package manager. If you don't have it, install it with:

pip install uv

Step 2: Get Your YouTube API Credentials
You need to authorize this script to manage your YouTube account.

Go to the Google Cloud Console: https://console.cloud.google.com/

Create a new project: If you don't have one, click the project selector at the top and create a "New Project". Give it a name like "YouTube Manager".

Enable the YouTube API:

In the search bar at the top, search for "YouTube Data API v3" and select it.

Click the "ENABLE" button.

Configure the OAuth Consent Screen:

From the navigation menu (☰), go to APIs & Services > OAuth consent screen.

Select "External" for the User Type and click "CREATE".

Fill in the required fields:

App name: YouTube Unsubscriber Script (or any name)

User support email: Your email address

Developer contact information: Your email address

Click "SAVE AND CONTINUE" through the "Scopes" and "Test users" pages. You don't need to add anything here. Finally, click "BACK TO DASHBOARD".

Create Credentials:

Go to APIs & Services > Credentials.

Click "+ CREATE CREDENTIALS" and select "OAuth client ID".

For Application type, select "Desktop app".

Give it a name, like "Desktop Client 1".

Click "CREATE".

Download the Credentials File:

A popup will show your Client ID and Secret. Click "DOWNLOAD JSON".

IMPORTANT: Rename the downloaded file to client_secret.json and place it in the same directory as the main.py script.

Step 3: Install Project Dependencies
Open your terminal in the project directory.

Create a virtual environment using uv:

uv venv

Activate the environment:

On macOS/Linux: source .venv/bin/activate

On Windows: .venv\Scripts\activate

Install the required libraries using uv:

uv pip install -r requirements.txt

(Note: uv can read the dependencies from a requirements.txt file, which it understands from the pyproject.toml.) If that command gives you trouble, you can install them directly:

uv pip install google-api-python-client google-auth-oauthlib

How to Run the Script
Activate the virtual environment if you haven't already.

Run the script from your terminal:

python main.py

First-time Authorization: The first time you run it, a new tab will open in your web browser.

Log in to the Google Account you want to manage.

You will see a "Google hasn’t verified this app" warning. This is normal because it's your own personal script. Click "Advanced" and then "Go to [Your App Name] (unsafe)".

Grant the script permission to manage your YouTube account.

After you approve, you can close the browser tab. A token.json file will be created. You won't have to do this again unless you delete that file.

Follow the Prompts: The script will fetch all your subscriptions and then ask you one by one if you want to unsubscribe.

y = yes, unsubscribe

n = no, keep subscription

q = quit the selection process and proceed with unsubscribing the ones you've already selected.