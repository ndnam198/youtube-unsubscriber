"""
YouTube API quota tracking and management.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger("youtube-unsubscriber")

# YouTube API v3 Quota Costs (as of 2024)
# Source: https://developers.google.com/youtube/v3/getting-started#quota
QUOTA_COSTS = {
    'subscriptions.list': 1,      # 1 unit per request
    'subscriptions.delete': 50,   # 50 units per request
    'channels.list': 1,           # 1 unit per request
}

# Daily quota limit for YouTube Data API v3
DAILY_QUOTA_LIMIT = 10000  # 10,000 units per day

QUOTA_FILE = 'quota_usage.json'


class QuotaTracker:
    """Tracks YouTube API quota usage and calculates remaining capacity."""
    
    def __init__(self):
        self.quota_file = QUOTA_FILE
        self.quota_data = self._load_quota_data()
    
    def _load_quota_data(self) -> Dict:
        """Load quota usage data from file."""
        if os.path.exists(self.quota_file):
            try:
                with open(self.quota_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Could not load quota data: {e}")
        
        # Initialize with default data
        return {
            'daily_usage': {},
            'total_used_today': 0,
            'last_reset': datetime.now().isoformat()
        }
    
    def _save_quota_data(self):
        """Save quota usage data to file."""
        try:
            with open(self.quota_file, 'w') as f:
                json.dump(self.quota_data, f, indent=2)
        except IOError as e:
            logger.error(f"Could not save quota data: {e}")
    
    def _reset_daily_quota_if_needed(self):
        """Reset daily quota if a new day has started."""
        now = datetime.now()
        last_reset = datetime.fromisoformat(self.quota_data['last_reset'])
        
        if now.date() > last_reset.date():
            logger.info("New day detected, resetting quota usage.")
            self.quota_data['daily_usage'] = {}
            self.quota_data['total_used_today'] = 0
            self.quota_data['last_reset'] = now.isoformat()
            self._save_quota_data()
    
    def record_api_call(self, operation: str, count: int = 1):
        """Record an API call and its quota cost."""
        self._reset_daily_quota_if_needed()
        
        if operation not in QUOTA_COSTS:
            logger.warning(f"Unknown API operation: {operation}")
            return
        
        cost = QUOTA_COSTS[operation] * count
        today = datetime.now().strftime('%Y-%m-%d')
        
        if today not in self.quota_data['daily_usage']:
            self.quota_data['daily_usage'][today] = {}
        
        if operation not in self.quota_data['daily_usage'][today]:
            self.quota_data['daily_usage'][today][operation] = 0
        
        self.quota_data['daily_usage'][today][operation] += count
        self.quota_data['total_used_today'] += cost
        
        logger.info(f"Recorded {count} {operation} call(s) - Cost: {cost} units")
        self._save_quota_data()
    
    def get_quota_status(self) -> Dict:
        """Get current quota status and statistics."""
        self._reset_daily_quota_if_needed()
        
        used = self.quota_data['total_used_today']
        remaining = DAILY_QUOTA_LIMIT - used
        percentage_used = (used / DAILY_QUOTA_LIMIT) * 100
        
        return {
            'used': used,
            'remaining': remaining,
            'limit': DAILY_QUOTA_LIMIT,
            'percentage_used': percentage_used,
            'daily_usage': self.quota_data['daily_usage'].get(
                datetime.now().strftime('%Y-%m-%d'), {}
            )
        }
    
    def calculate_max_unsubscriptions(self) -> int:
        """Calculate maximum number of channels that can be unsubscribed from today."""
        status = self.get_quota_status()
        remaining = status['remaining']
        
        # Each unsubscription costs 50 units
        max_unsubscriptions = remaining // QUOTA_COSTS['subscriptions.delete']
        
        return max(0, max_unsubscriptions)
    
    def can_perform_operation(self, operation: str, count: int = 1) -> bool:
        """Check if an operation can be performed with remaining quota."""
        if operation not in QUOTA_COSTS:
            return False
        
        cost = QUOTA_COSTS[operation] * count
        status = self.get_quota_status()
        
        return status['remaining'] >= cost
    
    def get_quota_warning_level(self) -> str:
        """Get warning level based on quota usage."""
        status = self.get_quota_status()
        percentage = status['percentage_used']
        
        if percentage >= 90:
            return 'critical'
        elif percentage >= 75:
            return 'warning'
        elif percentage >= 50:
            return 'info'
        else:
            return 'ok'
    
    def get_quota_summary_text(self) -> str:
        """Get a formatted summary of quota usage."""
        status = self.get_quota_status()
        max_unsubs = self.calculate_max_unsubscriptions()
        warning_level = self.get_quota_warning_level()
        
        # Color coding based on warning level
        if warning_level == 'critical':
            color = 'red'
            icon = '🚨'
        elif warning_level == 'warning':
            color = 'yellow'
            icon = '⚠️'
        elif warning_level == 'info':
            color = 'blue'
            icon = 'ℹ️'
        else:
            color = 'green'
            icon = '✅'
        
        summary = f"[{color}]{icon} Quota: {status['used']:,}/{status['limit']:,} units ({status['percentage_used']:.1f}% used)[/{color}]\n"
        summary += f"[{color}]Remaining: {status['remaining']:,} units[/{color}]\n"
        summary += f"[{color}]Max unsubscriptions today: {max_unsubs}[/{color}]"
        
        return summary
