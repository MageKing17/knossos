## Copyright 2014 Knossos authors, see NOTICE file
##
## Licensed under the Apache License, Version 2.0 (the "License");
## you may not use this file except in compliance with the License.
## You may obtain a copy of the License at
##
##     http://www.apache.org/licenses/LICENSE-2.0
##
## Unless required by applicable law or agreed to in writing, software
## distributed under the License is distributed on an "AS IS" BASIS,
## WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
## See the License for the specific language governing permissions and
## limitations under the License.

import logging
import os
import re
import shutil
import tempfile
import six

from knossos import progress
from knossos.util import get, download, ipath, pjoin, gen_hash, is_archive, extract_archive

if six.PY2:
    import knossos.py2_compat


# This function will move the contents of src inside dest so that src/a/r/z.dat ends up as dest/a/r/z.dat.
# It will overwrite everything already present in the destination directory!
def movetree(src, dest, ifix=False):
    if ifix:
        dest = ipath(dest)
    
    if not os.path.isdir(dest):
        os.makedirs(dest)

    if ifix:
        siblings = os.listdir(dest)
        l_siblings = [s.lower() for s in siblings]

    for item in os.listdir(src):
        spath = os.path.join(src, item)
        dpath = os.path.join(dest, item)

        if ifix and not os.path.exists(dpath):
            if item.lower() in l_siblings:
                l_item = siblings[l_siblings.index(item.lower())]
                logging.warning('Changing path "%s" to "%s" to avoid case problems...', dpath, os.path.join(dest, l_item))

                dpath = os.path.join(dest, l_item)
            else:
                siblings.append(item)
                l_siblings.append(item.lower())

        if os.path.isdir(spath):
            movetree(spath, dpath)
        else:
            if os.path.exists(dpath):
                os.unlink(dpath)
            
            shutil.move(spath, dpath)


class EntryPoint(object):
    # These URLs are taken from the Java installer.
    # (in src/com/fsoinstaller/main/FreeSpaceOpenInstaller.java)
    # These point to the root files which contain the latest installer version
    # and links to the mod configs.
    HOME_URLS = ('http://www.fsoinstaller.com/files/installer/java/', 'http://scp.indiegames.us/fsoinstaller/')

    # Home files:
    # * version.txt
    # * filenames.txt
    # * basic_config.txt
    @classmethod
    def get(cls, file, use_first=True):
        if use_first:
            for home in cls.HOME_URLS:
                result = get(home + file)
                if result is not None:
                    return result

            return None
        else:
            results = []
            for home in cls.HOME_URLS:
                result = get(home + file)
                if result is not None:
                    results.append(result)

            return results

    @classmethod
    def get_lines(cls, file):
        lines = set()
        for result in cls.get(file, False):
            lines |= set(result.splitlines())
            result.close()

        return lines

    @classmethod
    def get_version(cls):
        # version.txt contains 2 lines: The version and the link to the installer's jar.
        return cls.get('version.txt').strip()

    @classmethod
    def get_basic_config(cls):
        # basic_config.txt contains one mod or installation option per line.
        # It contains all options which should be enabled for the "Basic" installation.

        return [line.strip() for line in cls.get_lines('basic_config.txt')]

    @classmethod
    def get_mods(cls):
        mods = []

        for link in cls.get_lines('filenames.txt'):
            data = get(link.strip())

            if data is None:
                continue
            else:
                mods.extend(ModParser().parse(data))

        return mods


class Parser(object):
    _data = None

    def _read(self):
        return self._data.pop(0).strip()

    def _read_until(self, end):
        res = []
        while True:
            line = self._read()
            if line == end:
                break
            else:
                res.append(line)

        return res


