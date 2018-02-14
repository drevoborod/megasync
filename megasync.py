#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ToDo: 1. Сделать проверку кодировки файла настроек.

import sys


def exitfunc(message, number):
    print("\n%s\n" % message)
    if sys.version_info[0] == 2:
        raw_input("Press Enter to finish.\n")   # For python2 compatibility
    else:
        input("Press Enter to finish.\n")
    sys.exit(number)


if sys.version_info[0] < 3:
    exitfunc("Major version of Python interpreter should be at least equal to 3.\n"
             "Your version is: %s" % sys.version, 1)
else:
    if sys.version_info[1] < 4:
        exitfunc("Minor version of Python interpreter should be at least equal to 4\n"
                 "Your version is: %s" % sys.version, 1)


import os
import configparser
import argparse
import datetime
import subprocess
import shutil
import stat
import re
import getpass


class MegasyncErrors(Exception): pass


class Configuration():
    def __init__(self, file, mandatory, optional):
        config = configparser.ConfigParser()
        try:
            config.read(file)
        except IOError:
            raise MegasyncErrors("Unable to read configuration file.")
        for option in mandatory:
            try:
                setattr(self, option, config['DEFAULT'][option])
            except KeyError:
                raise MegasyncErrors("No option found: {0}".format(option))
        for option in optional:
            try:
                setattr(self, option, config['DEFAULT'][option])
            except KeyError:
                pass


class Megaquery:
    def __init__(self, file_prefix, username, user_passwd, archive_passwd, platform_prefix):
        self.prefix = file_prefix       # Часть, с которой начинается имя файла архива и директории.
        self.user = username            # Имя пользователя Меги.
        self.user_pass = user_passwd    # Пароль пользователя Меги
        self.platform = "_" + platform_prefix     # Идентификатор платформы.
        self.archive_pass = archive_passwd  # Пароль, с которым будет создаваться (и распаковываться) архив.

    def find_regular(self, filename):
        """
        Функция анализирует строку (по идее - название файла) на соотвествие с помощью регулярного выражения.
        :param filename:
        :return:
        """
        template = self.prefix + r"_[0-9]{1,2}_[0-9]{1,2}_[0-9]{1,2}_[0-9]{1,2}_[0-9]{1,2}_[0-9]{1,2}_[a-zA-Z]*\.7z"
        if re.compile(template).match(filename):
            return True

    def strip_tail(self, filename):
        """
        Функция для выделения из имени файла идентификатора платформы вместе с расширением.
        :param filename:
        :return:
        """
        template = r"_[a-zA-Z]*\.7z$"
        # Возвращаем кусок между последним символом подчёркивания и расширением
        try:
            res = re.compile(template).search(filename).group()
        except AttributeError:
            res = ''
        return res

    def find_newest(self, flist):
        """
        Функция для выделения из предложенного списка файлов одного, самого нового и подходящего под шаблон.
        На вход принимает список имён файлов.
        :param flist:
        :return:
        """
        # Получаем список времён создания из всех файлов, в которых время указано в подходящем под шаблон формате:
        paramsdict = {}
        for f in flist:
            # Постфикс файла + расширение:
            t = self.strip_tail(f)
            # Строка со временем из имени файла:
            param = f[(len(self.prefix) + 1):-len(t)]
            try:
                # Переводим строку со временем в формат datetime и добавляем, если не выпадает ошибка:
                paramsdict[datetime.datetime.strptime(param, '%d_%m_%y_%H_%M_%S')] = (param, t)
            except ValueError:
                pass
        # Если ни одного подходящего файла не нашлось, т.е. длина списка нулевая, возвращаем единицу,
        if len(paramsdict) == 0:
            return (1,)
        # иначе возвращаем 0 и самый новый файл:
        else:
            newest = max(paramsdict.keys())
            return (0, self.prefix + "_" + paramsdict[newest][0] + paramsdict[newest][1])

    def find_newest_mega(self):
        """
        Функция для получения из указанной директории Меги имени новейшего файла.
        Кроме того, если отсутствует указанная директория, функция её создаёт.
        :return:
        """
        try:
            files = subprocess.check_output("megals -u {0} -p {1} --names --reload /Root".format(self.user, self.user_pass), shell=True, universal_newlines=True).split("\n")
            if self.prefix not in files:
                subprocess.check_output("megamkdir -u {0} -p {1} --reload /Root/{2}".format(self.user, self.user_pass, self.prefix), shell=True)
            megacall = subprocess.check_output("megals -u {0} -p {1} --names --reload /Root/{2}".format(self.user, self.user_pass, self.prefix), shell=True, universal_newlines=True)
        except subprocess.CalledProcessError:
            raise MegasyncErrors("Unable to list MEGA files.")
        else:
            # Получаем из строки список файлов и сохраняем из него только те, которые подходят под шаблон:
            files = filter(self.find_regular, megacall.split("\n"))
            return self.find_newest(files)

    def get(self, filename):
        """
        Функция для получения файла с Меги.
        :param filename:
        :return:
        """
        try:
            subprocess.check_output("megaget -u {0} -p {1} --reload /Root/{2}/{3}".format(self.user, self.user_pass, self.prefix, filename), shell=True)
        except subprocess.CalledProcessError:
            raise MegasyncErrors("Unable to get MEGA file.")

    def send(self, filename):
        """
        Функция для отправки файла на Мегу.
        :param filename:
        :return:
        """
        try:
            subprocess.check_output("megaput -u {0} -p {1} --reload --path /Root/{2} {3}".format(self.user, self.user_pass, self.prefix, filename), shell=True)
        except subprocess.CalledProcessError:
            raise MegasyncErrors("Unable to upload file to MEGA.")


