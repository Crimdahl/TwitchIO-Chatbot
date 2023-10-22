import os
from configparser import ConfigParser, NoSectionError, NoOptionError

BOT_PATH = os.getcwd()
BOT_CONFIG_PATH = os.path.join(BOT_PATH, 'bot_config.ini')
BOT_CLIENT_ID = 'ddlzqj9jq8rspwc04v9gsa9ohl21n7'
REQUIRED_SCOPES = ['chat:read', 'chat:edit']

bot_config = ConfigParser()

DEFAULT_BOT_CONFIG = {
    'General': {
        'prefix': '!',
        'lp_enabled': 'True',
        'lp_type': 'Points',
        'lp_earn_interval_in_seconds': '300',
        'lp_number_earned': '10',
        'lp_subscriber_doubling': 'True',
        'enable_file_logging': 'True'
    },
    'Command_Permissions': {
        'reload_cogs': 'Moderator',
        'newcommand': 'Moderator',
        'newtimer': 'Moderator',
        'modifycommand': 'Moderator',
        'modifytimer': 'Moderator',
        'delcommand': 'Moderator',
        'deltimer': 'Moderator',
        'addperms': 'Nobody',
        'delperms': 'Nobody',
        'shutdown': 'Nobody',
        'reconnect': 'Nobody'
    },
    'Twitch': {
        'token': '',
        'secret': 'wzy8hj3lag2t9lnt97zaha4sko7cr4',
        'channels': '',
        'heartbeat_duration_in_seconds': '30',
        'retain_cache': 'True'
    }
}


def load_config():
    """
    Loads the config.ini file, if one exists. Primes the configuration using the DEFAULT_CONFIG dict before updating
    the values from an existing config.ini file.

    :return:
    """
    bot_config.read_dict(DEFAULT_BOT_CONFIG)
    if len(bot_config.read(BOT_CONFIG_PATH)) == 0 or not bot_config['Twitch']['token']:
        bot_config['Twitch']['token'] = input(f'It appears you are running the bot for the first time. '
                                              f'Please navigate to\n'
                                              f'https://id.twitch.tv/oauth2/authorize?response_type=token&'
                                              f'client_id={BOT_CLIENT_ID}&redirect_uri='
                                              f'https://twitchapps.com/tokengen/&scope={"%20".join(REQUIRED_SCOPES)}&'
                                              f'force_verify=true\nand input the code you are given here:\n>').strip()
        bot_config['Twitch']['channels'] = input('Whose channel do you want to connect to?\n>')
    with open(BOT_CONFIG_PATH, 'w') as config_file:
        bot_config.write(config_file)


def check_permissions(username: str, permission: str) -> bool:
    try:
        if username in bot_config['Permissions'][permission]:
            return True
    except (NoSectionError, NoOptionError):
        pass
    return False

