Really simple python script to grab the items from an RSS feed and repost them to a mastodon account.

- Update the feeds_config.json file with the RSS feed information and the mastodon API token.
- To get an API token from mastodon just login to your instance, and then open https://<instance>/settings/applications and "add new". Make sure it has write permissions. Return to the apps page and select the app and copy the API token.


Features:
- Posts images
- Stores ids of previously posted items so repeated posts do not happen
