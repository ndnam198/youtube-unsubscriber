CREATE TYPE subscription_status AS ENUM ('SUBSCRIBED', 'TO_BE_UNSUBSCRIBED', 'UNSUBSCRIBED');

CREATE TABLE subscriptions (
    id SERIAL PRIMARY KEY,
    youtube_channel_id VARCHAR(255) NOT NULL UNIQUE,
    youtube_subscription_id VARCHAR(255) NOT NULL UNIQUE,
    channel_name VARCHAR(255) NOT NULL,
    channel_link VARCHAR(255),
    subscription_date TIMESTAMP WITH TIME ZONE,
    status subscription_status NOT NULL DEFAULT 'SUBSCRIBED'
);

COMMENT ON COLUMN subscriptions.youtube_channel_id IS 'The ID of the channel you are subscribed to.';
COMMENT ON COLUMN subscriptions.youtube_subscription_id IS 'The ID of the subscription entry itself, used for deletion.';
COMMENT ON COLUMN subscriptions.status IS 'The current status of your subscription to this channel.';
