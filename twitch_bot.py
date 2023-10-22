"""
The MIT License (MIT)

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""
import os
from importlib import reload
from datetime import datetime
from json import load, dumps, JSONDecodeError
from twitchio.ext import commands, routines
from utils import LoggingLevel, log_to_file
from bot_configuration import bot_config, check_permissions, load_config

if __name__ == "__main__":
    # Token generating attributes
    TWITCH_OAUTH_URL_ROOT = 'https://id.twitch.tv/oauth2/token'

    # Bot path attributes
    BOT_PATH = os.getcwd()
    # BOT_CREDS_PATH = os.path.join(BOT_PATH, 'creds.json')
    BOT_LOG_PATH = os.path.join(BOT_PATH, 'bot_log_' + datetime.now().strftime('%Y-%m-%d_%I-%M-%S_%p') + '.txt')
    COG_PATH = os.path.join(BOT_PATH, 'cogs')
    LOYALTY_POINTS_PATH = os.path.join(BOT_PATH, 'loyalty.json')

    bot_thread = None
    tick_count = 0

    # Load config prior to the bot class code. This allows config values to be used for aliases of commands and such.
    load_config()


class Bot(commands.Bot):
    def __init__(self, token: str, secret: str, prefix: str, channels: [],
                 heartbeat: int = 30, retain_cache: bool = True, tick_rate: int = 1):
        super().__init__(
            token=token,
            client_secret=secret,
            prefix=prefix,
            initial_channels=channels,
            heartbeat=heartbeat,
            retain_cache=retain_cache,
            tick_rate=tick_rate
        )
        self.loyalty_points = {}
        self.prefix = prefix
        self.tick_pause = False

    async def load_cogs(self, force_reload=False):
        """
        Uses importlib and inspection to dynamically locate and load Classes that subclass Cog in .py files
        in the cogs directory. Creates the Cog objects and loads the objects into the bot.

        :param force_reload: Bool that controls whether the method reloads the imports. This allows existing cogs
            to be completely reloaded.
        :return: None
        """
        import inspect
        import importlib
        for root, directories, files in os.walk(COG_PATH):
            for file in files:
                if str(file).endswith('.py'):
                    # Check if the cog is already loaded. If so, skip.
                    if self.get_cog(os.path.splitext(file)[0]) is not None:
                        continue
                    file_path = '.'.join(os.path.join(root, os.path.splitext(file)[0]).split('\\')[-2:])
                    try:
                        cog_module = importlib.import_module(file_path)
                        if force_reload:
                            importlib.reload(cog_module)
                        # Look for classes
                        for name, obj in inspect.getmembers(cog_module):
                            if inspect.isclass(obj) and commands.Cog in inspect.getmro(obj):
                                try:
                                    self.add_cog(obj(self))
                                except commands.InvalidCog as exc:
                                    print(f'Error loading cog {str(obj)}: {exc}')
                    except Exception as e:
                        print(f'Error logging cog module at {str(file_path)}: {str(e)}')

    async def load_loyalty_points(self):
        """
        Loads loyalty points from any existing loyalty.json file in the bot directory.

        :return:
        """
        if os.path.exists(LOYALTY_POINTS_PATH):
            try:
                with open(LOYALTY_POINTS_PATH, 'r') as loyalty_file:
                    self.loyalty_points = load(loyalty_file)
            except JSONDecodeError:
                os.rename(LOYALTY_POINTS_PATH, os.path.splitext(LOYALTY_POINTS_PATH)[0] + '_backup.json')
                log('The existing loyalty points file appears corrupted. It has been backed up and a new file has '
                    'been created to record loyalty information. Please investigate.', LoggingLevel.Fatal)

    @routines.routine(seconds=1)
    async def tick(self):
        """
        Custom routine that runs each second and performs various operations:

        -Invokes the tick() functions in each of the cogs. Deliberately works similarly to the Tick() function in
            Streamlabs Chatbot scripts.
        -Accumulates loyalty points if loyalty points are enabled. By default, works the same way as Twitch
            Channel Points, where you get 10 points every 5 minutes base and points are doubled for subscribers.
            Streaks do not exist (yet).

        :return:
        """
        # current_time = datetime.now()
        # if current_time > datetime.fromtimestamp(float(bot_creds['expiry_time'])):
        #     log('Access token has expired. Generating a new access token and reconnecting.', LoggingLevel.Warn)
        #     make_creds_file()

        if not self.tick_pause:
            global tick_count
            tick_count += 1

            try:
                if (bot_config['General']['lp_enabled'] == 'True' and
                        tick_count % int(bot_config['General']['lp_earn_interval_in_seconds']) == 0):
                    log('Distributing loyalty points.', LoggingLevel.Info)
                    try:
                        int(bot_config['General']['lp_number_earned'])
                        chatters = zip(self.connected_channels[0].chatters,
                                       await self.fetch_users(names=[chatter.name for chatter
                                                                     in self.connected_channels[0].chatters]))
                        for chatter, attributes in chatters:
                            points_earned = int(bot_config['General']['lp_number_earned'])
                            if bot_config['General']['lp_subscriber_doubling'] == 'True' and chatter.is_subscriber:
                                points_earned = points_earned * 2
                            log(f'{chatter.name} with id {str(attributes.id)} is receiving {str(points_earned)}'
                                f' loyalty points.', LoggingLevel.Info)
                            try:
                                self.loyalty_points[str(attributes.id)]['loyalty_points'] = str(
                                    int(self.loyalty_points[str(attributes.id)]['loyalty_points']) +
                                    points_earned)
                            except KeyError:
                                # Chatter did not exist in the dictionary of loyalty points
                                self.loyalty_points[str(attributes.id)] = {
                                    'loyalty_points': points_earned,
                                    'username': chatter.name
                                }
                            except ValueError:
                                # Chatter did not have loyalty points
                                self.loyalty_points[str(attributes.id)]['loyalty_points'] = \
                                    points_earned

                        with open(LOYALTY_POINTS_PATH, 'w') as loyalty_file:
                            loyalty_file.write(dumps(self.loyalty_points))
                    except ValueError:
                        log_to_file('The value for loyalty_points_number_earned is not an integer. '
                                    'Points cannot be rewarded.',
                                    LoggingLevel.Warn)
            except ValueError:
                log_to_file('The value for loyalty_points_earn_interval_in_seconds is not an integer. '
                            'Points cannot be rewarded.',
                            LoggingLevel.Warn)

            # Uses list comprehension for protection against RuntimeError: dictionary keys changed during iteration
            for cog_name in [name for name in self.cogs]:
                cog = self.get_cog(cog_name)
                try:
                    await cog.tick(self.connected_channels[0])
                except (TypeError, AttributeError):
                    pass

    async def event_ready(self):
        """
        TwitchIO event handler that fires when the bot establishes a successful connection to Twitch

        :return:
        """
        print(f"Successfully logged in as {self.nick}.")
        await self.load_cogs()
        await self.load_loyalty_points()
        self.tick.start()

    async def event_message(self, message):
        """
        Receives messages. If the message starts with the command prefix iterates over all Cog objects, invoking
        the Cog's execute function. Also executes self.handle_commands to run standard bot commands.

        :param message: The chat message causing the event.
        :return:
        """
        # Messages with echo set to True are messages sent by the bot...
        # For now we just want to ignore them...
        if message.echo:
            return

        # Since we have commands and are overriding the default `event_message`
        # We must let the bot know we want to handle and invoke our commands...
        message_context = await self.get_context(message)
        command = str(message.content).split(' ')[0][1:]

        for cog_name in self.cogs:
            cog = self.get_cog(cog_name)
            try:
                # only_execute_on_command is a variable that determines whether the bot should only run the cog's
                #   execute function if the
                if cog_name == command.title() + 'Cog' or not cog.only_execute_on_command:
                    await cog.execute(message_context)
            except AttributeError:
                pass

        if str(message.content).startswith(self.prefix):
            await self.handle_commands(message)

    @commands.command(aliases=[bot_config['General']['lp_type'].lower()])
    async def loyalty(self, ctx: commands.Context):
        try:
            await ctx.send(f'@{ctx.author.name}: Your current amount of {bot_config["General"]["lp_type"]} is '
                           f'{self.loyalty_points[ctx.author.id]["loyalty_points"]}.')
        except (KeyError, ValueError):
            await ctx.send(f'@{ctx.author.name}: Your do not currently have any {bot_config["General"]["lp_type"]}.')

    @commands.command(aliases=['recog'])
    async def reload_cogs(self, ctx: commands.Context):
        """
        Reloads all cogs and cog modules. Can be used to apply updated cog code without restarting the whole bot.

        :return:
        """
        if not (ctx.author.name == self.connected_channels[0].name) and not \
                check_permissions(username=ctx.author.name,
                                  permission=bot_config['Command_Permissions']['reload_cogs']):
            await ctx.send(f'Sorry, @{ctx.author.name}, you do not have the '
                           f'required permissions to '
                           f'use that command.')
            return

        self.tick_pause = True
        # Uses list comprehension for protection against RuntimeError: dictionary keys changed during iteration
        for cog_name in [name for name in self.cogs]:
            self.remove_cog(cog_name)
        await self.load_cogs(force_reload=True)
        self.tick_pause = False

    @commands.command()
    async def newcommand(self, ctx: commands.Context, replace=False):
        """
        Uses the cog.template.py file to create a .py file in the cogs directory containing the code necessary
        to create and run a new Cog object, then adds the cog to the bot. Sends chat confirmation.

        :param ctx: Context containing the chat message and ability to send messages back to chat
        :param replace: Boolean that determines whether an existing cog file should be replaced
        :return: None
        """
        if not (ctx.author.name == self.connected_channels[0].name) and not \
                check_permissions(username=ctx.author.name,
                                  permission=bot_config['Command_Permissions']['newcommand']):
            await ctx.send(f'Sorry, @{ctx.author.name}, you do not have the '
                           f'required permissions to '
                           f'use that command.')
            return

        from cog_template import create_command_cog
        success = await create_command_cog(ctx, replace)
        if success:
            await self.load_cogs()
            if replace:
                await ctx.send('Command modified.')
            else:
                await ctx.send('Command created.')

    @commands.command()
    async def newtimer(self, ctx: commands.Context, replace=False):
        """
        Uses the cog.template.py file to create a .py file in the cogs directory containing the code necessary
        to create and run a new Cog object, then adds the cog to the bot. Sends chat confirmation.

        :param ctx: Context containing the chat message and ability to send messages back to chat
        :param replace: Boolean that determines whether an existing cog file should be replaced
        :return: None
        """
        if not (ctx.author.name == self.connected_channels[0].name) and not \
                check_permissions(username=ctx.author.name,
                                  permission=bot_config['Command_Permissions']['newtimer']):
            await ctx.send(f'Sorry, @{ctx.author.name}, you do not have the '
                           f'required permissions to '
                           f'use that command.')
            return

        from cog_template import create_timer_cog
        success = await create_timer_cog(ctx, replace)
        if success:
            await self.load_cogs()
            if replace:
                await ctx.send('Timer modified.')
            else:
                await ctx.send('Timer created.')

    @commands.command()
    async def modifycommand(self, ctx: commands.Context, replace=True):
        """
        Uses the cog.template.py file to create a .py file in the cogs directory containing the code necessary
        to create and run a new Cog object, then adds the cog to the bot. Sends chat confirmation.

        :param ctx: Context containing the chat message and ability to send messages back to chat
        :param replace: Boolean that determines whether an existing cog file should be replaced
        :return: None
        """
        if not (ctx.author.name == self.connected_channels[0].name) and not \
                check_permissions(username=ctx.author.name,
                                  permission=bot_config['Command_Permissions']['modifycommand']):
            await ctx.send(f'Sorry, @{ctx.author.name}, you do not have the '
                           f'required permissions to '
                           f'use that command.')
            return

        await self.newcommand(ctx, replace)

    @commands.command()
    async def modifytimer(self, ctx: commands.Context, replace=True):
        """
        Uses the cog.template.py file to create a .py file in the cogs directory containing the code necessary
        to create and run a new Cog object, then adds the cog to the bot. Sends chat confirmation.

        :param ctx: Context containing the chat message and ability to send messages back to chat
        :param replace: Boolean that determines whether an existing cog file should be replaced
        :return: None
        """
        if not (ctx.author.name == self.connected_channels[0].name) and not \
                check_permissions(username=ctx.author.name,
                                  permission=bot_config['Command_Permissions']['modifytimer']):
            await ctx.send(f'Sorry, @{ctx.author.name}, you do not have the '
                           f'required permissions to '
                           f'use that command.')
            return

        await self.newtimer(ctx, replace)

    @commands.command()
    async def delcommand(self, ctx: commands.Context, cog_type='Command'):
        """
        Uses the cog.template.py file to delete a .py file in the cogs directory and remove the Cog object
        from the bot. Sends chat confirmation.

        :param ctx: Context containing the chat message and ability to send messages back to chat
        :param cog_type: The type of cog being deleted.
        :return: None
        """
        if not (ctx.author.name == self.connected_channels[0].name) and not \
                check_permissions(username=ctx.author.name,
                                  permission=bot_config['Command_Permissions']['delcommand']):
            await ctx.send(f'Sorry, @{ctx.author.name}, you do not have the '
                           f'required permissions to '
                           f'use that command.')
            return

        from cog_template import delete_cog
        success = await delete_cog(ctx, cog_type)
        if success:
            self.remove_cog(self.get_cog(str(ctx.message)).name)
        await ctx.send(f'{cog_type} deleted.')

    @commands.command()
    async def deltimer(self, ctx: commands.Context):
        """
        Uses the cog.template.py file to delete a .py file in the cogs directory and remove the Cog object
        from the bot. Sends chat confirmation.

        :param ctx: Context containing the message
        :return: None
        """
        if not (ctx.author.name == self.connected_channels[0].name) and not \
                check_permissions(username=ctx.author.name,
                                  permission=bot_config['Command_Permissions']['deltimer']):
            await ctx.send(f'Sorry, @{ctx.author.name}, you do not have the '
                           f'required permissions to '
                           f'use that command.')
            return

        await self.delcommand(ctx, 'Timer')

    @commands.command()
    async def addperms(self, ctx: commands.Context):
        """
        Adds user to the ConfigParser's Permissions section under the appropriate option. If the user was added
        or if the user already had the permissions, sends chat confirmation.

        :param ctx: Context containing the chat message and ability to send messages back to chat
        :return: None
        """
        if not (ctx.author.name == self.connected_channels[0].name) and not \
                check_permissions(username=ctx.author.name,
                                  permission=bot_config['Command_Permissions']['addperms']):
            await ctx.send(f'Sorry, @{ctx.author.name}, you do not have the '
                           f'required permissions to '
                           f'use that command.')
            return

        args = ' '.join(str(ctx.message.content).split(' ')[1:]).split(',')
        if not len(args) > 1:
            await ctx.send('Command syntax: !addperms <username>,<permission level>(,<permission level>,...)')
            return
        username = str(args.pop(0).strip().lower())
        for permission_level in args:
            permission_level = str(permission_level).strip().lower()
            if bot_config.has_section('Permissions'):
                if bot_config.has_option('Permissions', permission_level):
                    existing_users = bot_config['Permissions'][permission_level].split(',')
                    if not username in existing_users:
                        existing_users.append(username)
                        bot_config['Permissions'][permission_level] = ','.join(existing_users)
                else:
                    bot_config['Permissions'][permission_level] = username
            else:
                bot_config.add_section('Permissions')
                bot_config['Permissions'][permission_level] = username
        with open(BOT_CONFIG_PATH, 'w') as config_file:
            bot_config.write(config_file)
        await ctx.send('Permissions added.')

    @commands.command()
    async def delperms(self, ctx: commands.Context):
        """
        Removes user from the ConfigParser's Permissions section. If the user did not have the permissions being
        removed or if the user is successfully removed, sends chat confirmation.

        :param ctx: Context containing the chat message and ability to send messages back to chat
        :return: None
        """
        if not (ctx.author.name == self.connected_channels[0].name) and not \
                check_permissions(username=ctx.author.name,
                                  permission=bot_config['Command_Permissions']['delperms']):
            await ctx.send(f'Sorry, @{ctx.author.name}, you do not have the '
                           f'required permissions to '
                           f'use that command.')
            return

        global BOT_CONFIG_PATH
        args = ' '.join(str(ctx.message.content).split(' ')[1:]).split(',')
        if not len(args) > 1:
            await ctx.send('Command syntax: !delperms <username>,<permission level>(,<permission level>,...)')
            return
        username = str(args.pop(0).strip().lower())
        for permission_level in args:
            permission_level = str(permission_level).strip().lower()
            if not bot_config.config.has_section('Permissions'):
                break
            if not bot_config.config.has_option('Permissions', permission_level):
                continue
            existing_users = bot_config['Permissions'][permission_level].split(',')
            if username in existing_users:
                existing_users.remove(username)
                if len(existing_users) == 0:
                    bot_config.remove_option('Permissions', permission_level)
                else:
                    bot_config['Permissions'][permission_level] = ','.join(existing_users)
        with open(BOT_CONFIG_PATH, 'w') as config_file:
            bot_config.write(config_file)
        await ctx.send('Permissions deleted.')

    @commands.command()
    async def shutdown(self, ctx: commands.Context):
        """
        Shuts down the connection and the bot.

        :param ctx: Context containing the chat message and ability to send messages back to chat
        :return: None
        """
        if not (ctx.author.name == self.connected_channels[0].name) and not \
                check_permissions(username=ctx.author.name,
                                  permission=bot_config['Command_Permissions']['shutdown']):
            await ctx.send(f'Sorry, @{ctx.author.name}, you do not have the '
                           f'required permissions to '
                           f'use that command.')
            return

        from asyncio.exceptions import CancelledError
        await ctx.send("Shutting down...")
        try:
            await self.close()
        except CancelledError:
            pass
        self.tick.stop()
        self.loop.stop()

    @commands.command()
    async def reconnect(self, ctx: commands.Context):
        """
        Reloads bot attributes from the config file and then attempts reconnection.

        :param ctx: Context containing the chat message and ability to send messages back to chat
        :return: None
        """

        if not (ctx.author.name == self.connected_channels[0].name) and not \
                check_permissions(username=ctx.author.name,
                                  permission=bot_config['Command_Permissions']['reconnect']):
            await ctx.send(f'Sorry, @{ctx.author.name}, you do not have the '
                           f'required permissions to '
                           f'use that command.')
            return

        import bot_configuration
        await ctx.send("Restarting...")
        self.tick.stop()
        reload(bot_configuration)
        self.prefix = bot_config['General']['prefix']
        self.token = bot_config['Twitch']['token']
        self.secret = bot_config['Twitch']['secret']
        self.initial_channels = bot_config['Twitch']['channels'].split(',')
        self.heartbeat = int(bot_config['Twitch']['heartbeat_duration_in_seconds'])
        self.retain_cache = bool(bot_config['Twitch']['retain_cache'])
        self._closing = False
        await self.connect()
        self.tick.start()
        await ctx.send("Reconnection complete.")


def log(log_string: str, log_level=LoggingLevel.str_to_int.get("All")):
    """
    Uses the log_to_file method to write to bot_log_<date>.txt

    :param log_string: The string contents to write to the file
    :param log_level: The severity of the log entry
    :return:
    """
    if bot_config.get('General', 'enable_file_logging') == 'True':
        log_to_file(BOT_LOG_PATH, log_string, log_level)


if __name__ == "__main__":
    Bot(
        token=bot_config['Twitch']['token'],
        secret=bot_config['Twitch']['secret'],
        prefix=bot_config['General']['prefix'],
        channels=bot_config['Twitch']['channels'].split(','),
        heartbeat=int(bot_config['Twitch']['heartbeat_duration_in_seconds']),
        retain_cache=bool(bot_config['Twitch']['retain_cache'])
    ).run()
