-- YouTube Unsubscriber Database Schema
-- This file contains the complete database schema for the YouTube Unsubscriber application

-- Create subscription status enum
CREATE TYPE subscription_status AS ENUM ('SUBSCRIBED', 'TO_BE_UNSUBSCRIBED', 'UNSUBSCRIBED', 'KEPT');

-- Create subscriptions table
CREATE TABLE subscriptions (
    id SERIAL PRIMARY KEY,
    youtube_channel_id VARCHAR(255) NOT NULL UNIQUE,
    youtube_subscription_id VARCHAR(255) NOT NULL UNIQUE,
    channel_name VARCHAR(255) NOT NULL,
    channel_link VARCHAR(255),
    subscription_date TIMESTAMP
    WITH
        TIME ZONE,
        status subscription_status NOT NULL DEFAULT 'SUBSCRIBED'
);

-- Create content type enum
CREATE TYPE content_type AS ENUM ('SHORTS', 'LONGS', 'MIXED', 'UNKNOWN');

-- Create channels table for additional metadata
CREATE TABLE channels (
    youtube_channel_id VARCHAR(255) PRIMARY KEY,
    channel_title VARCHAR(255) NOT NULL,
    description TEXT,
    subscriber_count BIGINT,
    video_count BIGINT,
    view_count BIGINT,
    country VARCHAR(10),
    custom_url VARCHAR(255),
    published_at TIMESTAMP WITH TIME ZONE,
    thumbnail_url TEXT,
    topic_ids TEXT [], -- Array of topic IDs from YouTube
    content_type content_type DEFAULT 'UNKNOWN',
    shorts_count INTEGER DEFAULT 0,
    longs_count INTEGER DEFAULT 0,
    shorts_percentage DECIMAL(5,2) DEFAULT 0.0,
    content_analysis_date TIMESTAMP WITH TIME ZONE,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Add foreign key constraint from subscriptions to channels
ALTER TABLE subscriptions
ADD CONSTRAINT fk_subscriptions_channel_id FOREIGN KEY (youtube_channel_id) REFERENCES channels (youtube_channel_id) ON DELETE CASCADE;

-- Create indexes for better performance
CREATE INDEX idx_channels_subscriber_count ON channels (subscriber_count);

CREATE INDEX idx_channels_video_count ON channels (video_count);

CREATE INDEX idx_channels_published_at ON channels (published_at);

CREATE INDEX idx_channels_last_updated ON channels (last_updated);

-- Create a view for combined subscriptions and channel metadata
CREATE OR REPLACE VIEW subscriptions_with_metadata AS
SELECT
    s.id AS subscription_id,
    s.youtube_channel_id,
    s.youtube_subscription_id,
    s.channel_name AS subscription_channel_name,
    s.channel_link,
    s.subscription_date,
    s.status,
    c.channel_title,
    c.description,
    c.subscriber_count,
    c.video_count,
    c.view_count,
    c.country,
    c.custom_url,
    c.published_at AS channel_published_at,
    c.thumbnail_url,
    c.topic_ids,
    c.content_type,
    c.shorts_count,
    c.longs_count,
    c.shorts_percentage,
    c.content_analysis_date,
    c.last_updated AS channel_metadata_last_updated,
    c.created_at AS channel_metadata_created_at
FROM subscriptions s
    LEFT JOIN channels c ON s.youtube_channel_id = c.youtube_channel_id;

-- Add table and column comments
COMMENT ON TABLE subscriptions IS 'YouTube channel subscriptions';

COMMENT ON COLUMN subscriptions.youtube_channel_id IS 'The ID of the channel you are subscribed to.';

COMMENT ON COLUMN subscriptions.youtube_subscription_id IS 'The ID of the subscription entry itself, used for deletion.';

COMMENT ON COLUMN subscriptions.status IS 'The current status of your subscription to this channel.';

COMMENT ON
TABLE channels IS 'Additional metadata for YouTube channels';

COMMENT ON COLUMN channels.youtube_channel_id IS 'The YouTube channel ID (primary key)';

COMMENT ON COLUMN channels.subscriber_count IS 'Number of subscribers to the channel';

COMMENT ON COLUMN channels.video_count IS 'Total number of videos uploaded by the channel';

COMMENT ON COLUMN channels.view_count IS 'Total number of views across all videos';

COMMENT ON COLUMN channels.description IS 'Channel description text';

COMMENT ON COLUMN channels.topic_ids IS 'Array of YouTube topic IDs associated with the channel';

COMMENT ON COLUMN channels.content_type IS 'Primary content type: SHORTS, LONGS, MIXED, or UNKNOWN';

COMMENT ON COLUMN channels.shorts_count IS 'Number of short-form videos (≤60s)';

COMMENT ON COLUMN channels.longs_count IS 'Number of long-form videos (>60s)';

COMMENT ON COLUMN channels.shorts_percentage IS 'Percentage of short-form content';

COMMENT ON COLUMN channels.content_analysis_date IS 'When content analysis was last performed';

COMMENT ON COLUMN channels.last_updated IS 'When this channel data was last fetched from YouTube API';

COMMENT ON COLUMN channels.created_at IS 'When this channel record was first created';

COMMENT ON VIEW subscriptions_with_metadata IS 'Combined view of subscriptions and their channel metadata';