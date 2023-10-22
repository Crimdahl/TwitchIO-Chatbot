import os
from twitchio.ext import commands


async def create_command_cog(context: commands.Context, replace=False) -> bool:
    """
    Creates a simple cog with an execute method that returns a string when invoked by a chatter with the
    appropriate permissions.

    :param context: Context containing the chat message and ability to send messages back to chat
    :param replace: Boolean that determines whether an existing cog file should be replaced
    :return:
    """
    print("\n\n")
    # Splits string into a first part containing the !command and command_name and second containing return_value
    #   args gets everything split by comma. The return string might have commas, but as long as we have at least
    #   a command name and return value
    args = str(context.message.content).split(',')
    if not (len(args) > 1):
        await context.send('newcommand syntax: "!newcommand command_name, '
                           '(required_permission_1|required_permission_2|...,) '
                           'command_return_string".')
        return False

    # message_left gets the "!newcommand command_name" part
    message_left = str(args[0]).split(' ')
    if not len(message_left) == 2:
        await context.send('newcommand syntax: "!newcommand command_name, '
                           '(required_permission 1|required_permission2|...,) '
                           'command_return_string". The command name cannot have spaces.')
        return False

    command = message_left[1].strip().lower()
    file_name = command + '.py'
    if os.path.isfile(os.path.join('cogs', file_name)) and not replace:
        await context.send('A command by that name already exists. To replace it, use the !modifycommand command.')
        return False
    cog_name = command.title() + 'Cog'

    if len(args) == 2:
        permissions = []
        return_string = ','.join(args[1:]).replace("'", "\\'").replace('"', '\\"').strip()
    else:
        permissions = args[1].lower().strip().split("|")
        return_string = ','.join(args[2:]).replace("'", "\\'").replace('"', '\\"').strip()

    if os.path.isfile(os.path.join('cogs', file_name)):
        await context.send(f'A command already exists with the name {str(command[0])}.')
        return False

    file_contents = f'''from twitchio.ext import commands


class {cog_name}(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.permissions = {permissions}
        self.only_execute_on_command = True
        self.tick_execution_interval = -1
    
    async def execute(self, context: commands.Context):
        if self.permissions:
            from config import config, get_value
            permission_error = True
            for permission_level in self.permissions:
                if not config.has_section('Permissions'):
                    break
                if not config.has_option('Permissions', permission_level):
                    continue
                try:
                    users = config['Permissions'][permission_level].split(',')
                except KeyError:
                    pass
                if context.author in users:
                    permission_error = False
            if permission_error:
                await context.send('You must have one of the following permissions to use that command, ' 
                                   + context.author.name + ':' + str(self.permissions) + '.')
                return
        await context.send(f'{return_string}')
'''

    try:
        with open(os.path.join('cogs', file_name), 'w') as outfile:
            outfile.write(file_contents)
    except IOError as e:
        await context.send(f'An error occurred trying to create the command: {str(e)}.')
        return False
    return True


async def create_timer_cog(context: commands.Context, replace=False) -> bool:
    """
    Creates a simple cog with a tick() method that posts a string to chat at the appropriate time interval.

    :param context: Context containing the chat message and ability to send messages back to chat
    :param replace: Boolean that determines whether an existing cog file should be replaced
    :return:
    """
    print("\n\n")
    # Splits string into a first part containing the !command and command_name and second containing return_value
    #   args gets everything split by comma. The return string might have commas, but as long as we have at least
    #   a command name and return value
    args = str(context.message.content).split(',')
    if not (len(args) > 2):
        await context.send('newtimer syntax: "!newtimer command_name, '
                           'interval_in_seconds, '
                           'command_return_string".')
        return False

    # message_left gets the "!newcommand command_name" part
    message_left = str(args[0]).split(' ')
    if not len(message_left) == 2:
        await context.send('newtimer syntax: "!newtimer command_name, '
                           'interval_in_seconds, '
                           'command_return_string". The command name cannot have spaces.')
        return False

    command = message_left[1].strip().lower()
    file_name = command + '.py'
    if os.path.isfile(os.path.join('cogs', file_name)) and not replace:
        await context.send('A timer by that name already exists. To replace it, use the !modifytimer command.')
        return False
    cog_name = command.title() + 'Cog'

    try:
        interval = int(args[1].lower().strip())
        if not interval > 0:
            raise ValueError
        return_string = ','.join(args[2:]).replace("'", "\\'").replace('"', '\\"').strip()
    except ValueError:
        await context.send('The timer interval must be a positive non-zero integer.')
        return False

    if os.path.isfile(os.path.join('cogs', file_name)):
        await context.send(f'A command already exists with the name {str(command[0])}.')
        return False

    file_contents = f'''from twitchio.ext import commands

tick_count = 0


class {cog_name}(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.permissions = []
        self.only_execute_on_command = True
        self.tick_execution_interval = {interval}
    
    async def tick(self, channel: Channel):
        global tick_count
        tick_count += 1
        if tick_count % self.tick_execution_interval == 0:
            await context.send(f'{return_string}')
'''

    try:
        with open(os.path.join('cogs', file_name), 'w') as outfile:
            outfile.write(file_contents)
    except IOError as e:
        await context.send(f'An error occurred trying to create the command: {str(e)}.')
        return False
    return True


async def delete_cog(context: commands.Context, cog_type) -> bool:
    """
    Function that deletes one of the cogs in the cogs directory.

    :param context: Context containing the chat message and ability to send messages back to chat
        :param cog_type: The type of cog being deleted.
    :return:
    """
    if not os.path.isfile(os.path.join('cogs', str(context.message.content) + '.py')):
        await context.send(f'No {cog_type} exists with the name {str(context.message.content)}.')
        return False
    try:
        os.remove(os.path.join('cogs', str(context.message.content) + '.py'))
    except IOError as e:
        await context.send(f'An error occurred trying to remove the command: {str(e)}.')
        return False
    return True
