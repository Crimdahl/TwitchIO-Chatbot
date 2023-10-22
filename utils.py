from time import time
from datetime import datetime
from math import floor


def get_formatted_time_diff(end_time: float, start_time: float = None):
    if not start_time:
        start_time = time()
    hours, minutes, seconds = str(datetime.fromtimestamp(end_time) - datetime.fromtimestamp(start_time)).split(":")
    return_string = ''
    if int(hours) > 0:
        return_string += f'{str(int(hours))} hours'
    if int(minutes) > 0:
        if return_string:
            return_string += f', {str(int(minutes))} minutes'
        else:
            return_string += f'{str(int(minutes))} minutes'
    if return_string:
        return_string += f', {str(floor(float(seconds)))} seconds'
    else:
        return_string += f'{str(floor(float(seconds)))} seconds'

    return return_string


class LoggingLevel:
    All = 1
    Debug = 2
    Info = 3
    Warn = 4
    Fatal = 5
    Nothing = 6

    str_to_int = {
        "All": 1,
        "Debug": 2,
        "Info": 3,
        "Warn": 4,
        "Fatal": 5,
        "Nothing": 6
    }

    int_to_string = {
        1: "All",
        2: "Debug",
        3: "Info",
        4: "Warn",
        5: "Fatal",
        6: "Nothing"
    }


def log_to_file(log_file_path: str, log_string: str, log_level=LoggingLevel.All):
    """
    Log a string to file with an appropriate severity level

    :param log_file_path: String path to the logging file
    :param log_string: String that should be logged to the file
    :param log_level: LoggingLevel indicating the log entry severity
    :return:
    """
    with open(log_file_path, 'a+') as log_file:
        log_file.writelines(
            str(datetime.now()).ljust(26) +
            " " +
            str(LoggingLevel.int_to_string.get(log_level) +
                ":").ljust(10) +
            log_string +
            "\n")
