#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, configparser, datetime, subprocess, shutil

class MegasyncErrors(Exception): pass

class Configuration():
    def __init__(self):
        config = configparser.ConfigParser()
        try:
            config.read("megasync.cfg")
        except IOError:
            raise MegasyncErrors("Unable to read configuration file.")
        for option in ("password", "username", "prefix", "platform_id"):
            try:
                exec(compile("self.{0} = config['DEFAULT']['{0}']".format(option), {}, "exec"))
            except KeyError:
                raise MegasyncErrors("No option found: {0}".format(option))


class Megaquery():
    def __init__(self, file_prefix, username, user_passwd, archive_passwd, platform_prefix):
        self.prefix = file_prefix       # Часть, с которой начинается имя файла архива и директории.
        self.user = username            # Имя пользователя Меги.
        self.user_pass = user_passwd    # Пароль пользователя Меги
        self.platform = platform_prefix     # Идентификатор платформы.
        self.archive_pass = archive_passwd  # Пароль, с которым будет создаваться (и распаковываться) архив.

    def find_newest(self, flist):
        """
        Функция для выделения из предложенного списка файлов одного, самого нового и подходящего под шаблон.
        На вход принимает список имён файлов.
        :param flist:
        :return:
        """
        times = []
        # Получаем список времён создания из всех файлов, в которых время указано в подходящем под шаблон формате:
        for f in flist:
            try:
                times.append((datetime.datetime.strptime(f[(len(self.prefix) + 1):-(len(self.platform) + 4)], '%d_%m_%y_%H_%M_%S'), f[-(len(self.platform) + 4):]))
            except ValueError:
                pass
        # Сортируем этот список и возвращаем имя файла, соответствующее самому новому из них:
        # Если ни одного подходящего файла не нашлось, т.е. длина списка нулевая, возвращаем единицу,
        if len(times) == 0:
            return (1,)
        # иначе возвращаем 0 и этот самый файл:
        else:
            times.sort()
            return (0, self.prefix + "_" + times[-1][0].strftime('%d_%m_%y_%H_%M_%S') + times[-1][1])


    def find_newest_mega(self):
        """
        Функция для получения из указанной директории Меги имени новейшего файла.
        Кроме того, если отсутствует указанная директория, она её создаёт.
        :return:
        """
        try:
            temp = subprocess.check_output("megals -u {0} -p {1} --names --reload /Root".format(self.user, self.user_pass), shell=True)
            temp_files = [x for x in str(temp)[2:-1].split(r"\n")]
            if self.prefix not in temp_files:
                subprocess.check_output("megamkdir -u {0} -p {1} --reload /Root/{2}".format(self.user, self.user_pass, self.prefix), shell=True)
            megacall = subprocess.check_output("megals -u {0} -p {1} --names --reload /Root/{2}".format(self.user, self.user_pass, self.prefix), shell=True)
        except subprocess.CalledProcessError:
            raise MegasyncErrors("Unable to list MEGA files.")
        else:
            # Получаем из строки список файлов и сохраняем из него только те, которые подходят под шаблон:
            files = [x for x in str(megacall)[2:-1].split(r"\n") if x.startswith(self.prefix) and x.endswith(".7z")]
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
        files = [x for x in os.listdir(".") if x.startswith(self.prefix) and x.endswith(".7z")]
        return self.find_newest(files)

    def zip(self):
        """
        Функция для упаковки указанной директории в файл согласно шаблону.
        :return:
        """
        filename = self.prefix + "_" + datetime.datetime.now().strftime('%d_%m_%y_%H_%M_%S') + "_" + self.platform + ".7z"
        try:
            subprocess.check_output("7z a -mhe=on -p{0} {1} {2}".format(self.archive_pass, filename, self.prefix), shell=True)
        except subprocess.CalledProcessError:
            raise MegasyncErrors("Unable to create archive.")
        else:
            return filename

    def unzip(self, filename):
        """
        Функция для распаковки указанного файла и замены старой версии соответствующей директории.
        :return:
        """
        olddir = self.prefix + "_old"
        if self.prefix in os.listdir("."):
            try:
                shutil.rmtree(olddir, ignore_errors=True)
                os.rename(self.prefix, olddir)
            except:
                raise MegasyncErrors("Unable to rename directory.")
            try:
                subprocess.check_output("7z x -p{0} {1}".format(self.archive_pass, filename), shell=True)
            except subprocess.CalledProcessError:
                raise MegasyncErrors("Unable to extract archive.")
        else:
            raise MegasyncErrors("No data to compress!")



def exitfunc(message, number):
    print("\n%s\n" % message)
    sys.exit(number)


if __name__ == "__main__":
    try:
        # Читаем настройки из файла:
        conf = Configuration()
    except MegasyncErrors as err:
        exitfunc(err, 1)
    # Запрашиваем у юзера пароль от Меги:
    mega_passwd = input("Enter MEGA password: ")
    # Инициализируем класс для работы с Мегой:
    mega = FileOpers(conf.prefix, conf.username, mega_passwd, conf.password, conf.platform_id)
    try:
        # Ищем самый свежий файл из Меги. Получаем кортеж из признака успеха (0|1) и собственно файла, если он есть:
        megafile = mega.find_newest_mega()
    except MegasyncErrors as err:
        exitfunc(err, 1)
    # Ищем самый новый файл на компьютере. Получаем в виде кортежа из кода ошибки (0/1) и собственно файла:
    local_file = mega.find_newest_local()
    # Если на Меге не найдено ни одного подходящего файла:
    if megafile[0] == 1:
        # Если к тому же и локального файла нет:
        if local_file[0] == 1:
            # То ищем директорию, которую можно запаковать:
            if conf.prefix in os.listdir("."):
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
            mega_file_age = datetime.datetime.strptime(megafile[1][(len(conf.prefix) + 1):-(len(conf.platform_id) + 4)], '%d_%m_%y_%H_%M_%S')
            local_file_age = datetime.datetime.strptime(local_file[1][(len(conf.prefix) + 1):-(len(conf.platform_id) + 4)], '%d_%m_%y_%H_%M_%S')
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
                    exitfunc("File '%s' downloaded successfully."% megafile[1], 0)
