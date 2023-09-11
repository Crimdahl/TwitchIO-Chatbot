import os
from configparser import ConfigParser
from pathlib import Path


CONFIG_PATH = Path(os.path.join(os.getcwd(), "config.ini"))
config = ConfigParser()


def load():
    try:
        global config
        config = ConfigParser()
        if len(config.read(CONFIG_PATH)) == 0:
            raise IOError
    except IOError:
        with open(CONFIG_PATH, 'w') as config_file:
            config.add_section('Twitch')
            # Client class settings
            config.set('Twitch', 'token', 'qmnkhhrlfi1hj19lba2p1yqysbhrwn  ')
            config.set('Twitch', 'secret', 'wzy8hj3lag2t9lnt97zaha4sko7cr4')
            config.set('Twitch', 'channels', '')
            config.set('Twitch', 'heartbeat_duration_seconds', '30')
            config.set('Twitch', 'retain_cache', 'True')

            # Bot class settings
            config.set('Twitch', 'prefix', '!')
            config.write(config_file)
        print("New config.ini file created. Before the bot can run, please fill in your token, secret, etc.")
        import sys
        sys.exit()


load()


def set_value(section, option, value, path=CONFIG_PATH):
    config.read(path)
    if not config.has_section(section):
        config.add_section(section)
    config.set(section, option, value)
    with open(path, 'w') as f:
        config.write(f)


def get_value(section, option, path=CONFIG_PATH):
    config.read(path)
    if config.has_section(section) and config.has_option(section, option):
        return config.get(section, option)
    else:
        return ''


def get_items(section, path=CONFIG_PATH):
    config.read(path)
    results = {}
    if config.has_section(section):
        for option in config.options(section):
            results[option] = config.get(section, option)
    return results


def remove_option(section, option, path=CONFIG_PATH):
    global config
    config.remove_option(section, option)
    with open(path, 'w') as f:
        config.write(f)
