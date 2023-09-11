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
import config

from twitchio.ext import commands

COG_PATH = os.path.join(os.getcwd(), 'cogs')
bot_thread = None


class Bot(commands.Bot):
    def __init__(self, token: str, secret: str, prefix: str, channels: [],
                 heartbeat: int = 30, retain_cache: bool = True):
        super().__init__(
            token=token,
            client_secret=secret,
            prefix=prefix,
            initial_channels=channels,
            heartbeat=heartbeat,
            retain_cache=retain_cache
        )
        self.prefix = prefix

    async def load_cogs(self):
        """
        Uses importlib and inspection to dynamically locate and load Classes that subclass Cog in .py files
        in the cogs directory. Creates the Cog objects and loads the objects into the bot.

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
                        # Look for classes
                        for name, obj in inspect.getmembers(cog_module):
                            if inspect.isclass(obj) and commands.Cog in inspect.getmro(obj):
                                try:
                                    self.add_cog(obj(self))
                                except commands.InvalidCog as exc:
                                    print(f'Error loading cog {str(obj)}: {exc}')
                    except Exception as e:
                        print(f'Error logging cog module at {str(file_path)}: {str(e)}')

    async def event_ready(self):
        print(f"Successfully logged in as {self.nick}.")
        await self.load_cogs()

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
        cog = self.get_cog(command.title() + 'Cog')
        if cog is not None:
            await cog.execute(message_context)

        await self.handle_commands(message)

    @commands.command()
    async def newcommand(self, ctx: commands.Context):
        """
        Uses the cog.template.py file to create a .py file in the cogs directory containing the code necessary
        to create and run a new Cog object, then adds the cog to the bot. Sends chat confirmation.

        :param ctx: Context containing the message
        :return: None
        """
        from cog_template import create_cog
        success = await create_cog(ctx)
        if success:
            await self.load_cogs()
        await ctx.send('Command created.')

    @commands.command()
    async def delcommand(self, ctx: commands.Context):
        """
        Uses the cog.template.py file to delete a .py file in the cogs directory and remove the Cog object
        from the bot. Sends chat confirmation.

        :param ctx: Context containing the message
        :return: None
        """
        from cog_template import delete_cog
        success = await delete_cog(ctx)
        if success:
            self.remove_cog(self.get_cog(str(ctx.message)).name)
        await ctx.send('Command deleted.')

    @commands.command()
    async def addperms(self, ctx: commands.Context):
        """
        Adds user to the ConfigParser's Permissions section under the appropriate option. If the user was added
        or if the user already had the permissions, sends chat confirmation.

        :param ctx: Context containing the message
        :return: None
        """
        config.load()
        args = ' '.join(str(ctx.message.content).split(' ')[1:]).split(',')
        if not len(args) > 1:
            await ctx.send('Command syntax: !addperms <username>,<permission level>(,<permission level>,...)')
            return
        username = str(args.pop(0).strip().lower())
        for permission_level in args:
            permission_level = str(permission_level).strip().lower()
            if config.config.has_section('Permissions'):
                if config.config.has_option('Permissions', permission_level):
                    existing_users = config.get_value('Permissions', permission_level).split(',')
                    if not username in existing_users:
                        existing_users.append(username)
                        config.set_value('Permissions', permission_level, ','.join(existing_users))
                else:
                    config.set_value('Permissions', permission_level, username)
            else:
                config.set_value('Permissions', permission_level, username)
        await ctx.send('Permissions added.')

    @commands.command()
    async def delperms(self, ctx: commands.Context):
        """
        Removes user from the ConfigParser's Permissions section. If the user did not have the permissions being
        removed or if the user is successfully removed, sends chat confirmation.

        :param ctx: Context containing the message
        :return: None
        """
        config.load()
        args = ' '.join(str(ctx.message.content).split(' ')[1:]).split(',')
        if not len(args) > 1:
            await ctx.send('Command syntax: !delperms <username>,<permission level>(,<permission level>,...)')
            return
        username = str(args.pop(0).strip().lower())
        for permission_level in args:
            permission_level = str(permission_level).strip().lower()
            if not config.config.has_section('Permissions'):
                break
            if not config.config.has_option('Permissions', permission_level):
                continue
            existing_users = config.get_value('Permissions', permission_level).split(',')
            if username in existing_users:
                existing_users.remove(username)
                if len(existing_users) == 0:
                    config.remove_option('Permissions', permission_level)
                else:
                    config.set_value('Permissions', permission_level, ','.join(existing_users))
        await ctx.send('Permissions deleted.')

    @commands.command()
    async def shutdown(self, ctx: commands.Context):
        """
        Shuts down the connection and the bot.

        :param ctx: Context containing the message
        :return: None
        """
        from asyncio.exceptions import CancelledError
        await ctx.send("Shutting down...")
        try:
            await self.close()
        except CancelledError:
            pass
        self.loop.stop()

    @commands.command()
    async def reconnect(self, ctx: commands.Context):
        """
        Reloads bot attributes from the config file and then attempts reconnection.

        :param ctx: Context containing the message
        :return: None
        """
        await ctx.send("Restarting...")
        config.load()
        self.token = config.get_value('Twitch', 'token'),
        self.secret = config.get_value('Twitch', 'secret'),
        self.prefix = config.get_value('Twitch', 'prefix'),
        self.initial_channels = config.get_value('Twitch', 'channels').split(','),
        self.heartbeat = int(config.get_value('Twitch', 'heartbeat_duration_seconds')),
        self.retain_cache = bool(config.get_value('Twitch', 'retain_cache'))
        self._closing = False
        await self.connect()
        await ctx.send("Reconnection complete.")


config.load()
Bot(
    token=config.get_value('Twitch', 'token'),
    secret=config.get_value('Twitch', 'secret'),
    prefix=config.get_value('Twitch', 'prefix'),
    channels=config.get_value('Twitch', 'channels').split(','),
    heartbeat=int(config.get_value('Twitch', 'heartbeat_duration_seconds')),
    retain_cache=bool(config.get_value('Twitch', 'retain_cache'))
).run()