class FileOpers(Megaquery):
    def find_newest_local(self):
        """
        Функция для получения самого свежего подходящего файла из локальных.
        :return:
        """
        files = filter(self.find_regular, os.listdir(os.curdir))
        return self.find_newest(files)

    def zip(self):
        """
        Функция для упаковки указанной директории в файл согласно шаблону.
        :return:
        """
        if self.prefix not in os.listdir(os.curdir):
            raise MegasyncErrors("Directory to pack not found.")
        filename = self.prefix + "_" + datetime.datetime.now().strftime('%d_%m_%y_%H_%M_%S') + self.platform + ".7z"
        try:
            subprocess.check_output("7z a -mhe=on -p{0} {1} {2}".format(self.archive_pass, filename, self.prefix), shell=True)
        except subprocess.CalledProcessError as err:
            raise MegasyncErrors("Unable to create archive: %s" % err)
        else:
            return filename

    def unzip(self, filename):
        """
        Функция для распаковки указанного файла и замены старой версии соответствующей директории.
        Если подготовительный этап (удаление старой и переименование новой директории) фейлится,
        то скачанный файл удаляется во избежание путаницы.
        Если архив просто не удаётся распаковать, то файл не удаляется.
        :return:
        """
        olddir = self.prefix + "_old"
        if self.prefix in os.listdir(os.curdir):
            try:
                shutil.rmtree(olddir, ignore_errors=False, onerror=del_rw)
            except FileNotFoundError:
                pass
            except Exception as err:
                os.remove(filename)
                raise MegasyncErrors("Unable to remove old directory. %s." % err)
            try:
                os.rename(self.prefix, olddir)
            except Exception:
                os.remove(filename)
                raise MegasyncErrors("Unable to rename directory.")
        try:
            subprocess.check_output("7z x -p{0} {1}".format(self.archive_pass, filename), shell=True)
        except subprocess.CalledProcessError:
            os.remove(filename)
            raise MegasyncErrors("Unable to extract archive '%s'." % filename)


def del_rw(func, name, exc_info):
    """
    Функция для удаления файлов только для чтения под Windows и Unix.
    """
    try:
        if sys.platform == "win32":
            os.chmod(name, stat.S_IWRITE)
            os.remove(name)
        else:
            # Даём юзеру права на запись к директории, содержащей неудаляемый файл:
            os.chmod(os.path.split(name)[0], stat.S_IRWXU)
            if os.path.isdir(name):
                shutil.rmtree(name, ignore_errors=False, onerror=del_rw)
            elif os.path.isfile(name):
                os.remove(name)
    except Exception as err:
        raise err


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--commit", action="store_true", help="Commit changes and push them to Mega.")
    return parser.parse_args()