class ModParser(Parser):
    TOKENS = ('NAME', 'DESC', 'FOLDER', 'DELETE', 'RENAME', 'URL', 'MULTIURL', 'HASH', 'VERSION', 'NOTE', 'DEPENDENCIES', 'END')
    #ENDTOKENS = { 'DESC': 'ENDDESC', 'MULTIURL': 'ENDMULTI', 'NOTE': 'ENDNOTE', 'DEPENDENCIES': 'ENDDEPENDENCIES' }

    def parse(self, data, toplevel=True):
        if isinstance(data, six.string_types):
            data = data.split('\n')

        self._data = data
        mods = []

        # Look for NAME
        while len(self._data) > 0:
            line = self._read()

            if line == 'NAME':
                mods.append(self._parse_sub())
            elif line in self.TOKENS:
                logging.error('ModInfo: Found invalid token "%s" outside a mod!', line)
                break

        if len(mods) < 1:
            logging.error('ModInfo: No mod found!')

        return mods

    def _parse_sub(self):
        mod = ModInfo()
        mod.name = self._read()
        logging.debug('ModInfo: Parsing mod "%s"...', mod.name)

        while len(self._data) > 0:
            line = self._read()

            if line == '':
                continue

            if line not in self.TOKENS:
                if re.match('^[A-Z]+$', line):
                    logging.warning('ModInfo: Unexpected line "%s". Was expecting a token (%s).', line, ', '.join(self.TOKENS))
                else:
                    if len(mod.urls) < 1:
                        logging.error('ModInfo: Failed to add "%s" to "%s" because we have no URLs, yet!', line, mod.name)
                    else:
                        logging.debug('ModInfo: Adding "%s" to mod "%s".', line, mod.name)
                        mod.urls[-1][1].append(line)

                continue

            if line == 'DESC':
                mod.desc = '\n'.join(self._read_until('ENDDESC'))
            elif line == 'FOLDER':
                mod.folder = self._read().replace('\\', '/')
                if mod.folder == '/':
                    mod.folder = ''
            elif line == 'DELETE':
                mod.delete.append(normpath(self._read()))
            elif line == 'RENAME':
                mod.rename.append((normpath(self._read()), normpath(self._read())))
            elif line == 'URL':
                mod.urls.append(([self._read()], []))
            elif line == 'MULTIURL':
                mod.urls.append((self._read_until('ENDMULTI'), []))
            elif line == 'HASH':
                line = self._read()
                parts = re.split('\s+', line)
                if len(parts) == 3:
                    mod.hashes.append((parts[0], normpath(parts[1]), parts[2]))
                else:
                    mod.hashes.append((line, normpath(self._read()), self._read()))
            elif line == 'VERSION':
                mod.version = self._read()
            elif line == 'NOTE':
                mod.note = '\n'.join(self._read_until('ENDNOTE'))
            elif line == 'DEPENDENCIES':
                mod.dependencies = self._read_until('ENDDEPENDENCIES')
            elif line == 'NAME':
                sub = self._parse_sub()
                sub.parent = mod
                mod.submods.append(sub)
            elif line == 'END':
                break
            else:
                logging.warning('ModInfo: Ignoring token "%s" because it wasn\'t implemented!', line)

        return mod


