import os
from twitchio.ext import commands


async def create_cog(context: commands.Context) -> bool:
    print("\n\n")
    # Splits string into a first part containing the !command and command_name and second containing return_value
    print(str(context.message.content))
    args = str(context.message.content).split(',')
    if not (len(args) == 2 or len(args) == 3):
        await context.send('newcommand syntax: "!newcommand command_name, '
                           '(required_permission 1|required_permission2|...,) '
                           'command_return".')
        return False

    # Test the first part for validity
    message_left = str(args[0]).split(' ')
    if not len(message_left) == 2:
        await context.send('newcommand syntax: "!newcommand command_name, '
                           '(required_permission 1|required_permission2|...,) '
                           'command_return". The command name cannot have spaces.')
        return False

    command = message_left[1].strip().lower()
    file_name = command + '.py'
    cog_name = command.title() + 'Cog'
    permissions = None

    if len(args) == 2:
        return_string = args[1].replace("'", "\\'").replace('"', '\\"').strip()
    else:
        permissions = args[1].lower().strip().split("|")
        return_string = args[2].replace("'", "\\'").replace('"', '\\"').strip()

    if os.path.isfile(os.path.join('cogs', file_name)):
        await context.send(f'A command already exists with the name {str(command[0])}.')
        return False

    file_contents = f'''from twitchio.ext import commands


class {cog_name}(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.permissions = {permissions}
    
    async def execute(self, context: commands.Context):
        if self.permissions:
            from config import config, get_value
            permission_error = True
            for permission_level in self.permissions:
                if not config.has_section('Permissions'):
                    break
                if not config.has_option('Permissions', permission_level):
                    continue
                users = get_value('Permissions', permission_level).split(',')
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


async def delete_cog(context: commands.Context) -> bool:
    if not os.path.isfile(os.path.join('cogs', str(context.message.content) + '.py')):
        await context.send(f'No command exists with the {str(context.message.content)}.')
        return False
    try:
        os.remove(os.path.join('cogs', str(context.message.content) + '.py'))
    except IOError as e:
        await context.send(f'An error occurred trying to remove the command: {str(e)}.')
        return False
    return True
