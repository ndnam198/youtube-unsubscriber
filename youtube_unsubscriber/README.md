# YouTube Subscription Manager - Package Structure

This package has been refactored for better maintainability and readability.

## Package Structure

```
youtube_unsubscriber/
├── __init__.py          # Package initialization
├── main.py              # Main application logic
├── config.py            # Configuration management
├── database.py          # Database operations
├── youtube_api.py       # YouTube API operations
└── ui.py               # User interface components
```

## Module Responsibilities

### `config.py`
- Manages all configuration settings
- Loads environment variables from `.env` file
- Centralizes all configuration constants

### `database.py`
- Handles all PostgreSQL database operations
- Connection management
- CRUD operations for subscriptions
- Statistics and reporting functions

### `youtube_api.py`
- YouTube API authentication
- Fetching subscriptions from YouTube
- Unsubscribing from channels
- API error handling

### `ui.py`
- User interface components
- Rich console formatting
- Input handling
- Display panels and reports

### `main.py`
- Main application entry point
- Orchestrates the application flow
- Command loop management

## Usage

### As a Package
```bash
python -m youtube_unsubscriber.main
```

### As a Script
```bash
python run.py
```

### As an Installed Command
```bash
youtube-unsubscriber
```

## Benefits of Refactoring

1. **Separation of Concerns**: Each module has a single responsibility
2. **Maintainability**: Easier to modify and extend individual components
3. **Testability**: Each module can be tested independently
4. **Reusability**: Components can be imported and used elsewhere
5. **Readability**: Code is organized logically and is easier to understand