class ModInfo(object):
    name = ''
    desc = ''
    folder = ''
    delete = None
    rename = None
    urls = None
    hashes = None
    version = ''
    note = ''
    dependencies = None
    submods = None
    parent = None
    ignore_subpath = False

    def __init__(self):
        self.delete = []
        self.rename = []
        self.urls = []
        self.hashes = []
        self.dependencies = []
        self.submods = []

    def download(self, dest, sel_files=None):
        count = 0
        num = 0
        for u, files in self.urls:
            if sel_files is not None:
                files = set(files) & sel_files
            count += len(files)

        for urls, files in self.urls:
            if not isinstance(urls, list):
                urls = [urls]

            if sel_files is not None:
                files = set(files) & sel_files
            
            for filename in files:
                done = False

                for link in urls:
                    with open(os.path.join(dest, filename), 'wb') as dl:
                        progress.start_task(float(num) / count, 1.0 / count, '%d/%d: %%s' % (num + 1, count))
                        if download(pjoin(link, filename), dl):
                            num += 1
                            done = True
                            progress.finish_task()
                            break
                        
                        progress.finish_task()

                if not done:
                    logging.error('Failed to download "%s"!', filename)
    
    def check_hashes(self, path):
        alright = True

        for algo, filepath, chksum in self.hashes:
            try:
                mysum = gen_hash(ipath(os.path.join(path, filepath)), algo)
            except:
                logging.exception('Failed to computed checksum for "%s" with algorithm "%s"!', filepath, algo)
                continue
            
            if mysum != chksum.lower():
                alright = False
                logging.warning('File "%s" has checksum "%s" but should have "%s"! Used algorithm: %s', filepath, mysum, chksum, algo)

        return alright

    def execute_del(self, path):
        count = float(len(self.delete))
        
        for i, item in enumerate(self.delete):
            logging.info('Deleting "%s"...', item)
            progress.update(i / count, 'Deleting "%s"...' % item)

            item = os.path.join(path, item)
            if os.path.isdir(item):
                shutil.rmtree(item)
            elif os.path.exists(item):
                os.unlink(item)
            else:
                logging.warning('"%s" not found!', item)

    def execute_rename(self, path):
        count = float(len(self.rename))
        i = 0
        
        for src, dest in self.rename:
            logging.info('Moving "%s" to "%s"...', src, dest)
            progress.update(i / count, 'Moving "%s" to "%s"...' % (src, dest))
            
            if os.path.exists(src):
                shutil.move(src, dest)
            else:
                logging.warning('"%s" not found!', src)
            i += 1

    def extract(self, path, sel_files=None):
        count = 0.0
        for u, files in self.urls:
            if sel_files is not None:
                files = set(files) & sel_files

            count += len(files)
        
        i = 0
        for u, files in self.urls:
            if sel_files is not None:
                files = set(files) & sel_files
            
            for item in files:
                mypath = os.path.join(path, item)
                if os.path.exists(mypath) and is_archive(mypath):
                    progress.update(i / count, 'Extracting "%s"...' % item)
                    
                    with tempfile.TemporaryDirectory() as tempdir:
                        # Extract to a temporary directory and then move the result
                        # to final destination to avoid "Do you want to overwrite?" questions.
                        
                        extract_archive(mypath, tempdir)
                        if self.ignore_subpath:
                            for sub_path, dirs, files in os.walk(tempdir):
                                for name in files:
                                    shutil.move(os.path.join(sub_path, name), ipath(os.path.join(path, name)))
                        else:
                            movetree(tempdir, path, ifix=True)
                
                i += 1
    
    def cleanup(self, path, sel_files=None):
        count = 0.0
        for u, files in self.urls:
            if sel_files is not None:
                files = set(files) & sel_files

            count += len(files)
        
        i = 0
        for u, files in self.urls:
            if sel_files is not None:
                files = set(files) & sel_files

            for item in files:
                mypath = os.path.join(path, item)
                if os.path.exists(mypath) and is_archive(mypath):
                    # Only remove the archives...
                    progress.update(i / count, 'Removing "%s"...' % item)
                    os.unlink(mypath)
                
                i += 1

    def setup(self, fs2_path):
        modpath = os.path.join(fs2_path, self.folder)

        if not os.path.isdir(modpath):
            os.mkdir(modpath)
        
        progress.start_task(0, 1/6.0)
        self.execute_del(modpath)
        progress.finish_task()
        
        progress.start_task(1/6.0, 1/6.0)
        self.execute_rename(modpath)
        progress.finish_task()
        
        progress.start_task(2/6.0, 1/6.0, 'Downloading: %s')
        self.download(modpath)
        progress.finish_task()
        
        progress.start_task(3/6.0, 1/6.0)
        self.extract(modpath)
        progress.finish_task()
        
        progress.start_task(4/6.0, 1/6.0)
        self.check_hashes(modpath)
        progress.finish_task()
        
        progress.start_task(5/6.0, 1/6.0)
        self.cleanup(modpath)
        progress.finish_task()