if __name__ == "__main__":

    config_file = "megasync.cfg"
    mandatory_settings = "username", "prefix"
    optional_settings = "password", "platform_id"

    # Параметры командной строки:
    args = get_args()
    try:
        # Читаем настройки из файла:
        conf = Configuration(config_file, mandatory_settings, optional_settings)
    except MegasyncErrors as err:
        exitfunc(err, 1)
    # Запрашиваем у юзера пароль от Меги:
    mega_passwd = getpass.getpass("Enter MEGA password: ")
    # Если нет пароля для архива, то тоже запрашиваем его у пользователя:
    if hasattr(conf, "password"):
        archive_password = conf.password
    else:
        archive_password = getpass.getpass("Enter password for an archive: ")
    # Инициализируем класс для работы с Мегой:
    mega = FileOpers(conf.prefix, conf.username, mega_passwd, archive_password, conf.platform_id if hasattr(conf, "platform_id") else '')
    try:
        # Ищем самый свежий файл из Меги. Получаем кортеж из признака успеха (0|1) и собственно файла, если он есть:
        megafile = mega.find_newest_mega()
    except MegasyncErrors as err:
        exitfunc(err, 1)
    # Ищем самый новый файл на компьютере. Получаем в виде кортежа из кода ошибки (0/1) и собственно файла:
    local_file = mega.find_newest_local()
    # Если указан ключ командной строки "-c", то запаковать имеющуюся директорию и отправить на Мегу:
    if args.commit:
        try:
            new_file = mega.zip()
            mega.send(new_file)
            exitfunc("File '%s' successfully uploaded." % new_file, 0)
        except MegasyncErrors as err:
            exitfunc(err, 1)
    # Если на Меге не найдено ни одного подходящего файла:
    if megafile[0] == 1:
        # Если к тому же и локального файла нет:
        if local_file[0] == 1:
            # То ищем директорию, которую можно запаковать:
            if conf.prefix in os.listdir(os.curdir):
                try:
                    # Запаковываем нужный локальный файл:
                    zipped = mega.zip()
                    # И шлём его на Мегу:
                    mega.send(zipped)
                except MegasyncErrors as err:
                    exitfunc(err, 1)
                else:
                    exitfunc("File '%s' has been sent successfully." % zipped, 0)
            else:
                # Если нет и директории, то просто выходим:
                exitfunc("No files to work with!", 1)
        # Если локальный файл есть, то шлём его на Мегу:
        else:
            try:
                mega.send(local_file[1])
            except MegasyncErrors as err:
                exitfunc(err, 1)
            else:
                exitfunc("File '%s' has been sent successfully." % local_file[1], 0)
    # Есла на Меге найден подходящий файл, то:
    elif megafile[0] == 0:
        # Если локально подходящий под шаблон файл не найден:
        if local_file[0] == 1:
            try:
                # То скачиваем его с Меги:
                mega.get(megafile[1])
                # И распаковываем:
                mega.unzip(megafile[1])
            except MegasyncErrors as err:
                exitfunc(err, 1)
            else:
                exitfunc("File '%s' downloaded successfully." % megafile[1], 0)
        # Если оба файла - и локальный, и на Меге - одинаковые, то просто выходим:
        elif local_file[1] == megafile[1]:
            exitfunc("Nothing to do.", 0)
        # Если локально подходящий под шаблон файл найден, то нужно выяснить, старше он или моложе того, что на Меге:
        else:
            mega_file_age = datetime.datetime.strptime(megafile[1][(len(conf.prefix) + 1):-len(mega.strip_tail(megafile[1]))], '%d_%m_%y_%H_%M_%S')
            local_file_age = datetime.datetime.strptime(local_file[1][(len(conf.prefix) + 1):-len(mega.strip_tail(local_file[1]))], '%d_%m_%y_%H_%M_%S')
            # Если локальный старше:
            if mega_file_age < local_file_age:
                try:
                    # То заливаем его на Мегу:
                    mega.send(local_file[1])
                except MegasyncErrors as err:
                    exitfunc(err, 1)
                else:
                    exitfunc("File '%s' successfully uploaded." % local_file[1], 0)
            # Если файл с Меги старше:
            else:
                try:
                    # Скачиваем его и распаковываем локально:
                    mega.get(megafile[1])
                    mega.unzip(megafile[1])
                except MegasyncErrors as err:
                    exitfunc(err, 1)
                else:
                    exitfunc("File '%s' downloaded successfully." % megafile[1], 0)
