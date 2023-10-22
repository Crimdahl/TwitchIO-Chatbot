import json
import os
import time
import pathlib
from random import randint
from twitchio.channel import Channel
from twitchio.ext import commands
from configparser import ConfigParser
from utils import LoggingLevel, log_to_file, get_formatted_time_diff

PARENT_BOT_PATH = pathlib.Path(os.path.abspath(os.path.dirname(__file__))).parent
TRIVIA_CONFIG_PATH = os.path.join(PARENT_BOT_PATH, 'trivia', 'trivia_config.ini')
TRIVIA_LOG_PATH = os.path.join(PARENT_BOT_PATH, 'trivia', 'trivia_log.txt')
TRIVIA_DATA_FOLDER = os.path.join(PARENT_BOT_PATH, 'trivia', 'questions')

master_questions_list = []  # List of all questions
current_questions_list = []  # List of currently active questions depending on settings
current_question_index = -1
question_start_time = time.time()
question_expiry_time = 0

trivia_config = ConfigParser()
trivia_paused = False
current_game = ''
game_detection_override = None
next_question_file_update_time = None
channel_is_live = False

ready_for_next_question = True
readiness_notification_time = None
grace_period_set = False

winners = {}

DEFAULT_CONFIG = {
    'General': {
        'prefix': '!',
        'run_only_when_live': 'True',
        'player_permissions': 'Everyone',
        'admin_permissions': 'Moderator',
        'enable_file_logging': 'True',
        'debug_level': 'Info',
        'command_prefix': '!trivia'
    },
    'Questions': {
        'duration_in_minutes': '5',
        'cooldown_between_questions_in_minutes': '5',
        'randomize_question_cooldown': 'False',
        'randomized_question_cooldown_upper_bound': '5',
        'randomized_question_cooldown_lower_bound': '2',
        'automatically_run_questions': 'True',
        'question_readiness_notify_in_minutes': '5',
        'enable_game_detection': 'False'
    },
    'Rewards': {
        'loyalty_points_type': 'Points',
        'default_loyalty_points_value': '50',
        'number_of_winners': '1',
        'use_grace_period': 'False',
        'multiple_winner_grace_period_in_seconds': '2'
    }
}


class Question(object):
    # Object-specific Variables
    points = None
    game = None
    question = None
    answers = []

    def __init__(self, **kwargs):
        self.points = kwargs["points"] if "points" in kwargs else (
            trivia_config['Questions']['default_loyalty_points_value'])
        self.game = kwargs["game"] if "game" in kwargs \
            else Question.raise_value_error(self, "Error: No 'game' keyword was supplied.")
        self.question = kwargs["question"] if "question" in kwargs \
            else Question.raise_value_error(self, "Error, no 'question' keyword was supplied.")
        self.answers = kwargs["answers"] if "answers" in kwargs \
            else Question.raise_value_error(self, "Error: No 'answers' keyword was supplied.")

    def as_string(self):
        return (f"for {str(self.points)} "
                f"{trivia_config['Rewards']['loyalty_points_type']}: "
                f"In {self.game}, {self.question}")

    def to_json(self):
        return {"Points": self.points, "Game": self.game, "Question": self.question, "Answers": self.answers}

    def get_game(self):
        return self.game

    def set_game(self, new_game):
        self.game = new_game

    def get_question(self):
        return self.question

    def set_question(self, new_question):
        self.question = new_question

    def get_points(self):
        return self.points

    def set_points(self, new_points):
        self.points = new_points

    def get_answers(self):
        return self.answers

    def set_answers(self, new_answers):
        if isinstance(new_answers, list):
            self.answers = new_answers
            return True
        else:
            return False

    def remove_answer(self, answer):
        try:
            self.answers.remove(answer.lower())
            return True
        except ValueError:
            return False

    def add_answer(self, answer):
        if answer.lower() in (answer.lower() for answer in self.answers):
            return False
        else:
            self.answers.append(answer.lower())
            return True

    def raise_value_error(self, error_text):
        raise ValueError(error_text)

    def __str__(self):
        return "Game: " + self.game + ", Question: " + self.question


class TriviaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        global question_start_time
        self.bot = bot
        self.only_execute_on_command = False
        self.load_trivia()

    # Function that runs continuously
    async def tick(self, channel: Channel):
        global question_start_time
        global question_expiry_time
        global next_question_file_update_time
        global trivia_paused
        global grace_period_set
        global current_game

        if (not trivia_paused and
                (channel_is_live or not trivia_config['General']['run_only_when_live'] == 'True')):
            channel_data = await self.bot.fetch_channel(channel.name)
            current_game = channel_data.game_name
            # If time has expired, check to see if there is a current question
            # If there is a current question, depending on settings the answers
            #   may need to be displayed and the points adjusted
            current_time = time.time()
            global current_question_index

            if not current_question_index == -1:
                # There is a current question
                if current_time > question_expiry_time:
                    # The question has expired. End the question.
                    self.log("Tick: Question time exceeded. Ending question.",
                             LoggingLevel.str_to_int.get("Debug"))
                    await self.end_question(channel)
                    grace_period_set = False
                # elif script_settings.create_current_question_file and (current_time > next_question_file_update_time):
                #     # The question has not expired. Display the question and the remaining time.
                #     update_current_question_file(parse_string(script_settings.question_file_ask_string), 1)

            else:
                # There is no current question
                if current_time > question_start_time:
                    # It is time for the next question.
                    if trivia_config['Questions']['automatically_run_questions'] == 'True':
                        # If the settings indicate to run the next question, do so.
                        self.log("Tick: Starting next question.", LoggingLevel.str_to_int.get("Debug"))
                        await self.next_question(channel)
                #     else:
                #         # If the settings indicate to NOT run the next question,
                #         #   set the boolean and display that the next question is ready.
                #         global ready_for_next_question
                #         global readiness_notification_time
                #         ready_for_next_question = True
                #         if readiness_notification_time is None:
                #             readiness_notification_time = (time.time() +
                #                 int(trivia_config.get('Questions',
                #                                       'question_readiness_notify_in_minutes')) * 60)
                #         # if script_settings.create_current_question_file:
                #         #     update_current_question_file("The next question is ready! Type !trivia to begin.",
                #         #                                  time.time() + 86400)
                #         if current_time > readiness_notification_time:
                #             if len(current_questions_list) > 0:
                #                 await ("The next question is ready! Type !trivia to begin.")
                #             readiness_notification_time = (time.time() +
                #                 int(trivia_config.get('Questions',
                #                                       'question_readiness_notify_in_minutes')) * 60)
                # elif script_settings.create_current_question_file and (current_time > next_question_file_update_time):
                #     # It is not time for the next question. Display the remaining time until the next question.
                #     update_current_question_file("Time until next question: " + str(
                #         get_strftime(question_start_time - time.time())) + ".", 1)

    async def execute(self, context: commands.Context):
        from bot_configuration import bot_config
        global channel_is_live
        current_channel = await context.bot.fetch_channel(context.channel.name)
        current_streams = await context.bot.fetch_streams(user_logins=[str(context.channel.name)], type='all')
        channel_is_live = len(current_streams) > 0
        if trivia_config['General']['run_only_when_live'] == 'True' and not \
                channel_is_live:
            return

        global trivia_paused
        global current_question_index
        global current_questions_list
        global master_questions_list
        global current_game
        user_permissions = []
        if bot_config.has_section('Permissions'):
            for section in bot_config.options('Permissions'):
                if context.author.name in bot_config['Permissions'][section]:
                    user_permissions.append(str(section).lower())

        if str(context.message.content).startswith(trivia_config['General']['command_prefix']):
            # Command started with the prefix
            args = str(context.message.content).split(' ')
            args.pop(0)  # remove base command

            if len(args) == 0 and not trivia_paused:
                if (trivia_config['General']['player_permissions'].lower() == 'everyone' or
                        trivia_config['General']['player_permissions'].lower() in
                        user_permissions):
                    global question_start_time
                    global question_expiry_time
                    if len(current_questions_list) == 0:
                        self.log("!Trivia: Called to start new question, but no questions exist.",
                                 LoggingLevel.str_to_int.get("Warn"))
                        if trivia_config['Questions']['enable_game_detection'] == 'True' and \
                                len(master_questions_list) > 0:
                            await context.send(f'@{context.author.name}: Could not load trivia. '
                                               f'No questions exist for the current game.')
                        else:
                            await context.send(f'@{context.author.name}: Could not load trivia. No questions exist.')
                    elif current_question_index == -1:
                        if trivia_config['Questions']['automatically_run_questions'] == 'False' and \
                                ready_for_next_question:
                            self.log("!Trivia: Called to start new question.",
                                     LoggingLevel.str_to_int.get("Debug"))
                            global next_question_file_update_time
                            global readiness_notification_time
                            await self.next_question(context)
                            next_question_file_update_time = time.time()
                            readiness_notification_time = time.time()
                        else:
                            await context.send(f'@{context.author.name}: There is no active trivia question. '
                                               f'The next trivia '
                                               'question arrives in ' + get_formatted_time_diff(
                                                question_start_time))
                    else:
                        await context.send(f'{current_questions_list[current_question_index].as_string()}')
                        await context.send(f'@{context.author.name}: Time remaining on current question: ' +
                                           get_formatted_time_diff(question_expiry_time))
                else:
                    await context.send(f'Sorry, @{context.author.name}, you do not have the '
                                       f'required permissions to '
                                       f'use that command.')
            else:
                subcommand = args.pop(0).lower().strip()

                if subcommand in ['start', 'unpause']:
                    if trivia_config['General']['admin_permissions'].lower() in user_permissions:
                        if trivia_paused:
                            trivia_paused = False
                            self.log("Trivia started with Command.", LoggingLevel.str_to_int.get("Info"))
                            await context.send("Trivia: Trivia started.")
                        else:
                            await context.send('Trivia: Trivia is already running.')
                    else:
                        await context.send(f'Sorry, @{context.author.name}, you do not have the '
                                           f'required permissions to '
                                           f'use that command.')
                elif subcommand in ['stop', 'pause']:
                    if trivia_config['General']['admin_permissions'].lower() in user_permissions:
                        if not trivia_paused:
                            trivia_paused = True
                            self.log("Trivia paused with Command.", LoggingLevel.str_to_int.get("Info"))
                            await context.send(f'@{context.author.name}: Trivia paused.')
                        else:
                            await context.send(f'@{context.author.name}: Trivia is already paused.')
                    else:
                        await context.send(f'Sorry, @{context.author.name}, you do not have the '
                                           f'required permissions to '
                                           f'use that command.')
                elif subcommand == 'load' and not trivia_paused:
                    if trivia_config['General']['admin_permissions'].lower() in user_permissions:
                        if len(current_questions_list) == 0:
                            if trivia_config['Questions']['enable_game_detection'] == 'True' and \
                                    len(master_questions_list) > 0:
                                await context.send(f'@{context.author.name}: No applicable questions exist for the '
                                                   f'currently detected game.')
                            else:
                                await context.send(f'@{context.author.name}: There are no questions available.')
                            return
                        if len(args) == 0:
                            await self.next_question(context)
                        else:
                            try:
                                question_index = int(args[0].strip()) - 1
                                if question_index < 0:
                                    raise ValueError
                                if question_index > len(current_questions_list) - 1:
                                    raise IndexError
                                await self.next_question(context, question_index)

                            except ValueError:
                                await context.send(f'@{context.author.name}: The value supplied to the load '
                                                   'subcommand must be a positive integer.')
                            except IndexError:
                                await context.send(f'@{context.author.name}: The supplied index was too high. '
                                                   f'Please supply a '
                                                   f'question index up to {str(len(current_questions_list))}.')
                    else:
                        await context.send(f'Sorry, {context.author.name}, you do not have the '
                                           f'required permissions to '
                                           f'use that command.')
                elif subcommand == 'game':
                    if trivia_config['General']['admin_permissions'].lower() in user_permissions:
                        if len(args) == 0:
                            await context.send(f'@{context.author.name}: The currently active '
                                               f'game is "{current_game}".')
                        else:
                            game_command = args.pop(0)
                            if game_command == 'detect' and not trivia_paused:
                                if current_channel.game_name.lower() == current_game.lower():
                                    await context.send(f'@{context.author.name}: Twitch reports the current game as "'
                                                       f'{current_channel.game_name.lower()}". '
                                                       f'Currently showing trivia for "{current_game.lower()}".')
                                else:
                                    previous_game = current_game.lower()
                                    current_game = current_channel.game_name.lower()
                                    await context.send(f'@{context.author.name}: Twitch reports the current game as "'
                                                       f'{current_channel.game_name.lower()}. '
                                                       f'Trivia game has been updated from "{previous_game.lower()}" '
                                                       f'to "{current_game.lower()}".')
                                self.load_trivia()

                            elif game_command.startswith('set:') and not trivia_paused:
                                global game_detection_override
                                new_game = game_command[len('set:'):]
                                if len(new_game) == 0:
                                    game_detection_override = None
                                    await context.send(f'@{context.author.name}: Game detection override disabled.')
                                else:
                                    game_detection_override = new_game.lower().strip()
                                    await context.send(f'@{context.author.name}: Game detection override updated to '
                                                       f'{game_detection_override}.')
                                self.load_trivia()
                    else:
                        await context.send(f'Trivia: Sorry, {context.author.name}, you do not have the '
                                           f'required permissions to '
                                           f'use that command.')
                elif subcommand == 'count':
                    if trivia_config['Questions']['enable_game_detection'] == 'True':
                        await context.send(f'@{context.author.name}: There are {str(len(current_questions_list))} '
                                           f'questions from '
                                           f'the current game and {str(len(master_questions_list))} questions total.')
                    else:
                        await context.send(f'@{context.author.name}: There are '
                                           f'{str(len(master_questions_list))} questions total.')
                elif subcommand == 'answers':
                    if trivia_config['General']['admin_permissions'].lower() in user_permissions:
                        if len(args) == 0:
                            if current_question_index == -1:
                                await context.send(f'@{context.author.name}: There is no question currently loaded.')
                            else:
                                await context.send(f'@{context.author.name}: The answers to the '
                                                   f'current question are: ' +
                                                   ', '.join(current_questions_list[current_question_index]
                                                             .get_answers()) + '.')
                        else:
                            try:
                                question_index = int(args[0])
                                if question_index < 0:
                                    raise ValueError
                                if question_index > len(current_questions_list) - 1:
                                    raise IndexError
                                await context.send(f'@{context.author.name}: The answers to that question are: ' +
                                                   ', '.join(current_questions_list[question_index]
                                                             .get_answers()) + '.')
                            except ValueError:
                                await context.send(f'@{context.author.name}: The value supplied to the load '
                                                   'subcommand must be a positive integer.')
                            except IndexError:
                                await context.send(f'@{context.author.name}: The supplied index was too high. '
                                                   f'Please supply a '
                                                   f'question index up to {str(len(current_questions_list) - 1)}.')
                    else:
                        await context.send(f'Trivia: Sorry, {context.author.name}, you do not have the '
                                           f'required permissions to '
                                           f'use that command.')
                elif subcommand == 'add':
                    if trivia_config['General']['admin_permissions'].lower() in user_permissions:
                        if len(args) == 0:
                            await context.send(f'@{context.author.name}: Syntax for add command is "'
                                               f'{trivia_config["General"]["command_prefix"]} '
                                               f'add (game:<name of game>|) '
                                               f'(points:<positive integer number of points>|) '
                                               f'question:<question>| '
                                               f'answers:<comma-separated list of string answers>"')
                        else:
                            args = ' '.join(args).split('|')
                            new_points = None
                            new_game = None
                            new_question_text = None
                            new_answers = None
                            for arg in args:
                                if arg.lower().startswith('points:'):
                                    try:
                                        new_points = arg[len('points:'):].strip()
                                        new_points = int(new_points)
                                        if new_points < 0:
                                            raise ValueError
                                    except ValueError:
                                        await context.send(f'@{context.author.name}: The points supplied, '
                                                           f'{new_points}, were not a positive '
                                                           f'integer.')
                                        return
                                elif arg.lower().startswith('game:'):
                                    new_game = arg[len('game:'):].strip()
                                elif arg.lower().startswith('question:'):
                                    new_question_text = arg[len('question:'):].strip()
                                elif arg.lower().startswith('answers:'):
                                    new_answers = \
                                        [answer.strip() for answer in arg[len('answers:'):].strip().split(',')]

                            if new_question_text is None or new_answers is None:
                                await context.send(
                                    f'@{context.author.name}: Syntax for add command is "'
                                    f'{trivia_config["General"]["command_prefix"]} '
                                    f'add (game:<name of game>|) '
                                    f'(points:<positive integer number of points>|) '
                                    f'question:<question>| '
                                    f'answers:<comma-separated list of string answers>"')
                                return

                            new_question = Question(
                                points=new_points if new_points is not None else 0,
                                game=new_game if new_game is not None else (current_game if current_game else 'none'),
                                question=new_question_text,
                                answers=new_answers
                            )
                            master_questions_list.append(new_question)
                            if (trivia_config['Questions']['enable_game_detection'] == 'True' and
                                    current_game == new_question.get_game()):
                                current_questions_list.append(new_question)
                            if self.save_trivia():
                                await context.send(f'@{context.author.name}: Question added.')
                    else:
                        await context.send(f'Trivia: Sorry, {context.author.name}, you do not have the '
                                           f'required permissions to '
                                           f'use that command.')
                elif subcommand == 'remove':
                    if trivia_config['General']['admin_permissions'].lower() in user_permissions:
                        if len(args) == 0:
                            await context.send(f'@{context.author.name}: Syntax for remove command is '
                                               f'"{trivia_config["General"]["command_prefix"]} '
                                               f'remove <index>".')
                        else:
                            try:
                                question_index = int(args[0]) - 1
                                if question_index < 0:
                                    raise ValueError
                                if question_index > len(current_questions_list) - 1:
                                    raise IndexError

                                old_question = current_questions_list.pop(question_index)
                                try:
                                    master_questions_list.remove(old_question)
                                    if self.save_trivia():
                                        await context.send(f'@{context.author.name}: Question removed.')
                                except ValueError:
                                    await context.send(f'@{context.author.name}: There was an unexpected '
                                                       f'error removing the '
                                                       f'question at index {str(question_index)}: The question '
                                                       f'was not found in the list of questions.')
                                    self.log(f'Failed to remove question from master questions list: '
                                             f'{old_question.as_string()}.',
                                             log_level=LoggingLevel.str_to_int.get("Error"))
                            except ValueError:
                                await context.send(f'@{context.author.name}: The index value supplied '
                                                   f'must be a positive integer.')
                            except IndexError:
                                await context.send(f'@{context.author.name}: The supplied index was too high. '
                                                   f'Please supply a '
                                                   f'question index up to {str(len(current_questions_list) - 1)}.')

                    else:
                        await context.send(f'Trivia: Sorry, {context.author.name}, you do not have the '
                                           f'required permissions to '
                                           f'use that command.')
                elif subcommand == 'modify':
                    if trivia_config['General']['admin_permissions'].lower() in user_permissions:
                        if len(args) < 3:
                            await context.send(f'@{context.author.name}: Syntax for add command is "'
                                               f'{trivia_config["General"]["command_prefix"]} '
                                               f'modify <question_index>|<game/points/question/answers/'
                                               f'addanswer/delanswer|<new value(s)>."')
                        else:
                            try:
                                question_index = int(args[0]) - 1
                                if question_index < 0:
                                    raise ValueError
                                if question_index > len(current_questions_list) - 1:
                                    raise IndexError

                                modification_type = args[1].lower()
                                valid_modifications_types = ['game', 'points', 'question',
                                                             'answers', 'addanswer', 'delanswer']
                                if modification_type not in valid_modifications_types:
                                    await context.send(f'@{context.author.name}: The second argument for the modify '
                                                       f'subcommand must '
                                                       f'be one of {str(valid_modifications_types)}.')
                                    return

                                question_to_modify = current_questions_list[question_index]
                                new_value = args[2]
                                if modification_type == 'game':
                                    question_to_modify.set_game(new_value)
                                elif modification_type == 'points':
                                    try:
                                        new_value = int(new_value)
                                        if new_value < 0:
                                            raise ValueError
                                        question_to_modify.set_points(new_value)
                                    except ValueError:
                                        await context.send(f'@{context.author.name}: The new points value must '
                                                           f'be a positive integer.')
                                        return
                                elif modification_type == 'question':
                                    question_to_modify.set_question(new_value)
                                elif modification_type == 'answers':
                                    question_to_modify.set_answers([answer.strip() for answer in
                                                                    new_value.strip().split(',')])
                                elif modification_type == 'addanswer':
                                    question_to_modify.add_answer(new_value)
                                elif modification_type == 'delanswer':
                                    question_to_modify.remove_answer(new_value)

                                if self.save_trivia():
                                    await context.send(f'@{context.author.name}: Question modified.')

                            except ValueError:
                                await context.send(f'@{context.author.name}: The index value supplied '
                                                   f'must be a positive integer.')
                            except IndexError:
                                await context.send(f'@{context.author.name}: The supplied index was too high. '
                                                   f'Please supply a '
                                                   f'question index up to {str(len(current_questions_list) - 1)}.')

                    else:
                        await context.send(f'Trivia: Sorry, {context.author.name}, you do not have the '
                                           f'required permissions to '
                                           f'use that command.')
        else:
            # Don't check for answers if trivia is paused, there is no active question, or if the user does
            #   not have permissions
            if (not trivia_paused and not current_question_index == -1 and
                    (trivia_config['General']['player_permissions'].lower() == 'everyone' or
                     trivia_config['General']['player_permissions'].lower() in user_permissions)):
                return

            # Process chat for possible winning answers
            await self.check_for_match(context)

    async def next_question(self, messageable: Channel | commands.Context, question_index=-1):
        global current_questions_list
        global question_start_time

        if isinstance(messageable, commands.Context):
            current_channel = await self.bot.fetch_channel(messageable.channel.name)
        elif isinstance(messageable, Channel):
            current_channel = await self.bot.fetch_channel(messageable.name)
        else:
            raise RuntimeError()

        # Check to see if questions exist
        if len(current_questions_list) > 0:
            global current_question_index
            global question_expiry_time
            global ready_for_next_question
            global current_game
            global game_detection_override

            if (trivia_config['Questions']['enable_game_detection'] == 'True' and not
                    game_detection_override):
                current_game = current_channel.game_name.lower()

            # Log the previous question to prevent duplicates
            previous_question_index = current_question_index

            # Start up a new question, avoiding using the same question twice in a row if possible
            if question_index == -1:
                if previous_question_index != -1 and len(current_questions_list) > 1:
                    while True:
                        current_question_index = randint(a=0, b=len(current_questions_list))
                        if current_question_index != previous_question_index:
                            break
                else:
                    current_question_index = randint(a=0, b=len(current_questions_list))
            else:
                current_question_index = question_index

            # Set the question expiration time
            question_expiry_time = (time.time() +
                                    (int(trivia_config['Questions']['duration_in_minutes']) * 60))
            self.log("NextQuestion: Next Question at " + get_formatted_time_diff(question_expiry_time) + ".",
                     LoggingLevel.str_to_int.get("Debug"))
            ready_for_next_question = False
            await messageable.send(f'Question {str(int(current_question_index) + 1)} '
                                   f'{current_questions_list[current_question_index].as_string()}')
        else:
            # If questions do not exist, try again every 60 seconds
            global question_start_time
            self.log("NextQuestion: No questions exist. Trying again in 60 seconds.",
                     LoggingLevel.str_to_int.get("Warn"))
            question_start_time = time.time() + 60

    @staticmethod
    async def end_question(messageable: Channel | commands.Context):
        global current_question_index
        global question_start_time
        global winners

        if isinstance(messageable, Channel):
            current_channel = messageable
        elif isinstance(messageable, commands.Context):
            current_channel = messageable
        else:
            raise RuntimeError()

        # First, check to see if there is an active question. If there is no active question, nothing needs to be done.
        if not current_question_index == -1:
            winner_names = list(winners.values())
            # Post message rewarding users
            if len(winner_names) > 2:
                await current_channel.send(f'Trivia: {", ".join(winner_names[:-1]) + ", and " + str(winner_names[-1])} '
                                           f'answered correctly!')
            elif len(winner_names) == 2:
                await current_channel.send(f'Trivia: {" and ".join(winner_names)} answered correctly!')
            elif winner_names:
                await current_channel.send(f'Trivia: {winner_names[0]} answered correctly!')
            else:
                # No winners were detected. Display expiration message.
                await current_channel.send(f'Trivia: Nobody answered the previous question. The answers were '
                                           f'{str(current_questions_list[current_question_index].get_answers())}')
            winners = {}

        # End current question and set the next question's start time.
        current_question_index = -1
        question_start_time = (time.time() +
                               (int(trivia_config['Questions']['cooldown_between_questions_in_minutes'])
                                * 60))

        global ready_for_next_question
        ready_for_next_question = False

    async def check_for_match(self, context: commands.Context):
        global current_question_index
        global winners
        try:
            current_question = current_questions_list[current_question_index]
            current_answers = current_question.get_answers()
            for answer in current_answers:
                if context.message.content.lower().strip() == answer.lower().strip():
                    # We have a match. Add them to the dictionary of correct users,
                    #   then check to see if the question needs to be ended.
                    winners[context.author.id] = context.author.name
                    self.log("CheckForMatch: Match detected between answer " + answer + " and message "
                             + context.message.content + ". User " + context.author.name +
                             " added to the list of correct users.",
                             LoggingLevel.str_to_int.get("Debug"))
                    # Check to see if the maximum number of winners has been met
                    if 0 < int(trivia_config['Rewards']['number_of_winners']) <= len(winners):
                        self.log("CheckForMatch: Number of winners achieved. Ending question.",
                                 LoggingLevel.str_to_int.get("Debug"))
                        # If it has, immediately end the question
                        await self.end_question(context)
                    else:
                        # If the maximum number of winners has not been met, but the grace period is being
                        #   used, apply the grace period to end the question if it has not already been applied
                        if trivia_config['Rewards']['use_grace_period'] == 'True':
                            global question_expiry_time
                            global grace_period_set
                            if not grace_period_set:
                                question_expiry_time = \
                                    (time.time() +
                                     int(trivia_config['Rewards']['multiple_winner_grace_period_in_seconds']))
                                grace_period_set = True
        except IndexError:
            current_question_index = -1

    @staticmethod
    def log(log_string: str, log_level=LoggingLevel.str_to_int.get("All")):
        if trivia_config['General']['enable_file_logging'] == 'True':
            log_to_file(TRIVIA_LOG_PATH, log_string, log_level)

    def save_trivia(self):
        try:
            games = set()
            for question in master_questions_list:
                games.add(question.game.lower())

            for game in games:
                with open(os.path.join(TRIVIA_DATA_FOLDER, game.lower() + '.json'), 'w') as question_file:
                    question_file.write(
                        json.dumps([question.to_json() for question in
                                    master_questions_list if question.game.lower() == game])
                    )

            # # if the trivia file does not exist, create it
            # if not os.path.exists(TRIVIA_DATA_PATH):
            #     with open(TRIVIA_DATA_PATH, 'w') as outfile:
            #         outfile.write(json.dumps({}))
            #     self.log("SaveTrivia: The trivia file was not found. A new one was created.",
            #              LoggingLevel.str_to_int.get("Warn"))
            #
            # # record the questions
            # with open(TRIVIA_DATA_PATH, 'w') as outfile:
            #     outfile.seek(0)
            #     # When writing the Questions to disk, use the Question.toJSON() function
            #     json.dump(master_questions_list, outfile, indent=4, default=lambda q: q.toJSON())
            #     outfile.truncate()
            #     self.log("SaveTrivia: The trivia file was successfully updated.",
            #               LoggingLevel.str_to_int.get("Debug"))

            return True

        except IOError as e:
            self.log("SaveTrivia: Unable to save trivia questions: " + str(e), LoggingLevel.str_to_int.get("Fatal"))
            raise e

    def load_trivia(self):
        # Check if the length of the master questions list is 0. If it is, we need to load questions.
        global master_questions_list
        global current_questions_list
        global current_question_index

        # If there is a question currently running, end that question.
        if current_question_index != -1:
            global question_start_time
            current_question_index = -1
            question_start_time = (time.time() +
                                   (int(trivia_config['Questions']['cooldown_between_questions_in_minutes'])
                                    * 5))

        os.makedirs(TRIVIA_DATA_FOLDER, exist_ok=True)
        for root, dirs, files in os.walk(TRIVIA_DATA_FOLDER):
            for file in files:
                if file.endswith('.json'):
                    try:
                        with open(os.path.join(root, file), 'r') as infile:
                            object_data = json.load(infile)  # Load the json data

                        # For each object/question in the object_data, create new questions
                        #   and feed them to the master_questions_list
                        # If game detection is off, feed them to the g
                        global current_questions_list
                        global current_game
                        for question in object_data:
                            new_question = Question(game=question["Game"],
                                                    points=question["Points"],
                                                    question=question["Question"],
                                                    answers=question["Answers"])
                            master_questions_list.append(new_question)
                    except ValueError:
                        self.log(f'LoadTrivia: Question file {file} exists, but contained no data.',
                                 LoggingLevel.str_to_int.get("Warn"))
        else:
            self.log("LoadTrivia: No questions files exist in the questions directory.",
                     LoggingLevel.str_to_int.get("Warn"))

        del current_questions_list[:]
        # If the length of the master questions list is greater than 0,
        #   we can check if the user is using game detection
        if trivia_config['Questions']['enable_game_detection'] == 'True':
            global current_game
            # User is using game detection. Iterate over the master list to get games matching their current game.
            for i in range(len(master_questions_list)):
                if master_questions_list[i].get_game() == current_game:
                    current_questions_list.append(master_questions_list[i])
        else:
            # User is not using game detection. Copy the master list to the current questions list
            current_questions_list = master_questions_list

        self.log("LoadTrivia: Questions loaded into master list: " + str(
            len(master_questions_list)) + ". Questions currently being used: " + str(len(current_questions_list)),
                 LoggingLevel.str_to_int.get("Info"))


trivia_config.read_dict(DEFAULT_CONFIG)
if len(trivia_config.read(TRIVIA_CONFIG_PATH)) == 0:
    with open(TRIVIA_CONFIG_PATH, 'w') as config_file:
        trivia_config.write(config_file)
